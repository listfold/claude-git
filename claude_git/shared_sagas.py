"""
Shared atomic sagas for Claude Git hooks
These sagas perform single actions and can be composed together
"""

import os
from pathlib import Path

from claude_saga import (
    Call,
    Log,
    Put,
    Select,
    Stop,
    change_directory_effect,
    connect_pycharm_debugger_effect,
    create_directory_effect,
    run_command_effect,
    write_file_effect,
)

# Debug sagas


def pycharm_debug_saga():
    """Connect to PyCharm debugger if DEBUG_PYCHARM env var is set"""
    if os.environ.get("DEBUG_PYCHARM") != "1":
        return
    connected = yield Call(connect_pycharm_debugger_effect)
    if not connected:
        yield Stop("Failed to connect to PyCharm debugger")


# Git validation sagas


def validate_git_repository_saga():
    """Check if we're in a git repository and get the root path"""
    result = yield Call(run_command_effect, "git rev-parse --show-toplevel")
    if not result or result.returncode != 0:
        yield Stop("Not a git repository, run git init in project root to use this tool.")

    git_root = result.stdout.strip()
    yield Put({"git_root": git_root})


def validate_repo_root_saga():
    """Ensure Claude Code is running from the repository root"""
    state = yield Select()
    if state.git_root != state.cwd:
        yield Stop(
            "Claude Code is not running from the repo's root, run claude code from the repo root to use this tool."
        )


def change_to_git_root_saga():
    """Change the execution context to the git root directory"""
    state = yield Select()
    yield Call(change_directory_effect, state.git_root)


# Path and directory sagas


def setup_paths_saga():
    """Initialize state with required directory paths"""
    state = yield Select()
    claude_git_dir = Path(state.git_root) / ".claude" / "git"
    shadow_dir = claude_git_dir / "shadow-worktree"

    yield Put(
        {
            "claude_git_dir": claude_git_dir,
            "shadow_dir": shadow_dir,
        }
    )


def create_claude_directories_saga():
    """Create the .claude/git directory structure"""
    state = yield Select()

    # Create .claude/git directory
    claude_git_dir_result = yield Call(create_directory_effect, state.claude_git_dir)
    if not claude_git_dir_result:
        yield Stop(f"Failed to create Claude git directory: {state.claude_git_dir}")

    # Create shadow-worktree directory
    shadow_dir_result = yield Call(create_directory_effect, state.shadow_dir)
    if not shadow_dir_result:
        yield Stop(f"Failed to create shadow worktree directory: {state.shadow_dir}")


def ensure_gitignore_saga():
    """Add .claude/git to .gitignore if not already present"""
    state = yield Select()
    relative_path = state.claude_git_dir.relative_to(state.git_root)

    # Check if already in .gitignore
    check_result = yield Call(run_command_effect, f"grep -q '{relative_path}' .gitignore", cwd=state.git_root)

    if check_result.returncode != 0:
        # Add to .gitignore
        yield Call(run_command_effect, f"echo '{relative_path}/' >> .gitignore", cwd=state.git_root)
        yield Log("info", f"Added {relative_path}/ to .gitignore")


def verify_shadow_worktree_exists_saga():
    """Verify that shadow worktree exists and is valid"""
    state = yield Select()

    # Check if shadow worktree directory exists
    if not state.shadow_dir.exists():
        yield Log("info", "Shadow worktree doesn't exist yet")
        yield Stop("Shadow worktree not initialized")

    # Verify it's actually a worktree
    worktree_list = yield Call(run_command_effect, "git worktree list")
    if not worktree_list or str(state.shadow_dir) not in worktree_list.stdout:
        yield Log("warning", "Shadow directory exists but is not a git worktree")
        yield Stop("Invalid shadow worktree")

    yield Log("debug", f"Shadow worktree found at {state.shadow_dir}")


# Archive management sagas


def cleanup_archive_saga():
    """Clean up any previous archive directory"""
    state = yield Select()
    archive_dir = state.claude_git_dir / "main-archive"
    yield Call(run_command_effect, f'rm -rf "{archive_dir}"', capture_output=False)
    yield Put({"archive_dir": archive_dir})


def create_main_archive_saga():
    """Create a clean git archive of the main repository"""
    state = yield Select()

    # Create archive directory
    archive_dir_result = yield Call(create_directory_effect, state.archive_dir)
    if not archive_dir_result:
        yield Stop(f"Failed to create archive directory: {state.archive_dir}")

    # Extract git archive to archive directory
    archive_result = yield Call(run_command_effect, f'git archive HEAD | tar -x -C "{state.archive_dir}"')

    if archive_result and archive_result.returncode != 0:
        yield Stop("Failed to create git archive")


def capture_uncommitted_changes_saga():
    """Capture uncommitted changes from the main worktree"""
    # Get unstaged changes
    unstaged_diff = yield Call(run_command_effect, "git diff HEAD")

    # Get staged changes
    staged_diff = yield Call(run_command_effect, "git diff --cached HEAD")

    # Combine patches if there are any changes
    combined_patch = ""
    if unstaged_diff and unstaged_diff.stdout:
        combined_patch += unstaged_diff.stdout
    if staged_diff and staged_diff.stdout:
        combined_patch += staged_diff.stdout

    yield Put({"combined_patch": combined_patch})


def apply_uncommitted_to_archive_saga():
    """Apply uncommitted changes to archive to get current state"""
    state = yield Select()

    if not state.combined_patch:
        return  # No uncommitted changes

    patch_file = state.archive_dir / "uncommitted.patch"
    yield Call(write_file_effect, patch_file, state.combined_patch)

    # Apply to archive directory
    yield Call(
        run_command_effect,
        f'cd "{state.archive_dir}" && git apply --ignore-whitespace "{patch_file}"',
        capture_output=False,
    )

    # Cleanup patch file
    if patch_file.exists():
        patch_file.unlink()


def generate_cross_diff_saga():
    """Generate diff between clean archive and shadow worktree"""
    state = yield Select()

    cross_diff_result = yield Call(
        run_command_effect, f'git diff --no-index "{state.archive_dir}" "{state.shadow_dir}"'
    )

    cross_diff = ""

    # git diff --no-index returns exit code 1 when differences exist, 0 when identical
    if cross_diff_result and cross_diff_result.returncode == 0:
        yield Log("info", "Main repo and shadow worktree are already synchronized")
    elif cross_diff_result and cross_diff_result.returncode == 1:
        # Differences found - need to synchronize
        cross_diff = cross_diff_result.stdout.strip()
        yield Log("info", "Differences found, synchronizing shadow worktree with main repo")
    else:
        # Error occurred
        yield Stop("Failed to generate cross-repo diff")

    yield Put({"cross_diff": cross_diff})


# Shadow worktree management sagas


def reset_shadow_worktree_saga():
    """Reset shadow worktree to a clean state"""
    state = yield Select()

    # Change to shadow worktree directory
    yield Call(change_directory_effect, str(state.shadow_dir))

    # Reset shadow worktree to clean state
    yield Call(run_command_effect, "git reset --hard HEAD", capture_output=False)
    yield Call(run_command_effect, "git clean -fd", capture_output=False)


def apply_cross_diff_saga():
    """Apply cross-repo changes to shadow worktree if differences exist"""
    state = yield Select()

    if not state.cross_diff:
        return  # No differences to apply

    # Write cross-repo diff to temporary file
    diff_file = state.shadow_dir / "temp_cross_repo_sync.patch"
    yield Call(write_file_effect, diff_file, state.cross_diff)

    # Apply the cross-repo patch
    apply_result = yield Call(
        run_command_effect, f'git apply --reject --ignore-whitespace "{diff_file}"', capture_output=False
    )

    # Clean up temp file
    if diff_file.exists():
        diff_file.unlink()

    if apply_result and apply_result.returncode != 0:
        yield Log("warning", "Some patch chunks may have failed - manual review may be needed")

    # Stage all changes in shadow worktree
    yield Call(run_command_effect, "git add -A", capture_output=False)


def commit_changes_saga(commit_message: str):
    """Create a commit in the shadow worktree with the given message"""
    # Commit the changes
    commit_result = yield Call(
        run_command_effect, f'git commit --allow-empty -m "{commit_message}"', capture_output=False
    )

    if commit_result and commit_result.returncode == 0:
        yield Log("info", f"Created commit in shadow worktree: {commit_message}")
        return True
    else:
        yield Log("warning", "Failed to create commit")
        return False


def apply_uncommitted_changes_saga():
    """Apply uncommitted changes from main worktree as a separate commit"""
    state = yield Select()

    if not state.combined_patch:
        return  # No uncommitted changes to apply

    yield Log("info", "Applying uncommitted changes from main worktree as separate commit")

    # Write combined patch to file
    uncommitted_patch_file = state.claude_git_dir / "uncommitted_changes.patch"
    yield Call(write_file_effect, uncommitted_patch_file, state.combined_patch)

    # Apply patch to shadow worktree
    apply_to_shadow = yield Call(
        run_command_effect, f'git apply --reject --ignore-whitespace "{uncommitted_patch_file}"'
    )

    if apply_to_shadow and apply_to_shadow.returncode != 0:
        yield Log("warning", "Some uncommitted changes may have failed to apply to shadow worktree")

    # Clean up patch file
    if uncommitted_patch_file.exists():
        uncommitted_patch_file.unlink()

    # Stage the uncommitted changes
    yield Call(run_command_effect, "git add -A", capture_output=False)

    # Commit the uncommitted changes with a clear message
    uncommitted_commit_msg = f"Uncommitted changes from main worktree at sync time (session {state.session_id})"
    commit_result = yield Call(
        run_command_effect, f'git commit --allow-empty -m "{uncommitted_commit_msg}"', capture_output=False
    )

    if commit_result and commit_result.returncode == 0:
        yield Log("info", "Created separate commit for uncommitted changes")


def finalize_sync_saga():
    """Clean up and return to original directory"""
    state = yield Select()

    # Clean up archive directory
    yield Call(run_command_effect, f'rm -rf "{state.archive_dir}"', capture_output=False)

    # Return to original directory
    yield Call(change_directory_effect, state.git_root)


# Composition sagas for common workflows


def basic_git_setup_saga():
    """Basic git setup: validate, change to root, setup paths"""
    yield from validate_git_repository_saga()
    yield from validate_repo_root_saga()
    yield from change_to_git_root_saga()
    yield from setup_paths_saga()


def ensure_shadow_worktree_saga():
    """Ensure the shadow worktree exists"""
    state = yield Select()
    worktree_list = yield Call(run_command_effect, "git worktree list")
    if worktree_list and str(state.shadow_dir) in worktree_list.stdout:
        yield Log("info", "Shadow worktree already exists")
        return
    # Create shadow worktree if it doesn't exist
    yield Log("info", "Creating shadow worktree")

    # Create new worktree at current HEAD (later any uncommitted changes in the main repo will be added to the shadow)
    worktree_result = yield Call(run_command_effect, f'git worktree add -d "{state.shadow_dir}" HEAD')
    if not worktree_result or worktree_result.returncode != 0:
        yield Stop("Failed to create shadow worktree")

    yield Log("info", f"Created shadow worktree at {state.shadow_dir}")


def sync_worktrees_saga():
    """Synchronize main repo state to shadow worktree"""
    state = yield Select()

    # Navigate to git root for operations
    yield Call(change_directory_effect, state.git_root)

    # Execute synchronization steps
    yield from cleanup_archive_saga()
    yield from create_main_archive_saga()
    yield from capture_uncommitted_changes_saga()
    yield from generate_cross_diff_saga()
    yield from reset_shadow_worktree_saga()
    yield from apply_cross_diff_saga()

    # Commit sync changes if there were any
    if state.cross_diff:
        commit_msg = f"Sync with main repo state (session {state.session_id})"
        yield from commit_changes_saga(commit_msg)
        yield Log("info", "Shadow worktree synchronized with main repo")

    yield from apply_uncommitted_changes_saga()
    yield from finalize_sync_saga()


def detect_and_sync_changes_saga(commit_message_builder=None):
    """Detect changes and sync them to shadow worktree with optional commit"""
    state = yield Select()

    # Navigate to git root for operations
    yield Call(change_directory_effect, state.git_root)

    # Create archive and capture current state
    yield from cleanup_archive_saga()
    yield from create_main_archive_saga()
    yield from capture_uncommitted_changes_saga()
    yield from apply_uncommitted_to_archive_saga()  # Apply uncommitted to archive first
    yield from generate_cross_diff_saga()

    # Check if there are differences
    if state.cross_diff:
        yield Log("info", "Changes detected, updating shadow worktree")

        # Change to shadow worktree
        yield Call(change_directory_effect, str(state.shadow_dir))

        # Apply changes
        yield from apply_cross_diff_saga()

        # Build commit message
        if commit_message_builder:
            commit_msg = commit_message_builder(state)
        else:
            commit_msg = f"Changes detected (session {state.session_id})"

        # Create commit
        yield from commit_changes_saga(commit_msg)
    else:
        yield Log("info", "No changes detected between main repo and shadow worktree")

    # Cleanup
    yield from finalize_sync_saga()

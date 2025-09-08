#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
# "claude-saga==0.1.0"
# ]
# ///

"""
Undo slash command for Claude Git

Undoes the last N changes made by Claude by generating a reverse patch
from the shadow worktree and applying it to the main repository.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from claude_saga import (
    BaseSagaState,
    Call,
    Complete,
    Log,
    Put,
    SagaRuntime,
    Select,
    Stop,
    change_directory_effect,
    run_command_effect,
    write_file_effect,
)

from claude_git.shared_sagas import (
    basic_git_setup_saga,
    verify_shadow_worktree_exists_saga,
)


@dataclass
class UndoSagaState(BaseSagaState):
    """State object for undo operations"""

    # From basic_git_setup_saga
    git_root: str = None
    claude_git_dir: Path = None
    shadow_dir: Path = None

    # Undo-specific state
    n_commands: int = 1
    commits_to_undo: list = None
    reverse_patch: str = ""


# Atomic sagas for undo functionality


def validate_undo_arguments_saga(args_string: str):
    """Validate and parse undo arguments"""
    args = args_string.strip().split() if args_string.strip() else []

    if not args:
        # Default to 1 if no arguments provided
        yield Put({"n_commands": 1})
        return

    if len(args) != 1:
        yield Stop("Usage: /undo <number-of-commands>\nExample: /undo 2")

    try:
        n_commands = int(args[0])
        if n_commands <= 0:
            yield Stop("Number of commands must be a positive integer")
        yield Put({"n_commands": n_commands})
    except ValueError:
        yield Stop(f"Invalid number: '{args[0]}'. Must be a positive integer.")


def get_recent_commits_saga():
    """Get recent commits from shadow worktree"""
    state = yield Select()

    # Change to shadow worktree directory
    yield Call(change_directory_effect, str(state.shadow_dir))

    # Get the last n_commands commits
    commit_result = yield Call(run_command_effect, f"git log --oneline -n {state.n_commands} --format='%H %s'")

    if not commit_result or commit_result.returncode != 0:
        yield Stop("Failed to retrieve recent commits from shadow worktree")

    if not commit_result.stdout.strip():
        yield Stop("No commits found in shadow worktree to undo")

    # Parse commits
    commit_lines = commit_result.stdout.strip().split("\n")
    commits = []
    for line in commit_lines:
        if line.strip():
            parts = line.strip().split(" ", 1)
            min_parts = 2
            if len(parts) >= min_parts:
                commits.append({"hash": parts[0], "message": parts[1]})

    if not commits:
        yield Stop("No valid commits found to undo")

    yield Put({"commits_to_undo": commits})
    yield Log("info", f"Found {len(commits)} commit(s) to undo")


def generate_reverse_patch_saga():
    """Generate reverse patch from commits to undo"""
    state = yield Select()

    if not state.commits_to_undo:
        yield Stop("No commits available to generate reverse patch")

    # Get the oldest commit hash (last in our list since we got them with git log)
    oldest_commit = state.commits_to_undo[-1]["hash"]

    # Create reverse patch from oldest_commit~1 to HEAD (reverse order)
    # This will create a patch that undoes all the changes from oldest_commit to HEAD
    patch_result = yield Call(run_command_effect, f"git diff {oldest_commit}~1..HEAD")

    if not patch_result or patch_result.returncode != 0:
        yield Stop("Failed to generate patch from shadow worktree commits")

    if not patch_result.stdout.strip():
        yield Log("info", "No changes to undo (empty patch)")
        yield Put({"reverse_patch": ""})
        return

    # The patch shows changes from oldest~1 to HEAD, but we want to reverse them
    # So we need to generate the reverse patch
    reverse_patch_result = yield Call(run_command_effect, f"git diff HEAD..{oldest_commit}~1")

    if not reverse_patch_result or reverse_patch_result.returncode != 0:
        yield Stop("Failed to generate reverse patch")

    yield Put({"reverse_patch": reverse_patch_result.stdout})

    if reverse_patch_result.stdout.strip():
        yield Log("info", "Generated reverse patch to undo changes")
    else:
        yield Log("info", "No changes to undo")


def validate_reverse_patch_saga():
    """Validate that reverse patch can be applied to main repo"""
    state = yield Select()

    if not state.reverse_patch.strip():
        return  # Nothing to validate

    # Change back to main repo
    yield Call(change_directory_effect, state.git_root)

    # Write patch to temporary file for validation
    patch_file = Path(state.git_root) / "temp_undo.patch"
    yield Call(write_file_effect, patch_file, state.reverse_patch)

    # Test if patch can be applied with --check
    check_result = yield Call(run_command_effect, f'git apply --check "{patch_file}"')

    # Clean up temp file
    if patch_file.exists():
        patch_file.unlink()

    if check_result and check_result.returncode != 0:
        yield Stop(
            "Cannot apply undo patch cleanly. This might happen if:\n"
            "1. The main repository has been modified since the Claude changes\n"
            "2. The files have conflicts\n"
            "3. The changes have already been manually undone\n\n"
            "You may need to manually resolve conflicts or reset the repository state."
        )

    yield Log("info", "Reverse patch validation successful")


def apply_reverse_patch_saga():
    """Apply the reverse patch to main repository"""
    state = yield Select()

    if not state.reverse_patch.strip():
        yield Log("info", "No patch to apply - nothing to undo")
        return

    # Ensure we're in the main repo
    yield Call(change_directory_effect, state.git_root)

    # Write patch to temporary file
    patch_file = Path(state.git_root) / "temp_undo.patch"
    yield Call(write_file_effect, patch_file, state.reverse_patch)

    # Apply the patch
    apply_result = yield Call(run_command_effect, f'git apply "{patch_file}"')

    # Clean up temp file
    if patch_file.exists():
        patch_file.unlink()

    if apply_result and apply_result.returncode != 0:
        yield Stop("Failed to apply undo patch. Repository may be in an inconsistent state.")

    yield Log("info", "Successfully applied undo patch to main repository")


def revert_shadow_worktree_saga():
    """Reset shadow worktree back N commits to reflect the undo"""
    state = yield Select()

    if not state.commits_to_undo:
        return  # Nothing to revert

    commit_count = len(state.commits_to_undo)

    # Change to shadow worktree directory
    yield Call(change_directory_effect, str(state.shadow_dir))

    # Reset shadow worktree back N commits (hard reset to remove the commits)
    oldest_commit = state.commits_to_undo[-1]["hash"]  # Last in list is oldest
    reset_target = f"{oldest_commit}~1"  # One commit before the oldest commit we're undoing

    reset_result = yield Call(run_command_effect, f"git reset --hard {reset_target}")

    if reset_result and reset_result.returncode != 0:
        yield Stop("Failed to reset shadow worktree state")

    yield Log("info", f"Shadow worktree reset back {commit_count} commit{'s' if commit_count > 1 else ''}")

    # Clean any untracked files that might remain
    clean_result = yield Call(run_command_effect, "git clean -fd")
    if clean_result and clean_result.returncode != 0:
        yield Log("warning", "Failed to clean untracked files in shadow worktree")

    yield Log("info", "Shadow worktree state synchronized with undo operation")


# Composition saga


def undo_changes_saga(args_string: str):
    """Main saga to undo the last N Claude changes"""
    # Setup and validation
    yield from validate_undo_arguments_saga(args_string)
    yield from basic_git_setup_saga()
    yield from verify_shadow_worktree_exists_saga()

    # Get commits and generate reverse patch
    yield from get_recent_commits_saga()
    yield from generate_reverse_patch_saga()

    # Validate and apply the undo (no commit in main repo)
    yield from validate_reverse_patch_saga()
    yield from apply_reverse_patch_saga()

    # Reset shadow worktree to reflect the undo
    yield from revert_shadow_worktree_saga()

    yield Complete("Undo operation completed successfully")


# CLI entry point for slash command


def main():
    """Main entry point for the undo slash command"""
    # Get arguments from command line or environment
    args_string = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else os.environ.get("ARGUMENTS", "")

    try:
        # Create runtime with undo state
        state = UndoSagaState()
        state.cwd = str(Path.cwd())
        runtime = SagaRuntime(state)
        # Run the undo saga
        final_state = runtime.run(undo_changes_saga(args_string))

        # Output result based on final state
        if final_state.continue_:
            print("Undo completed successfully")
            sys.exit(0)
        else:
            print("Undo operation failed", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error during undo operation: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

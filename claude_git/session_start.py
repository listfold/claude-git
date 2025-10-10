# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pydevd-pycharm==251.23774.444"
# "claude-saga==0.1.0"
# ]
# ///

"""
Init hook saga - Initializes shadow worktrees for Claude sessions
Uses the claude-saga framework for saga-based effect handling.
Run on the SessionStart CC hook: https://docs.anthropic.com/en/docs/claude-code/hooks#sessionstart
"""

import json
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
    parse_json_saga,
    run_command_effect,
    validate_input_saga,
)

from .shared_sagas import (
    change_to_git_root_saga,
    create_claude_directories_saga,
    detect_and_sync_changes_saga,
    ensure_gitignore_saga,
    ensure_shadow_worktree_saga,
    pycharm_debug_saga,
    setup_paths_saga,
    validate_git_repository_saga,
    validate_repo_root_saga,
)


@dataclass
class InitSagaState(BaseSagaState):
    """State object specific to init hook"""

    # Git-related state (session_id is already in BaseSagaState)
    git_root: str | None = None
    claude_git_dir: Path | None = None
    shadow_dir: Path | None = None


# All atomic sagas are now imported from shared_sagas


def setup_and_validate_saga():
    """Composition saga for all setup and validation steps"""
    yield from validate_git_repository_saga()
    yield from validate_repo_root_saga()
    yield from change_to_git_root_saga()
    yield from setup_paths_saga()
    yield from create_claude_directories_saga()
    yield from ensure_gitignore_saga()


def cleanup_shadow_worktree_saga():
    """Remove existing shadow worktree and prune worktree references"""
    state = yield Select()

    # Remove .claude/git directory if it exists
    if state.claude_git_dir and state.claude_git_dir.exists():
        yield Log("info", "Removing existing shadow worktree")
        yield Call(run_command_effect, f'rm -rf "{state.claude_git_dir}"', capture_output=False)

    # Prune worktree references
    yield Call(run_command_effect, "git worktree prune", capture_output=False)
    yield Log("info", "Cleaned up shadow worktree")


def synchronize_main_to_shadow_saga():
    """Composition saga to synchronize shadow worktree with main repo state"""
    yield from detect_and_sync_changes_saga(
        commit_message_builder=lambda state: f"Sync with main repo state (session {state.session_id})"
    )
    yield Complete("Shadow worktree is ready for this session")


def main_saga():
    """Main saga that handles complete shadow worktree initialization"""
    # Input validation and parsing
    yield from validate_input_saga()
    # Initialize state with hook input json.
    yield from parse_json_saga()
    # Initialize state with fields required by our sagas
    yield Put(
        {
            "git_root": None,
            "claude_git_dir": None,
            "shadow_dir": None,
            "archive_dir": None,
            "cross_diff": "",
            "combined_patch": "",
            "initial_state_file": None,
        }
    )

    # Complete shadow worktree setup - fresh start each session
    yield from pycharm_debug_saga()  # Debug setup if needed
    yield from validate_git_repository_saga()  # Validate we're in a git repo
    yield from validate_repo_root_saga()  # Validate we're at the repo root
    yield from change_to_git_root_saga()  # Change to git root
    yield from setup_paths_saga()  # Setup paths
    yield from cleanup_shadow_worktree_saga()  # Clean up any existing shadow worktree
    yield from create_claude_directories_saga()  # Recreate .claude/git directories
    yield from ensure_gitignore_saga()  # Ensure .gitignore has .claude/git
    yield from ensure_shadow_worktree_saga()  # Create new shadow worktree
    yield from synchronize_main_to_shadow_saga()  # Sync main → shadow


def main():
    """Main entry point - pure orchestration"""
    # Create runtime with empty initial state object
    runtime = SagaRuntime(InitSagaState())
    # Run the saga
    final_state = runtime.run(main_saga())
    # Output the final state as JSON, CC uses hook stdout to decide its next step.
    print(json.dumps(final_state.to_json()))
    # Exit with appropriate code
    if final_state.continue_:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

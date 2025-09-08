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
    Complete,
    Put,
    SagaRuntime,
    parse_json_saga,
    validate_input_saga,
)

from .shared_sagas import (
    change_to_git_root_saga,
    create_claude_directories_saga,
    ensure_gitignore_saga,
    ensure_shadow_worktree_saga,
    pycharm_debug_saga,
    setup_paths_saga,
    sync_worktrees_saga,
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


# ensure_shadow_worktree_saga is now imported from shared_sagas


# All synchronization sagas are now imported from shared_sagas


def synchronize_main_to_shadow_saga():
    """Composition saga to synchronize shadow worktree with main repo state"""
    yield from sync_worktrees_saga()
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

    # Complete shadow worktree setup - consolidated 4-step process
    yield from pycharm_debug_saga()  # Debug setup if needed
    yield from setup_and_validate_saga()  # Step 1: Setup & validation (composition of atomic sagas)
    yield from ensure_shadow_worktree_saga()  # Step 2: Ensure shadow worktree exists
    yield from synchronize_main_to_shadow_saga()  # Step 3: Sync main → shadow (composition of atomic sagas)


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

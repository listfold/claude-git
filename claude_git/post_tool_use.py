# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pydevd-pycharm==251.23774.444"
# "claude-saga==0.1.0"
# ]
# ///

"""
PostToolUse hook saga - Commits changes to shadow worktree after Claude modifies files
Uses the claude-saga framework for saga-based effect handling.
Run on the PostToolUse CC hook: https://docs.anthropic.com/en/docs/claude-code/hooks#posttooluse
"""

import json
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
    connect_pycharm_debugger_effect,
    parse_json_saga,
    validate_input_saga,
)

from .shared_sagas import (
    basic_git_setup_saga,
    detect_and_sync_changes_saga,
    verify_shadow_worktree_exists_saga,
)


@dataclass
class PostToolUseSagaState(BaseSagaState):
    """State object specific to PostToolUse hook"""

    # Git-related state
    git_root: str | None = None
    claude_git_dir: Path | None = None
    shadow_dir: Path | None = None
    # Tool-specific state
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_response: dict | None = None


def pycharm_debug_saga():
    """Connect to PyCharm debugger if DEBUG_PYCHARM env var is set"""
    if os.environ.get("DEBUG_PYCHARM") != "1":
        return
    connected = yield Call(connect_pycharm_debugger_effect)
    if not connected:
        yield Stop("Failed to connect to PyCharm debugger")


def validate_and_setup_saga():
    """Validate git repo and locate shadow worktree"""
    # Use shared basic setup
    yield from basic_git_setup_saga()

    # Verify shadow worktree exists (specific to post tool use)
    yield from verify_shadow_worktree_exists_saga()


def should_track_tool_saga():
    """Check if this tool should trigger a commit"""
    state = yield Select()

    # Tools that modify files
    tracked_tools = ["Write", "Edit", "MultiEdit", "NotebookEdit", "TodoWrite", "Create", "Delete", "Move", "Copy"]

    if state.tool_name not in tracked_tools:
        yield Log("debug", f"Tool '{state.tool_name}' doesn't modify files, skipping")
        yield Stop("Tool doesn't require tracking")

    # Check if the tool actually succeeded
    if state.tool_response and not state.tool_response.get("success", True):
        yield Log("debug", f"Tool '{state.tool_name}' failed, skipping commit")
        yield Stop("Tool execution failed")

    yield Log("info", f"Tracking changes from tool: {state.tool_name}")


def detect_and_commit_changes_saga():
    """Detect changes between main repo and shadow, commit if different"""
    yield from detect_and_sync_changes_saga(commit_message_builder=build_commit_message)


def build_commit_message(state):
    """Build a descriptive commit message from tool information"""
    tool_name = state.tool_name or "Unknown"
    session_id = state.session_id or "unknown"

    # Extract file information if available
    file_info = ""
    if state.tool_input:
        if "file_path" in state.tool_input:
            file_info = f": {state.tool_input['file_path']}"
        elif "path" in state.tool_input:
            file_info = f": {state.tool_input['path']}"
        elif "files" in state.tool_input:
            files = state.tool_input["files"]
            if isinstance(files, list) and files:
                max_files_display = 3
                file_info = f": {', '.join(files[:max_files_display])}"
                if len(files) > max_files_display:
                    file_info += f" and {len(files) - max_files_display} more"

    return f"{tool_name}{file_info} (session: {session_id})"


def main_saga():
    """Main saga for PostToolUse hook"""
    # Input validation and parsing
    yield from validate_input_saga()
    # Parse JSON input
    yield from parse_json_saga()

    # Extract tool-specific information from parsed input
    state = yield Select()
    tool_name = state.hook_input.get("tool_name")
    tool_input = state.hook_input.get("tool_input", {})
    tool_response = state.hook_input.get("tool_response", {})

    # Store tool information in state
    yield Put(
        {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_response": tool_response,
            "git_root": None,
            "claude_git_dir": None,
            "shadow_dir": None,
            "archive_dir": None,
            "cross_diff": "",
            "combined_patch": "",
        }
    )

    # Run the hook workflow
    yield from pycharm_debug_saga()
    yield from validate_and_setup_saga()
    yield from should_track_tool_saga()
    yield from detect_and_commit_changes_saga()

    yield Complete(f"Successfully tracked changes from {tool_name}")


def main():
    """Main entry point"""
    # Create runtime with initial state
    runtime = SagaRuntime(PostToolUseSagaState())
    # Run the saga
    final_state = runtime.run(main_saga())
    # Output the final state as JSON
    print(json.dumps(final_state.to_json()))
    # Exit with appropriate code
    if final_state.continue_:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

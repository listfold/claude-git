# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pytest>=8.0.0",
# "claude-saga==0.1.0"
# ]
# ///

"""
Tests for shared_sagas.py
Tests the shared atomic sagas used by both hooks
"""

import os
from pathlib import Path
from unittest.mock import Mock

from claude_saga import (
    Call,
    Complete,
    Log,
    Put,
    Select,
    Stop,
    change_directory_effect,
    run_command_effect,
    write_file_effect,
)

from claude_git.shared_sagas import (
    apply_cross_diff_saga,
    basic_git_setup_saga,
    capture_uncommitted_changes_saga,
    cleanup_archive_saga,
    ensure_shadow_worktree_saga,
    finalize_sync_saga,
    generate_cross_diff_saga,
    pycharm_debug_saga,
    setup_paths_saga,
    sync_worktrees_saga,
    validate_git_repository_saga,
    verify_shadow_worktree_exists_saga,
)


class SagaTester:
    """Helper class to test saga generators"""

    def __init__(self, saga_gen):
        self.saga = saga_gen
        self.effects = []

    def send_value(self, value):
        """Send a value to the saga and get the next effect"""
        try:
            effect = next(self.saga) if not self.effects else self.saga.send(value)
            self.effects.append(effect)
            return effect
        except StopIteration as e:
            return e.value


def test_pycharm_debug_saga_disabled():
    """Test pycharm debug saga when DEBUG_PYCHARM is not set"""
    original = os.environ.get("DEBUG_PYCHARM")
    if "DEBUG_PYCHARM" in os.environ:
        del os.environ["DEBUG_PYCHARM"]

    try:
        saga = pycharm_debug_saga()
        tester = SagaTester(saga)

        # Should return immediately (no effects)
        effect = tester.send_value(None)
        assert effect is None
    finally:
        if original is not None:
            os.environ["DEBUG_PYCHARM"] = original


def test_validate_git_repository_saga():
    """Test git repository validation"""
    saga = validate_git_repository_saga()
    tester = SagaTester(saga)

    # First effect should be Call to run git command
    effect = tester.send_value(None)
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert effect.args[0] == "git rev-parse --show-toplevel"

    # Send successful result
    result = Mock(returncode=0, stdout="/path/to/repo\n")
    effect = tester.send_value(result)

    # Should Put the git_root
    assert isinstance(effect, Put)
    assert effect.payload == {"git_root": "/path/to/repo"}


def test_setup_paths_saga():
    """Test path setup saga"""
    saga = setup_paths_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with git_root
    state = Mock()
    state.git_root = "/path/to/repo"
    effect = tester.send_value(state)

    # Should Put the paths
    assert isinstance(effect, Put)
    assert "claude_git_dir" in effect.payload
    assert "shadow_dir" in effect.payload
    assert effect.payload["claude_git_dir"] == Path("/path/to/repo/.claude/git")
    assert effect.payload["shadow_dir"] == Path("/path/to/repo/.claude/git/shadow-worktree")


def test_verify_shadow_worktree_exists_saga_missing():
    """Test shadow worktree verification when directory doesn't exist"""
    saga = verify_shadow_worktree_exists_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with non-existent shadow_dir
    state = Mock()
    state.shadow_dir = Mock()
    state.shadow_dir.exists.return_value = False
    effect = tester.send_value(state)

    # Should log info
    assert isinstance(effect, Log)
    assert "doesn't exist yet" in effect.message

    # Send None for log
    effect = tester.send_value(None)

    # Should Stop
    assert isinstance(effect, Stop)
    assert "not initialized" in effect.payload


def test_cleanup_archive_saga():
    """Test archive cleanup saga"""
    saga = cleanup_archive_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state
    state = Mock()
    state.claude_git_dir = Path("/path/to/repo/.claude/git")
    effect = tester.send_value(state)

    # Should remove archive directory
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "rm -rf" in effect.args[0]
    assert "main-archive" in effect.args[0]

    # Send success
    effect = tester.send_value(Mock(returncode=0))

    # Should Put archive_dir
    assert isinstance(effect, Put)
    assert "archive_dir" in effect.payload


def test_capture_uncommitted_changes_saga():
    """Test capturing uncommitted changes"""
    saga = capture_uncommitted_changes_saga()
    tester = SagaTester(saga)

    # Should get unstaged diff
    effect = tester.send_value(None)
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert effect.args[0] == "git diff HEAD"

    # Send unstaged diff
    unstaged = Mock(stdout="unstaged changes\n")
    effect = tester.send_value(unstaged)

    # Should get staged diff
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert effect.args[0] == "git diff --cached HEAD"

    # Send staged diff
    staged = Mock(stdout="staged changes\n")
    effect = tester.send_value(staged)

    # Should Put combined patch
    assert isinstance(effect, Put)
    assert "combined_patch" in effect.payload
    assert "unstaged changes" in effect.payload["combined_patch"]
    assert "staged changes" in effect.payload["combined_patch"]


def test_generate_cross_diff_saga_no_differences():
    """Test generating cross diff with no differences"""
    saga = generate_cross_diff_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state
    state = Mock()
    state.archive_dir = Path("/archive")
    state.shadow_dir = Path("/shadow")
    effect = tester.send_value(state)

    # Should run git diff --no-index
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "git diff --no-index" in effect.args[0]

    # Send result with no differences (exit code 0)
    result = Mock(returncode=0, stdout="")
    effect = tester.send_value(result)

    # Should log info
    assert isinstance(effect, Log)
    assert "already synchronized" in effect.message

    # Send none for log
    effect = tester.send_value(None)

    # Should Put empty cross_diff
    assert isinstance(effect, Put)
    assert effect.payload["cross_diff"] == ""


def test_apply_cross_diff_saga_no_changes():
    """Test apply_cross_diff_saga when there are no changes"""
    saga = apply_cross_diff_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with empty cross_diff
    state = Mock()
    state.cross_diff = ""
    effect = tester.send_value(state)

    # Should return early (no more effects)
    assert effect is None


def test_apply_cross_diff_saga_with_changes():
    """Test apply_cross_diff_saga when there are changes"""
    saga = apply_cross_diff_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with cross_diff
    state = Mock()
    state.shadow_dir = Path("/shadow")
    state.cross_diff = "diff content here"
    effect = tester.send_value(state)

    # Should write diff to file
    assert isinstance(effect, Call)
    assert effect.fn == write_file_effect

    # Send None for write
    effect = tester.send_value(None)

    # Should apply patch
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "git apply" in effect.args[0]


def test_basic_git_setup_saga():
    """Test basic git setup composition saga"""
    saga = basic_git_setup_saga()
    effects_seen = []

    # Track effects through the composition
    try:
        effect = next(saga)
        while True:
            effects_seen.append(effect)

            # Provide responses
            if isinstance(effect, Call):
                if "git rev-parse" in str(effect.args):
                    response = Mock(returncode=0, stdout="/repo\n")
                else:
                    response = Mock(returncode=0)
            elif isinstance(effect, Select):
                response = Mock(git_root="/repo", cwd="/repo")
            elif isinstance(effect, Put):
                response = None
            else:
                response = None

            effect = saga.send(response)
    except StopIteration:
        pass

    # Should have multiple effects from sub-sagas
    call_effects = [e for e in effects_seen if isinstance(e, Call)]
    put_effects = [e for e in effects_seen if isinstance(e, Put)]

    assert len(call_effects) > 0  # At least git validation call
    assert len(put_effects) > 0  # At least paths setup


def test_ensure_shadow_worktree_saga_already_exists():
    """Test ensure shadow worktree when it already exists"""
    saga = ensure_shadow_worktree_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state
    state = Mock()
    state.shadow_dir = "/shadow/path"
    effect = tester.send_value(state)

    # Should check worktree list
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "git worktree list" in effect.args[0]

    # Send result showing worktree exists
    result = Mock(stdout="/shadow/path")
    effect = tester.send_value(result)

    # Should log and return
    assert isinstance(effect, Log)
    assert "already exists" in effect.message


def test_finalize_sync_saga():
    """Test finalize sync saga"""
    saga = finalize_sync_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state
    state = Mock()
    state.archive_dir = "/archive"
    state.git_root = "/repo"
    effect = tester.send_value(state)

    # Should cleanup archive
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "rm -rf" in effect.args[0]

    # Send success
    effect = tester.send_value(Mock(returncode=0))

    # Should change back to git root
    assert isinstance(effect, Call)
    assert effect.fn == change_directory_effect
    assert effect.args[0] == "/repo"


def test_sync_worktrees_saga_composition():
    """Test sync worktrees composition saga"""
    saga = sync_worktrees_saga()
    effects_seen = []

    # Run through the saga with mock responses
    try:
        effect = next(saga)
        while True:
            effects_seen.append(effect)

            if isinstance(effect, Call):
                response = Mock(returncode=0, stdout="")
            elif isinstance(effect, Select):
                response = Mock(
                    git_root="/repo",
                    claude_git_dir=Path("/repo/.claude/git"),
                    shadow_dir=Path("/repo/.claude/git/shadow-worktree"),
                    archive_dir=Path("/repo/.claude/git/main-archive"),
                    cross_diff="",
                    combined_patch="",
                    session_id="test",
                )
            elif isinstance(effect, Complete):
                break
            else:
                response = None

            effect = saga.send(response)
    except StopIteration:
        pass

    # Should have multiple operations
    call_effects = [e for e in effects_seen if isinstance(e, Call)]
    min_expected_saga_operations = 5
    assert len(call_effects) > min_expected_saga_operations  # Archive, diff, reset, etc.


if __name__ == "__main__":
    # Run some basic tests
    test_validate_git_repository_saga()
    test_setup_paths_saga()
    test_capture_uncommitted_changes_saga()
    test_apply_cross_diff_saga_no_changes()
    print("Basic shared saga tests passed!")

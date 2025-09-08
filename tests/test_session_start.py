# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pytest>=8.0.0",
# "claude-saga==0.1.0"
# ]
# ///

"""
Tests for session_start.py sagas
Tests the saga pattern implementation with minimal mocking
"""

from pathlib import Path
from unittest.mock import Mock

from claude_saga import (
    Call,
    Complete,
    Log,
    Put,
    Select,
    Stop,
    create_directory_effect,
    run_command_effect,
    write_file_effect,
)

from claude_git.session_start import (
    InitSagaState,
    setup_and_validate_saga,
    synchronize_main_to_shadow_saga,
)
from claude_git.shared_sagas import (
    apply_cross_diff_saga,
    apply_uncommitted_changes_saga,
    capture_uncommitted_changes_saga,
    cleanup_archive_saga,
    create_claude_directories_saga,
    ensure_gitignore_saga,
    generate_cross_diff_saga,
    setup_paths_saga,
    validate_git_repository_saga,
    validate_repo_root_saga,
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

    def send_select(self, state):
        """Send a Select response with the given state"""
        return self.send_value(state)

    def assert_effect_type(self, effect, expected_type):
        """Assert that an effect is of the expected type"""
        assert type(effect).__name__ == expected_type.__name__

    def run_until_complete(self, responses=None):
        """Run the saga until it completes, providing responses for each effect"""
        responses = responses or {}
        effect_count = 0

        while True:
            try:
                if effect_count == 0:
                    effect = next(self.saga)
                else:
                    # Provide response based on effect type
                    response = responses.get(effect_count - 1, None)
                    effect = self.saga.send(response)

                self.effects.append(effect)
                effect_count += 1

                if isinstance(effect, Stop | Complete):
                    return effect

            except StopIteration:
                break

        return None


# Test atomic validation sagas


def test_validate_git_repository_saga_success():
    """Test successful git repository validation"""
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


def test_validate_git_repository_saga_failure():
    """Test failed git repository validation"""
    saga = validate_git_repository_saga()
    tester = SagaTester(saga)

    # First effect should be Call to run git command
    effect = tester.send_value(None)
    assert isinstance(effect, Call)

    # Send failed result
    result = Mock(returncode=128, stdout="")
    effect = tester.send_value(result)

    # Should Stop with error message
    assert isinstance(effect, Stop)
    assert "Not a git repository" in effect.payload


def test_validate_repo_root_saga_success():
    """Test successful repo root validation"""
    saga = validate_repo_root_saga()
    tester = SagaTester(saga)

    # First effect should be Select to get state
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state where git_root matches cwd
    state = InitSagaState(git_root="/path/to/repo", cwd="/path/to/repo")
    effect = tester.send_value(state)

    # Should complete without Stop
    assert effect is None


def test_validate_repo_root_saga_failure():
    """Test failed repo root validation"""
    saga = validate_repo_root_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state where git_root doesn't match cwd
    state = InitSagaState(git_root="/path/to/repo", cwd="/different/path")
    effect = tester.send_value(state)

    # Should Stop with error message
    assert isinstance(effect, Stop)
    assert "not running from the repo's root" in effect.payload


def test_setup_paths_saga():
    """Test path setup saga"""
    saga = setup_paths_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with git_root
    state = InitSagaState(git_root="/path/to/repo")
    effect = tester.send_value(state)

    # Should Put the paths
    assert isinstance(effect, Put)
    assert "claude_git_dir" in effect.payload
    assert "shadow_dir" in effect.payload
    assert effect.payload["claude_git_dir"] == Path("/path/to/repo/.claude/git")
    assert effect.payload["shadow_dir"] == Path("/path/to/repo/.claude/git/shadow-worktree")


def test_create_claude_directories_saga_success():
    """Test successful directory creation"""
    saga = create_claude_directories_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with paths
    state = InitSagaState(
        claude_git_dir=Path("/path/to/repo/.claude/git"), shadow_dir=Path("/path/to/repo/.claude/git/shadow-worktree")
    )
    effect = tester.send_value(state)

    # Should Call create_directory_effect for claude_git_dir
    assert isinstance(effect, Call)
    assert effect.fn == create_directory_effect
    assert effect.args[0] == state.claude_git_dir

    # Send success
    effect = tester.send_value(True)

    # Should Call create_directory_effect for shadow_dir
    assert isinstance(effect, Call)
    assert effect.fn == create_directory_effect
    assert effect.args[0] == state.shadow_dir

    # Send success
    effect = tester.send_value(True)

    # Should complete
    assert effect is None


def test_ensure_gitignore_saga_not_present():
    """Test adding to .gitignore when not already present"""
    saga = ensure_gitignore_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state
    state = InitSagaState(git_root="/path/to/repo", claude_git_dir=Path("/path/to/repo/.claude/git"))
    effect = tester.send_value(state)

    # Should check if already in .gitignore
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "grep" in effect.args[0]
    assert ".claude/git" in effect.args[0]

    # Send result indicating not found (grep returns 1 when not found)
    result = Mock(returncode=1)
    effect = tester.send_value(result)

    # Should add to .gitignore
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "echo" in effect.args[0]
    assert ".gitignore" in effect.args[0]

    # Send success
    effect = tester.send_value(Mock(returncode=0))

    # Should log
    assert isinstance(effect, Log)
    assert "Added" in effect.message


# Test atomic synchronization sagas


def test_cleanup_archive_saga():
    """Test archive cleanup saga"""
    saga = cleanup_archive_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state
    state = InitSagaState(claude_git_dir=Path("/path/to/repo/.claude/git"))
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

    # Send state - create a mock state with the needed attributes
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


def test_apply_cross_diff_saga_with_changes():
    """Test applying cross diff when there are changes"""
    saga = apply_cross_diff_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with cross_diff - use mock state
    state = Mock()
    state.shadow_dir = Path("/shadow")
    state.cross_diff = "diff content here"
    state.session_id = "test-session"
    effect = tester.send_value(state)

    # Should write diff to file
    assert isinstance(effect, Call)
    assert effect.fn == write_file_effect

    # Continue through the saga
    responses = [
        None,  # write_file_effect response
        Mock(returncode=0),  # git apply response
        Mock(returncode=0),  # git add response
        Mock(returncode=0),  # git commit response
        None,  # Log response
    ]

    for response in responses:
        effect = tester.send_value(response)
        if effect is None:
            break


# Test composition sagas


def test_setup_and_validate_saga_composition():
    """Test that setup_and_validate_saga calls all sub-sagas"""
    saga = setup_and_validate_saga()

    # Track which sub-sagas are called by checking effects
    effects_seen = []

    # This saga is a composition, so it will yield from multiple sub-sagas
    # We'll iterate through and collect all effects
    try:
        effect = next(saga)
        while True:
            effects_seen.append(effect)

            # Provide appropriate responses based on effect type
            if isinstance(effect, Call):
                if effect.fn == run_command_effect:
                    if "git rev-parse" in str(effect.args):
                        response = Mock(returncode=0, stdout="/repo\n")
                    else:
                        response = Mock(returncode=0)
                else:
                    response = True
            elif isinstance(effect, Select):
                response = InitSagaState(
                    git_root="/repo",
                    cwd="/repo",
                    claude_git_dir=Path("/repo/.claude/git"),
                    shadow_dir=Path("/repo/.claude/git/shadow-worktree"),
                )
            elif isinstance(effect, Put | Log):
                response = None
            else:
                response = None

            effect = saga.send(response)
    except StopIteration:
        pass

    # Verify we saw effects from multiple sub-sagas
    call_effects = [e for e in effects_seen if isinstance(e, Call)]
    put_effects = [e for e in effects_seen if isinstance(e, Put)]
    select_effects = [e for e in effects_seen if isinstance(e, Select)]

    # Should have multiple Calls, Puts, and Selects from the sub-sagas
    assert len(call_effects) > 0
    assert len(put_effects) > 0
    assert len(select_effects) > 0


def test_synchronize_main_to_shadow_saga_composition():
    """Test that synchronize saga calls all sub-sagas in order"""
    saga = synchronize_main_to_shadow_saga()

    effects_seen = []

    try:
        effect = next(saga)
        while True:
            effects_seen.append(effect)

            # Provide responses
            if isinstance(effect, Call):
                response = Mock(returncode=0, stdout="")
            elif isinstance(effect, Select):
                response = Mock()
                response.git_root = "/repo"
                response.claude_git_dir = Path("/repo/.claude/git")
                response.shadow_dir = Path("/repo/.claude/git/shadow-worktree")
                response.archive_dir = Path("/repo/.claude/git/main-archive")
                response.cross_diff = ""
                response.combined_patch = ""
                response.session_id = "test"
            elif isinstance(effect, Complete):
                break
            else:
                response = None

            effect = saga.send(response)
    except StopIteration:
        pass

    # Should end with Complete
    assert any(isinstance(e, Complete) for e in effects_seen)

    # Should have multiple Call effects for different operations
    call_effects = [e for e in effects_seen if isinstance(e, Call)]
    min_expected_operations = 3
    assert len(call_effects) > min_expected_operations  # At minimum: cleanup, archive operations, finalize


# Test error handling


def test_validate_git_repository_saga_handles_none_result():
    """Test handling of None result from git command"""
    saga = validate_git_repository_saga()
    tester = SagaTester(saga)

    # First effect should be Call
    effect = tester.send_value(None)
    assert isinstance(effect, Call)

    # Send None result
    effect = tester.send_value(None)

    # Should Stop with error
    assert isinstance(effect, Stop)


def test_create_claude_directories_saga_handles_failure():
    """Test handling of directory creation failure"""
    saga = create_claude_directories_saga()
    tester = SagaTester(saga)

    # Setup
    effect = tester.send_value(None)  # Select
    state = InitSagaState(claude_git_dir=Path("/path"), shadow_dir=Path("/path/shadow"))
    effect = tester.send_value(state)

    # First directory creation fails
    effect = tester.send_value(False)

    # Should Stop with error
    assert isinstance(effect, Stop)
    assert "Failed to create Claude git directory" in effect.payload


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


def test_apply_uncommitted_changes_saga_no_changes():
    """Test apply_uncommitted_changes_saga when there are no changes"""
    saga = apply_uncommitted_changes_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with empty combined_patch
    state = Mock()
    state.combined_patch = ""
    effect = tester.send_value(state)

    # Should return early (no more effects)
    assert effect is None


if __name__ == "__main__":
    # Run a simple test to verify the module loads
    test_validate_git_repository_saga_success()
    test_setup_paths_saga()
    test_capture_uncommitted_changes_saga()
    print("Basic tests passed!")

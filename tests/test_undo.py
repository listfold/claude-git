# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pytest>=8.0.0",
# "claude-saga==0.1.0"
# ]
# ///

"""
Tests for undo.py sagas
Tests the undo functionality with minimal mocking
"""

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

from claude_git.undo import (
    apply_reverse_patch_saga,
    generate_reverse_patch_saga,
    get_recent_commits_saga,
    revert_shadow_worktree_saga,
    undo_changes_saga,
    validate_reverse_patch_saga,
    validate_undo_arguments_saga,
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


# Test argument validation


def test_validate_undo_arguments_saga_default():
    """Test default argument (empty string)"""
    saga = validate_undo_arguments_saga("")
    tester = SagaTester(saga)

    # Should Put default value of 1
    effect = tester.send_value(None)
    assert isinstance(effect, Put)
    assert effect.payload == {"n_commands": 1}


def test_validate_undo_arguments_saga_valid_number():
    """Test valid number argument"""
    saga = validate_undo_arguments_saga("3")
    tester = SagaTester(saga)

    # Should Put the parsed number
    effect = tester.send_value(None)
    assert isinstance(effect, Put)
    assert effect.payload == {"n_commands": 3}


def test_validate_undo_arguments_saga_invalid_number():
    """Test invalid number argument"""
    saga = validate_undo_arguments_saga("abc")
    tester = SagaTester(saga)

    # Should Stop with error
    effect = tester.send_value(None)
    assert isinstance(effect, Stop)
    assert "Invalid number" in effect.payload


def test_validate_undo_arguments_saga_negative_number():
    """Test negative number argument"""
    saga = validate_undo_arguments_saga("-1")
    tester = SagaTester(saga)

    # Should Stop with error
    effect = tester.send_value(None)
    assert isinstance(effect, Stop)
    assert "positive integer" in effect.payload


def test_validate_undo_arguments_saga_zero():
    """Test zero argument"""
    saga = validate_undo_arguments_saga("0")
    tester = SagaTester(saga)

    # Should Stop with error
    effect = tester.send_value(None)
    assert isinstance(effect, Stop)
    assert "positive integer" in effect.payload


def test_validate_undo_arguments_saga_multiple_args():
    """Test multiple arguments (should fail)"""
    saga = validate_undo_arguments_saga("1 2")
    tester = SagaTester(saga)

    # Should Stop with usage error
    effect = tester.send_value(None)
    assert isinstance(effect, Stop)
    assert "Usage:" in effect.payload


# Test commit retrieval


def test_get_recent_commits_saga_success():
    """Test successful commit retrieval"""
    saga = get_recent_commits_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with shadow_dir and n_commands
    state = Mock()
    state.shadow_dir = "/shadow"
    state.n_commands = 2
    effect = tester.send_value(state)

    # Should change to shadow directory
    assert isinstance(effect, Call)
    assert effect.fn == change_directory_effect
    assert effect.args[0] == "/shadow"

    # Send None for directory change
    effect = tester.send_value(None)

    # Should get recent commits
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "git log --oneline" in effect.args[0]
    assert "-n 2" in effect.args[0]

    # Send successful result with commits
    result = Mock(returncode=0, stdout="abc123 First commit message\ndef456 Second commit message\n")
    effect = tester.send_value(result)

    # Should Put the parsed commits
    assert isinstance(effect, Put)
    assert "commits_to_undo" in effect.payload
    commits = effect.payload["commits_to_undo"]
    expected_commit_count = 2
    assert len(commits) == expected_commit_count
    assert commits[0]["hash"] == "abc123"
    assert commits[0]["message"] == "First commit message"
    assert commits[1]["hash"] == "def456"
    assert commits[1]["message"] == "Second commit message"


def test_get_recent_commits_saga_no_commits():
    """Test when no commits are found"""
    saga = get_recent_commits_saga()
    tester = SagaTester(saga)

    # Setup
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.shadow_dir = "/shadow"
    state.n_commands = 1
    effect = tester.send_value(state)  # State
    effect = tester.send_value(None)  # Directory change

    # Send result with no commits
    result = Mock(returncode=0, stdout="")
    effect = tester.send_value(result)

    # Should Stop with error
    assert isinstance(effect, Stop)
    assert "No commits found" in effect.payload


def test_get_recent_commits_saga_git_failure():
    """Test when git command fails"""
    saga = get_recent_commits_saga()
    tester = SagaTester(saga)

    # Setup
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.shadow_dir = "/shadow"
    state.n_commands = 1
    effect = tester.send_value(state)  # State
    effect = tester.send_value(None)  # Directory change

    # Send failed result
    result = Mock(returncode=1)
    effect = tester.send_value(result)

    # Should Stop with error
    assert isinstance(effect, Stop)
    assert "Failed to retrieve" in effect.payload


# Test reverse patch generation


def test_generate_reverse_patch_saga_success():
    """Test successful reverse patch generation"""
    saga = generate_reverse_patch_saga()
    tester = SagaTester(saga)

    # First effect should be Select
    effect = tester.send_value(None)
    assert isinstance(effect, Select)

    # Send state with commits
    state = Mock()
    state.commits_to_undo = [
        {"hash": "abc123", "message": "First commit"},
        {"hash": "def456", "message": "Second commit"},
    ]
    effect = tester.send_value(state)

    # Should call git diff for forward patch first
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "git diff def456~1..HEAD" in effect.args[0]

    # Send successful result
    result = Mock(returncode=0, stdout="diff --git a/file.txt b/file.txt\n...")
    effect = tester.send_value(result)

    # Should call git diff for reverse patch
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "git diff HEAD..def456~1" in effect.args[0]

    # Send reverse patch result
    reverse_result = Mock(returncode=0, stdout="reverse patch content")
    effect = tester.send_value(reverse_result)

    # Should Put the reverse patch
    assert isinstance(effect, Put)
    assert effect.payload["reverse_patch"] == "reverse patch content"


def test_generate_reverse_patch_saga_no_commits():
    """Test when no commits to process"""
    saga = generate_reverse_patch_saga()
    tester = SagaTester(saga)

    # Send state with no commits
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.commits_to_undo = []
    effect = tester.send_value(state)

    # Should Stop with error
    assert isinstance(effect, Stop)
    assert "No commits available" in effect.payload


# Test patch validation


def test_validate_reverse_patch_saga_success():
    """Test successful patch validation"""
    saga = validate_reverse_patch_saga()
    tester = SagaTester(saga)

    # Setup
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.reverse_patch = "diff --git a/file.txt b/file.txt\n..."
    state.git_root = "/repo"
    effect = tester.send_value(state)

    # Should change to git root
    assert isinstance(effect, Call)
    assert effect.fn == change_directory_effect
    assert effect.args[0] == "/repo"

    # Send None for directory change
    effect = tester.send_value(None)

    # Should write patch file
    assert isinstance(effect, Call)
    assert effect.fn == write_file_effect

    # Send None for write
    effect = tester.send_value(None)

    # Should check patch with git apply --check
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "git apply --check" in effect.args[0]

    # Send successful check result
    result = Mock(returncode=0)
    effect = tester.send_value(result)

    # Should log success
    assert isinstance(effect, Log)
    assert "validation successful" in effect.message


def test_validate_reverse_patch_saga_empty_patch():
    """Test validation with empty patch"""
    saga = validate_reverse_patch_saga()
    tester = SagaTester(saga)

    # Send state with empty patch
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.reverse_patch = ""
    effect = tester.send_value(state)

    # Should return early (no more effects)
    assert effect is None


def test_validate_reverse_patch_saga_conflict():
    """Test patch validation failure"""
    saga = validate_reverse_patch_saga()
    tester = SagaTester(saga)

    # Setup
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.reverse_patch = "diff content"
    state.git_root = "/repo"
    effect = tester.send_value(state)
    effect = tester.send_value(None)  # Directory change
    effect = tester.send_value(None)  # Write patch

    # Send failed check result
    result = Mock(returncode=1)
    effect = tester.send_value(result)

    # Should Stop with conflict error
    assert isinstance(effect, Stop)
    assert "Cannot apply undo patch cleanly" in effect.payload


# Test patch application


def test_apply_reverse_patch_saga_success():
    """Test successful patch application"""
    saga = apply_reverse_patch_saga()
    tester = SagaTester(saga)

    # Setup
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.reverse_patch = "patch content"
    state.git_root = "/repo"
    effect = tester.send_value(state)

    # Should change to git root
    assert isinstance(effect, Call)
    assert effect.fn == change_directory_effect

    # Continue through the saga
    responses = [
        None,  # Directory change
        None,  # Write patch file
        Mock(returncode=0),  # git apply result
        None,  # Log response
    ]

    for response in responses:
        effect = tester.send_value(response)
        if effect is None:
            break


def test_apply_reverse_patch_saga_empty():
    """Test applying empty patch"""
    saga = apply_reverse_patch_saga()
    tester = SagaTester(saga)

    # Send state with empty patch
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.reverse_patch = ""
    effect = tester.send_value(state)

    # Should log and return early
    assert isinstance(effect, Log)
    assert "nothing to undo" in effect.message


# Test shadow worktree reset


def test_revert_shadow_worktree_saga_success():
    """Test successful shadow worktree reset"""
    saga = revert_shadow_worktree_saga()
    tester = SagaTester(saga)

    # Setup
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.shadow_dir = "/shadow"
    state.commits_to_undo = [
        {"hash": "abc123", "message": "First change"},
        {"hash": "def456", "message": "Second change"},
    ]
    effect = tester.send_value(state)

    # Should change to shadow directory
    assert isinstance(effect, Call)
    assert effect.fn == change_directory_effect
    assert effect.args[0] == "/shadow"

    # Send None for directory change
    effect = tester.send_value(None)

    # Should reset shadow worktree
    assert isinstance(effect, Call)
    assert effect.fn == run_command_effect
    assert "git reset --hard def456~1" in effect.args[0]

    # Send successful reset result
    result = Mock(returncode=0)
    effect = tester.send_value(result)

    # Should log success
    assert isinstance(effect, Log)
    assert "Shadow worktree reset back 2 commits" in effect.message


def test_revert_shadow_worktree_saga_no_commits():
    """Test shadow worktree reset with no commits"""
    saga = revert_shadow_worktree_saga()
    tester = SagaTester(saga)

    # Send state with no commits
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.commits_to_undo = []
    effect = tester.send_value(state)

    # Should return early (no more effects)
    assert effect is None


def test_revert_shadow_worktree_saga_reset_failure():
    """Test handling of reset failure"""
    saga = revert_shadow_worktree_saga()
    tester = SagaTester(saga)

    # Setup
    effect = tester.send_value(None)  # Select
    state = Mock()
    state.shadow_dir = "/shadow"
    state.commits_to_undo = [{"hash": "abc123", "message": "Test"}]
    effect = tester.send_value(state)
    effect = tester.send_value(None)  # Directory change

    # Send failed reset result
    result = Mock(returncode=1)
    effect = tester.send_value(result)

    # Should Stop with error
    assert isinstance(effect, Stop)
    assert "Failed to reset shadow worktree state" in effect.payload


# Test composition saga


def test_undo_changes_saga_composition():
    """Test that undo_changes_saga calls all sub-sagas"""
    saga = undo_changes_saga("2")

    # Track which sub-sagas are called by checking effects
    effects_seen = []

    # This saga is a composition, so it will yield from multiple sub-sagas
    try:
        effect = next(saga)
        while True:
            effects_seen.append(effect)

            # Provide appropriate responses based on effect type
            if isinstance(effect, Call):
                if "git log" in str(effect.args):
                    response = Mock(returncode=0, stdout="abc123 First commit\n")
                elif "git diff" in str(effect.args):
                    response = Mock(returncode=0, stdout="diff content")
                elif (
                    "git apply --check" in str(effect.args)
                    or "git apply" in str(effect.args)
                    or "git reset --hard" in str(effect.args)
                    or "git clean" in str(effect.args)
                ):
                    response = Mock(returncode=0)
                elif "git worktree list" in str(effect.args):
                    response = Mock(returncode=0, stdout="/repo/shadow worktree")
                else:
                    response = Mock(returncode=0)
            elif isinstance(effect, Select):
                shadow_path = Mock()
                shadow_path.exists.return_value = True
                shadow_path.__str__ = Mock(return_value="/repo/shadow")
                response = Mock(
                    n_commands=2,
                    git_root="/repo",
                    shadow_dir=shadow_path,
                    commits_to_undo=[{"hash": "abc123", "message": "Test"}],
                    reverse_patch="patch content",
                )
            elif isinstance(effect, Put | Log):
                response = None
            elif isinstance(effect, Complete):
                break
            else:
                response = None

            effect = saga.send(response)
    except StopIteration:
        pass

    # Verify we saw effects from multiple sub-sagas
    call_effects = [e for e in effects_seen if isinstance(e, Call)]
    put_effects = [e for e in effects_seen if isinstance(e, Put)]

    # Should have multiple operations
    min_expected_operations = 4  # At minimum: git log, git diff, git apply, git reset
    assert len(call_effects) > min_expected_operations
    assert len(put_effects) > 0  # At least argument parsing


if __name__ == "__main__":
    # Run some basic tests
    test_validate_undo_arguments_saga_default()
    test_validate_undo_arguments_saga_valid_number()
    test_get_recent_commits_saga_success()
    test_generate_reverse_patch_saga_success()
    test_revert_shadow_worktree_saga_success()
    print("Basic undo saga tests passed!")

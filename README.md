# claude-git

Create a git worktree that tracks claude-code changes without polluting the main repo's git history.

This tool creates a shadow git worktree that tracks all changes made by Claude Code, providing a complete history of AI-assisted modifications without affecting your main repository.

## Features

- Creates a persistent shadow worktree when Claude Code starts a session
- Synchronizes the shadow worktree with your main repository's state  
- Automatically commits Claude's changes to the shadow worktree after each tool use
- Maintains a clean history of AI-assisted changes separate from your main branch

## Installation

### 1. Install the package

```bash
uv pip install claude-git
```

### 2. Configure the Claude Code hooks

Add the following to your `.claude/settings.json` file in your project root:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "claude-git-init"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "claude-git-commit"
          }
        ]
      }
    ]
  }
}
```

Alternatively, you can configure it globally in `~/.claude/settings.json` to apply to all projects.

### 3. How it works

**On session start (SessionStart hook):**
1. Creates a `.claude/git/` directory in your project (if it doesn't exist)
2. Creates or reuses a persistent shadow worktree at `.claude/git/shadow-worktree/`
3. Synchronizes the shadow worktree with your main repository's current state

**After each file modification (PostToolUse hook):**
1. Detects changes made by Claude's tools (Write, Edit, etc.)
2. Applies those changes to the shadow worktree
3. Creates a commit with details about the tool and files modified
4. Your main working directory remains unchanged throughout

## Configuration

The hook uses environment variables provided by Claude Code:
- `CLAUDE_SESSION_ID` - Used in commit messages to identify which session made changes
- `CLAUDE_PROJECT_DIR` - The project directory being worked on

## Directory Structure

After initialization, your project will have:
- `.claude/git/` - Claude git tracking directory
- `.claude/git/shadow-worktree/` - Persistent shadow worktree
- `.claude/settings.json` - Claude Code settings with hook configuration

## Viewing the Shadow Worktree History

To see the commits made by Claude:

```bash
cd .claude/git/shadow-worktree
git log --oneline
```

Each commit message includes:
- The tool that made the change (Write, Edit, etc.)
- The file(s) affected
- The session ID for tracking

## Development

To contribute or modify:

1. Clone the repository
2. Install development dependencies with `uv pip install -e .`
3. Hook scripts are in the `claude_git/` package:
   - `session_start.py` - SessionStart hook
   - `post_tool_use.py` - PostToolUse hook

## License

MIT
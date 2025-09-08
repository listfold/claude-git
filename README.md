# claude-git

A comprehensive git integration for Claude Code that tracks AI-assisted changes in a separate shadow worktree, maintaining a complete audit trail without polluting your main repository history.

## Overview

claude-git provides three integrated components that work together:

1. **Automatic Tracking Hooks** - Track Claude's changes in a shadow worktree
2. **Undo Slash Command** - Reverse Claude's changes when needed  
3. **Complete Audit Trail** - Full history of AI modifications separate from your main branch

## How It Works

### Component Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  SessionStart   │    │   PostToolUse    │    │  Undo Command   │
│      Hook       │    │      Hook        │    │   (/undo)       │
├─────────────────┤    ├──────────────────┤    ├─────────────────┤
│ • Validate git  │    │ • Detect changes │    │ • Analyze N     │
│ • Create shadow │    │ • Apply to shadow│    │   commits       │  
│ • Sync main→    │    │ • Commit changes │    │ • Generate      │
│   shadow        │    │ • Track tools    │    │   reverse patch │
└─────────────────┘    └──────────────────┘    │ • Apply to main │
                                               └─────────────────┘
```

### Workflow

1. **Session Start**: Claude Code starts → SessionStart hook creates/syncs shadow worktree
2. **During Session**: Claude modifies files → PostToolUse hook commits changes to shadow worktree  
3. **Undo (Optional)**: User runs `/undo N` → Reverse last N Claude changes in main repository

### Directory Structure

```
your-project/
├── .claude/
│   ├── settings.json          # Hook and command configuration
│   ├── commands/              # Slash commands (optional)
│   │   ├── undo.py           # Undo command script  
│   │   └── undo.md           # Undo command definition
│   └── git/                  # Claude git tracking (auto-created)
│       ├── shadow-worktree/  # Shadow git worktree
│       └── main-archive/     # Temporary sync files
├── your-source-files...      # Your main project files
└── .gitignore               # Includes .claude/git/ (auto-added)
```

## Installation

### 1. Install the Package

```bash
uv pip install claude-git
```

### 2. Configure Hooks and Commands

Create or update `.claude/settings.json` in your project root (or `~/.claude/settings.json` for global setup):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "claude-git-init",
            "description": "Initialize shadow worktree for tracking Claude changes"
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
            "command": "claude-git-commit",
            "description": "Commit Claude's file changes to shadow worktree"
          }
        ]
      }
    ]
  }
}
```

### 3. Install Undo Command (Optional)

The `/undo` slash command allows you to reverse Claude's changes:

```bash
# For project-specific installation
mkdir -p .claude/commands
cp claude_git/undo.py .claude/commands/
cp .claude/commands/undo.md .claude/commands/
chmod +x .claude/commands/undo.py

# For global installation (available in all projects)  
mkdir -p ~/.claude/commands
cp claude_git/undo.py ~/.claude/commands/
cp .claude/commands/undo.md ~/.claude/commands/
chmod +x ~/.claude/commands/undo.py
```

## Usage

### Automatic Operation

Once configured, claude-git works automatically:

1. **Start Claude Code session** → Shadow worktree created/synchronized
2. **Claude modifies files** → Changes automatically committed to shadow worktree
3. **Continue working** → All Claude changes tracked separately

### Manual Undo Operations

Use the `/undo` slash command to reverse Claude's changes:

```bash
/undo           # Undo last change
/undo 3         # Undo last 3 changes  
/undo 10        # Undo last 10 changes
```

**How undo works:**
1. Analyzes the last N commits in the shadow worktree
2. Generates a reverse patch that undoes those exact changes
3. Validates the patch can be applied cleanly
4. Applies the reverse patch to your main repository (no commit created)
5. Resets the shadow worktree back N commits to reflect the undo

**Why no commits in main repo?** The undo operation applies changes directly to your working directory, giving you full control over whether and how to commit the reverted state. The shadow worktree is reset to maintain consistency with the undone changes.

### Viewing Change History

See all changes made by Claude:

```bash
cd .claude/git/shadow-worktree
git log --oneline --graph
```

Each commit shows:
- Tool used (Write, Edit, MultiEdit, etc.)
- Files modified
- Session ID for tracking
- Timestamp of change

Compare shadow worktree with main repository:

```bash
git diff HEAD .claude/git/shadow-worktree/
```

## Component Dependencies

### Required for Basic Tracking
- ✅ **SessionStart hook** - Creates and syncs shadow worktree  
- ✅ **PostToolUse hook** - Commits Claude's changes
- ✅ **Git repository** - Must be initialized (`git init`)

### Optional for Undo Functionality  
- 🔧 **Undo slash command** - Reverses Claude changes
- 🔧 **Existing commits in shadow worktree** - Generated by PostToolUse hook

### Automatic Dependencies
- 📦 **claude-saga framework** - Effect-based saga pattern implementation
- 📦 **uv or pip** - Python package management
- 📦 **.claude/git/** directory - Auto-created by SessionStart hook  
- 📦 **.gitignore entry** - Auto-added by SessionStart hook

## Environment Variables

claude-git uses these environment variables provided by Claude Code:

- `CLAUDE_SESSION_ID` - Unique session identifier for commit messages
- `CLAUDE_PROJECT_DIR` - Project directory being worked on  
- `ARGUMENTS` - Command arguments for slash commands

## Error Handling

### Common Issues and Solutions

**"Not a git repository"**
```bash
git init  # Initialize git in your project root
```

**"Shadow worktree doesn't exist yet"** (when using `/undo`)
- Start a Claude Code session first (triggers SessionStart hook)
- Make at least one change with Claude (triggers PostToolUse hook)

**"Cannot apply undo patch cleanly"**
- Main repository has been modified since Claude changes
- Manually resolve conflicts or reset repository state

**"No commits found in shadow worktree to undo"**
- No Claude changes have been made yet
- Shadow worktree was recently reset

## Configuration Examples

### Minimal Configuration (Tracking Only)
```json
{
  "hooks": {
    "SessionStart": [{"matcher": "*", "hooks": [{"type": "command", "command": "claude-git-init"}]}],
    "PostToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit", "hooks": [{"type": "command", "command": "claude-git-commit"}]}]
  }
}
```

### Full Configuration (Tracking + Undo)  
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "claude-git-init", 
            "description": "Initialize shadow worktree for tracking Claude changes"
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
            "command": "claude-git-commit",
            "description": "Commit Claude's file changes to shadow worktree"
          }
        ]
      }
    ]
  }
}
```

### Advanced Configuration (Custom Tool Matching)
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "claude-git-init"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [{"type": "command", "command": "claude-git-commit"}]
      },
      {
        "matcher": "Edit|MultiEdit", 
        "hooks": [{"type": "command", "command": "claude-git-commit"}]
      },
      {
        "matcher": "NotebookEdit",
        "hooks": [{"type": "command", "command": "claude-git-commit"}]
      }
    ]
  }
}
```

## Development

### Project Structure

```
claude_git/
├── __init__.py
├── session_start.py      # SessionStart hook implementation
├── post_tool_use.py      # PostToolUse hook implementation  
├── shared_sagas.py       # Shared atomic saga operations
└── undo.py              # Undo slash command implementation

tests/
├── test_session_start.py   # SessionStart hook tests
├── test_shared_sagas.py    # Shared saga tests  
└── test_undo.py           # Undo command tests

.claude/
├── commands/
│   └── undo.md           # Undo slash command definition
└── settings.json         # Development configuration
```

### Contributing

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd claude-git
   ```

2. Install development dependencies:
   ```bash
   uv pip install -e .
   uv pip install -e ".[dev]"
   ```

3. Run tests:
   ```bash
   uv run pytest tests/ -v
   ```

4. Run linting:
   ```bash
   uv run ruff check --fix .
   uv run ruff format .
   ```

### Saga Pattern Architecture

claude-git is built using the saga pattern for reliable effect management:

- **Atomic Sagas**: Single-purpose operations (validate, create, sync)
- **Composition Sagas**: Orchestrate multiple atomic sagas
- **Effect System**: Call, Put, Select, Log, Stop, Complete effects
- **Testability**: Easy to test with minimal mocking

For more details, see the [claude-saga documentation](https://pypi.org/project/claude-saga/).

## License

MIT

---

For more information about Claude Code hooks and slash commands:
- [Claude Code Hooks Documentation](https://docs.anthropic.com/en/docs/claude-code/hooks)  
- [Claude Code Slash Commands Documentation](https://docs.anthropic.com/en/docs/claude-code/slash-commands)
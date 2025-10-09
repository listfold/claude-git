# claude-git

A git integration for Claude Code that tracks changes made by claude code changes in a separate [worktree](https://git-scm.com/docs/git-worktree).

Built using [claude-saga](https://pypi.org/project/claude-saga/) framework for reliable effect-based programming.

## Core Features

Claude-git works by first creating a worktree (a clone of your git repo, with its own git-history).

importantly the main-repo's git history is untouched, while the shadow worktree records each change made by Claude-Code as a commit.

A unique feature is the shadow worktree is created inside the existing project, ensuring the hook is scoped only to the claude-code project and git repo it is running in.
(It is more conventional to create worktrees outside an existing repo to avoid accidentally committing a nested repo, claude-git avoids this problem by including the shadow worktree in the main repo's .gitignore)

With this system in place claude-git enables some powerful features, for example:

1. **Automatic Change Tracking** - Comprehensive & colocated record of AI modifications to a codebase.
2. **Local Tool Integration** - Fast, energy-efficient operations using git instead of LLM calls, this package includes an `/undo` slash command to demonstrate.

## Why Git Integration?

The main reason for creating this package was the feeling of waste when prompting claude-code to "undo" its work, invoking an LLM to do this seems wasteful when git would be far more efficient.

So this package includes an `/undo` slash-command to show the power of local tooling.

## Demo
In this screenshot, we prompt claude to create a file called Foo.md and then use `/undo 1` to revert the last change.

![](claude_git/images/demo_image.png)

## How It Works

### Workflow

1. **Session Start**: Claude Code starts → Git validation + shadow worktree creation/sync
2. **During Session**: Claude modifies files → Changes committed to shadow worktree with metadata  
3. **Local Operations**: User runs local commands (e.g. `/undo N`) → Fast git-based operations
4. **Multi-Agent Ready**: Foundation supports coordination between multiple AI agents

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

### Prerequisites

- **Git repository**: Your project must be a git repository (`git init`)
- **uv**: You must be able to run `uv`.
  
  ```bash
  # Install uv if you haven't already
  curl -LsSf https://astral.sh/uv/install.sh | sh
  
  # Initialize uv in your project (creates .venv)
  uv init --no-workspace
  ```
  
  **Note**: Your project doesn't need to be a Python project, but `uv` must be initialized to run the hooks.

### 1. Install the Package

```bash
uv pip install claude-git
```

### 2. Configure Hooks and Commands

Create or update `.claude/settings.json` in your project root (or `~/.claude/settings.json` for global setup).

**Important**: The hooks use `uv run` to execute the commands within the virtual environment:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "uv run claude-git-init",
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
            "command": "uv run claude-git-commit",
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
# Copy the command files to your project
mkdir -p .claude/commands
cp claude_git/undo.md .claude/commands/
chmod +x claude_git/undo.py
```

## Usage

### Automatic Operation

Once configured, claude-git works automatically:

1. **Start Claude Code session** → Shadow worktree created/synchronized
2. **Claude modifies files** → Changes automatically committed to shadow worktree
3. **Continue working** → All Claude changes tracked separately

### Local Git Operations (Example: Undo)

The `/undo` slash command showcases **local-first tooling**:

```bash
/undo           # Undo last change
/undo 3         # Undo last 3 changes  
/undo 10        # Undo last 10 changes
```

This approach is:

- ⚡ **Faster** - No network roundtrips or LLM processing time
- 🔋 **Energy Efficient** - No electricity used for model inference
- 💰 **Cost Effective** - Saves Claude usage for more important tasks
- 🎯 **Precise** - Exact reversal of changes without interpretation errors, most of the time it's only the last change that is undone.
- 🔧 **Extensible** - Enables building sophisticated local workflows using the power of git
- 
**Local tooling philosophy:** Instead of asking "Claude, please undo your last 3 changes", we use git to analyze what Claude did and locally reverse it.

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
- ✅ **uv environment** - Must be initialized (`uv init --no-workspace`)

### Optional for Undo Functionality  
- 🔧 **Undo slash command** - Reverses Claude changes
- 🔧 **Existing commits in shadow worktree** - Generated by PostToolUse hook

### Automatic Dependencies
- 📦 **claude-saga framework** - Effect-based saga pattern implementation
- 📦 **Python virtual environment** - Created by `uv init`
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
    "SessionStart": [{"matcher": "*", "hooks": [{"type": "command", "command": "uv run claude-git-init"}]}],
    "PostToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit", "hooks": [{"type": "command", "command": "uv run claude-git-commit"}]}]
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
            "command": "uv run claude-git-init", 
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
            "command": "uv run claude-git-commit",
            "description": "Commit Claude's file changes to shadow worktree"
          }
        ]
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

claude-git is built using the [claude-saga](https://pypi.org/project/claude-saga/) framework for reliable effect management:

- **Atomic Sagas**: Single-purpose operations, even side effects are made deterministic
- **Composition Sagas**: Orchestrate multiple atomic sagas
- **Effect System**: Call, Put, Select, Log, Stop, Complete effects
- **Testability**: Easy to test with minimal mocking
- **Reliability**: Transactional semantics for complex operations

The saga pattern ensures that complex git operations (like worktree synchronization) are reliable and easy to reason about, making the foundation solid for building advanced local tooling.

## License

MIT

---

**Related Resources:**
- [claude-saga Framework](https://pypi.org/project/claude-saga/) - Effect-based programming for reliable operations
- [Claude Code Hooks Documentation](https://docs.anthropic.com/en/docs/claude-code/hooks) - Hook integration guide
- [Claude Code Slash Commands Documentation](https://docs.anthropic.com/en/docs/claude-code/slash-commands) - Custom command creation

**Get Started**: The git integration provides a foundation for building sophisticated local AI development tools. Start with the basic tracking hooks, explore the `/undo` command, then build your own local operations on top of the git foundation.

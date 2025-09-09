# claude-git

A git integration for Claude Code that tracks AI-agent changes in a separate shadow worktree.

Built using the [claude-saga](https://pypi.org/project/claude-saga/) framework for reliable effect-based programming.

## Core Features

claude-git works by creating a worktree (essentially a clone of your git repo, with its own git-history).

Importantly the main-repo's git history is untouched, while the shadow worktree records each change made by Claude-Code as a commit.

With this system in place claude-git enables some nifty features:

1. **Automatic Change Tracking** - Comprehensive record of AI modifications.
2. **Local Tool Integration** - Fast, energy-efficient operations using git instead of LLM calls, this package includes an `/undo` slash command to demonstrate.
4. **Dataset Generation** - Option to Export/Share AI-assisted changes for training data and analysis

## Why Git Integration?

The main reason for creating this package was the feeling of waste when prompting claude-code to "undo" its work, this seems wasteful when normally git would be fine for this.

So this package includes an `/undo` slash-command to show the power of local tooling.

This approach is:

- ⚡ **Faster** - No network roundtrips or LLM processing time
- 🔋 **Energy Efficient** - No electricity used for model inference  
- 💰 **Cost Effective** - Saves Claude usage for more important tasks
- 🎯 **Precise** - Exact reversal of changes without interpretation errors, most of the time it's only the last change that is undone.
- 🔧 **Extensible** - Enables building sophisticated local workflows using the power of git

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

### Local Git Operations (Example: Undo)

The `/undo` slash command showcases **local-first tooling** - fast git operations instead of slow LLM calls:

```bash
/undo           # Undo last change
/undo 3         # Undo last 3 changes  
/undo 10        # Undo last 10 changes
```

**Local git workflow:**
1. **Analyze** shadow worktree commits (local git log)
2. **Generate** reverse patch (local git diff) 
3. **Validate** patch compatibility (local git apply --check)
4. **Apply** changes to working directory (local git apply)
5. **Sync** shadow worktree state (local git reset)

**Benefits over LLM-based undo:**
- ⚡ **~100x faster** - No network/inference latency
- 🔋 **Zero energy** - No GPU cycles for model inference
- 💰 **Cost-free** - Preserves Claude usage for creative tasks  
- 🎯 **Bit-perfect** - Exact reversal without LLM interpretation
- 🔒 **Offline-capable** - Works without internet connection

**Local tooling philosophy:** Instead of asking "Claude, please undo your last 3 changes", we use git to analyze what Claude did and locally reverse it. This pattern can be extended to many other operations.

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

## Future Possibilities

The git integration foundation enables many advanced workflows:

### Multi-Agent Coordination
```bash
# Agent 1 works on feature A
claude-code-agent-1 --task="implement authentication"

# Agent 2 works on feature B  
claude-code-agent-2 --task="add user profiles"

# Merge agent changes with conflict resolution
git merge shadow-worktree-agent-1 shadow-worktree-agent-2
```

### Training Dataset Generation
```bash
# Export high-quality AI coding examples
git log --format='%H %s' .claude/git/shadow-worktree/ | \
  claude-export-dataset --output=ai-coding-examples.jsonl

# Create before/after training pairs
claude-generate-training-pairs --commits=last-100 --format=instruction-following
```

### Advanced Change Analysis
```bash
# Analyze AI coding patterns
git log --stat .claude/git/shadow-worktree/ | claude-analyze-patterns

# Generate development insights  
claude-git-insights --timeframe=last-month --breakdown=by-tool
```

### Collaborative Review Workflows
```bash
# Share AI changes for team review
git format-patch main..shadow-worktree | claude-create-review-pr

# Cherry-pick approved AI changes
git cherry-pick shadow-worktree~3..shadow-worktree~1
```

These examples show how the git foundation can power sophisticated AI development workflows that would be impossible with traditional prompt-based approaches.

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

claude-git is built using the [claude-saga](https://pypi.org/project/claude-saga/) framework for reliable effect management:

- **Atomic Sagas**: Single-purpose operations (validate, create, sync)
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
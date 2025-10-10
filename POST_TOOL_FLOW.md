# Post Tool Use Flow Documentation

This document describes how changes from the main worktree are detected and synchronized to the shadow worktree after Claude modifies files.

## Overview

The claude-git system maintains a shadow worktree that mirrors the main repository. This shadow worktree creates a complete history of all changes made during a Claude session, including both committed and uncommitted changes.

### Two-Commit Architecture

The system uses two different synchronization strategies depending on when they run:

1. **SessionStart** (`sync_worktrees_saga`): Full synchronization with two separate commits
2. **PostToolUse** (`detect_and_sync_changes_saga`): Incremental detection with single commit

## SessionStart Flow (`sync_worktrees_saga`)

**When**: At the start of each Claude session
**Purpose**: Establish complete baseline synchronization
**Location**: `claude_git/shared_sagas.py:352-374`

### Steps

1. **Create archive of main repo HEAD**
   - Uses `git archive HEAD` to get clean snapshot of tracked files
   - Excludes `.git`, `.gitignore`, and other untracked files

2. **Capture uncommitted changes**
   - Gets both staged and unstaged changes from main worktree
   - Stores combined patch for later use

3. **Generate cross-repo diff**
   - Compares archive (clean HEAD) vs shadow worktree
   - Uses `git diff --no-index` for cross-repo comparison

4. **Reset shadow worktree**
   - `git reset --hard HEAD` and `git clean -fd`
   - Ensures clean state before applying changes

5. **Apply and commit sync changes**
   - Applies the cross-repo diff to shadow
   - Creates first commit: "Sync with main repo state (session {id})"
   - This captures all committed changes from main repo

6. **Apply and commit uncommitted changes**
   - Applies the captured uncommitted patch to shadow
   - Creates second commit: "Uncommitted changes from main worktree at sync time (session {id})"
   - This preserves the distinction between committed and uncommitted work

### Why Two Commits?

Separating committed and uncommitted changes provides clear history:
- First commit shows the "official" repo state
- Second commit shows work-in-progress at session start
- Makes it easy to see what was committed vs uncommitted

## PostToolUse Flow (`detect_and_sync_changes_saga`)

**When**: After Claude modifies files (Write, Edit, etc.)
**Purpose**: Incrementally capture changes as they happen
**Location**: `claude_git/shared_sagas.py:426-470`

### Steps

1. **Get shadow worktree HEAD**
   - Retrieves current HEAD commit hash from shadow worktree
   - This is the baseline for comparison

2. **Generate diff from main to shadow**
   - Uses native git diff: `git diff <shadow-head>` from main worktree
   - Captures **all** changes (committed + uncommitted) in main vs shadow
   - Respects `.gitignore` and git's file tracking automatically
   - More reliable than archive-based approach

3. **Check for differences**
   - If no diff: Log and exit (nothing to sync)
   - If diff exists: Proceed to sync

4. **Reset shadow worktree**
   - `git reset --hard HEAD` and `git clean -fd`
   - **Why reset?** Defensive programming - ensures the shadow is in a known clean state
   - The diff assumes starting point is a clean checkout of shadow HEAD
   - Without reset, previous partial applies or rejected hunks could cause conflicts

5. **Apply diff to shadow**
   - Changes to shadow worktree directory
   - Applies the patch: `git apply --reject --ignore-whitespace`
   - Stages all changes: `git add -A`

6. **Commit with custom message**
   - Uses `commit_message_builder` if provided (e.g., "Edit: path/to/file.py (session: xyz)")
   - Otherwise uses default: "Changes detected (session {id})"
   - Creates single commit containing all changes

### Why Single Commit?

For incremental updates during a session:
- Changes are typically small and focused (one tool use at a time)
- Commit message identifies the specific tool and file modified
- Simpler than splitting into committed/uncommitted
- The entire current state (committed + uncommitted) represents the "truth"

## Why Reset Shadow Worktree?

Both flows reset the shadow worktree before applying changes. This is defensive programming:

### The Problem Without Reset

If shadow worktree has any uncommitted changes from:
- Previous failed patch application
- Rejected hunks saved as `.rej` files
- Manual intervention or debugging
- File system issues

Then applying a new patch could:
- Fail due to conflicts
- Apply incorrectly
- Create unexpected merge states

### The Solution

Resetting ensures:
- Shadow working tree = clean checkout of shadow HEAD
- This matches the diff's assumed starting point
- Patches apply cleanly and predictably
- No leftover state from previous operations

### When Is It Safe?

We always commit successfully before the next sync, so shadow **should** always be clean. The reset is insurance against:
- Bugs in the sync process
- Interrupted operations
- External modifications to shadow worktree

## Key Differences Summary

| Aspect | sync_worktrees_saga | detect_and_sync_changes_saga |
|--------|---------------------|------------------------------|
| **When** | SessionStart | PostToolUse |
| **Diff Method** | Archive + `git diff --no-index` | Native `git diff <commit>` |
| **Commits Created** | 2 (committed + uncommitted) | 1 (all changes together) |
| **Reset Shadow** | Yes | Yes |
| **Use Case** | Initial sync, complete baseline | Incremental updates |
| **Commit Message** | Fixed format | Customizable via builder |

## Archived Flow (No Longer Used)

The original `detect_and_sync_changes_saga` used an archive-based approach:

1. Create archive of main HEAD
2. Apply uncommitted changes to archive
3. Diff archive vs shadow
4. Apply directly to shadow (no reset)

**Problems:**
- Patches might apply differently than actual file state after commit
- No reset meant potential accumulation of partial states
- `git diff --no-index` between non-git dir and git worktree was less reliable

**Solution:**
- Use native git diff which respects tracking and gitignore
- Always reset shadow for predictable state
- Simpler and more reliable

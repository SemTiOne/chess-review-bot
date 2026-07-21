# chess-review-bot

chess.com's Game Review vocabulary — Brilliant!!, Great!, Best, Excellent, Good,
Book, Inaccuracy?!, Mistake?, Blunder??, Miss — pointed at a git diff instead of
a chess move.

```
chess-review-bot  ──────────────────────────────────────────────
  Diff:        HEAD~1..HEAD  ·  3 files  ·  +142 / -38 lines
  Accuracy:     71/100
──────────────────────────────────────────────────────────────

  src/auth/session.py                                  Blunder??
    → touches critical path with no matching test changes
    → "chess-review-bot says: hanging your queen in the auth module
       without a single test is how production incidents are born."

  src/utils/formatting.py                              Book
    → dependency/formatting-only change, nothing to see here

  tests/test_session.py                                Great!
    → tests added alongside a meaningful source change

──────────────────────────────────────────────────────────────
Result: FAIL (1 Blunder)  ·  Exit code: 1
```

Category is **never** LLM-decided. Deterministic signals (size, test-file
overlap, critical-path membership, force-push, revert, commit message quality,
credential leakage) run through a fixed rule table. Delete `commentary.py`;
classification doesn't change.

LLM's only job (optional): phrase an already-decided category in one dry
sentence. Same lesson as `position-evaluator`: LLMs are bad at inventing a
severity scale, good at picking from a fixed one.

## Install

```bash
pip install chess-review-bot
```

Zero required runtime deps. Commentary is an opt-in extra:

```bash
pip install "chess-review-bot[commentary]"
```

No extra / no Gemini key: still classifies and reports correctly, just prints
the deterministic reason instead of a generated sentence.

## CLI usage

```bash
chessreview                       # HEAD~1..HEAD in current repo
chessreview HEAD~5..HEAD          # wider range
chessreview my-change.diff        # saved diff file
git diff | chessreview -          # stdin
```

| Option | Description |
|---|---|
| `--critical PATTERN` | Critical-path glob. Repeatable, adds to defaults. |
| `--only-critical PATTERN` | Replace default critical-path globs. Repeatable. |
| `--large-threshold N` | Lines changed = "large". Default 400. |
| `--moderate-threshold N` | Lines changed = "moderate". Default 100. |
| `--force-pushed` | Flag as force-pushed (local testing only). |
| `--revert` | Flag as a revert. |
| `--enable-commentary` | Gemini one-line commentary. Requires a key. |
| `--gemini-key TEXT` | Or set `GEMINI_API_KEY`. |
| `--format [text\|json\|markdown]` | Default: text. |
| `--summary` | One-line output. |
| `--debug` | Show per-file signals. |

Exit codes: `0` clean, `1` Blunder found, `2` tool error.

## GitHub Action

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0   # needed for force-push ancestry check

- uses: SemTiOne/chess-review-bot@v1
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    gemini-key: ${{ secrets.GEMINI_API_KEY }}   # optional
    fail-on-blunder: 'true'
```

| Input | Description | Default |
|---|---|---|
| `github-token` | `pull-requests: write` + `contents: read`. | required |
| `gemini-key` | Optional, enables commentary. | `''` |
| `critical-paths` | Newline-separated globs. | built-in defaults |
| `large-threshold` | Lines changed = "large". | `400` |
| `moderate-threshold` | Lines changed = "moderate". | `100` |
| `fail-on-blunder` | Fail check on any Blunder??. | `true` |
| `post-comment` | Post/update the PR review card. | `true` |

One comment per PR, updated on every push (idempotency marker
`<!-- chess-review-bot-managed-comment -->`) — never a second comment.

```markdown
### ♟️ chess-review-bot — PR Game Review

**Accuracy: 71/100** · 3 files · +142/-38 · 1 Blunder??

| File | Category | Why |
|---|---|---|
| `src/auth/session.py` | Blunder?? | critical path, no tests, no description |
| `src/utils/formatting.py` | Book | dependency/formatting-only change |
| `tests/test_session.py` | Great! | tests added alongside a real change |
```

## What this deliberately does NOT do

- **Never scores or names a person.** Diffs and commits only, never authors.
  An earlier concept scored people ("most toxic collaborator") — rejected on
  purpose: a screenshotted report naming someone is an HR incident, and no
  manager installs a tool that can start a fight on their team.
- **Doesn't find bugs.** Severity *communication*, not a correctness/security
  scanner. Pair with your existing linters/CI.
- **Commit-message quality is a blunt denylist heuristic**, not sentiment
  analysis.
- **Force-push detection is Action-mode only.** Compares `synchronize` event's
  `before`/`after` SHAs via `git merge-base --is-ancestor` (needs
  `fetch-depth: 0`). CLI can't infer this from reflog — pass `--force-pushed`
  to test it locally. (Earlier draft assumed a `forced` payload field; that
  field only exists on `push` events, not `pull_request`. See `CHANGELOG.md`.)

## Exit codes

| Code | Meaning |
|---|---|
| `0` | No file classified `Blunder??` |
| `1` | At least one `Blunder??` |
| `2` | Tool error (bad input, invalid config, git failure) |

## Companion tools

- [`position-evaluator`](https://github.com/SemTiOne/position-evaluator) — the
  original: chess terminology for personal decisions, not code.
- [`env-auditor`](https://github.com/SemTiOne/env-auditor) — finds undocumented, stale, and missing environment variables across JS, Python, Go, Ruby, Shell, and Docker.

## Releasing

Bump `version` in `pyproject.toml` **and** `CHESSREVIEW_VERSION` in `action/action.yml` (has to match; `github.action_ref` is not reliable inside composite actions, so this can't be derived automatically, has to be kept in sync by hand every release). Commit, then:

```bash
git tag v0.1.1
git push --tags
```

`release.yml` runs tests, checks the tag matches `pyproject.toml`, builds, and publishes to PyPI via Trusted Publishing (OIDC). One-time setup on PyPI: add SemTiOne/chess-review-bot as a pending publisher for workflow `release.yml`, environment `pypi`, before the first tag push.

**Floating major-version tag:** consumers reference `@v1`, not `@v0.1.1` directly; same convention as `actions/checkout@v4`. After tagging an exact version, move the floating tag to match:

```bash
git tag -fa v1 -m "v1"
git push origin v1 --force
```

Only do this once the exact-version tag (`v0.1.1`) is already pushed and
`release.yml` has passed — don't move `v1` to a commit that hasn't been
verified yet.

## Trademark note

chess-review-bot is not affiliated with, endorsed by, or sponsored by
Chess.com. "Chess.com" is a trademark of Chess.com, LLC. The category names
used here are inspired by chess.com's Game Review feature, applied to git
diffs instead of chess moves.

## License

MIT

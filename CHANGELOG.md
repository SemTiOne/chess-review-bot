# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/) loosely.

## [Unreleased]

### Fixed

- `requirements.txt` (and `requirements-*.txt` variants) weren't
  recognized as a dependency manifest at all; a version-only bump was
  scored like any other change instead of routine `Book`. Found via two
  real repos with 9+ such files between them. `package.json`/
  `pyproject.toml`'s version-line pattern doesn't match pip's `==`/`>=`/
  `~=` operators either, so this needed its own pattern, not just a name
  added to an existing list.

## [0.1.2]

### Fixed

- Credential detection flagged safe env/config lookups
  (`os.environ["X"]`, `config["X"]`, `os.getenv(...)`, `settings.X`) as
  leaked secrets, purely because they matched `keyword = <anything>`.
  Found by running the detector against real tutorial repos that load
  API keys this way (a very common, safe pattern). A hardcoded literal
  value is still flagged exactly as before.

## [0.1.1]

### Fixed

- `action.yml` referenced `${{ github.action_path }}/action/entrypoint.py`
  -- `github.action_path` already points at the directory containing
  `action.yml`, so this doubled the path segment and every Action run
  failed with exit code 2 before classifying anything. Found immediately
  via dogfooding on this repo's own PRs.
- `Great!` required only "some test file changed somewhere in the PR,"
  not a test file matching *this* file. A PR touching an unrelated file
  plus a totally unrelated test made the unrelated file inherit "Great!"
  it had nothing to do with. Now requires a same-named test file
  (`foo.py` <-> `test_foo.py`) changed in the same PR.
- The Action's `critical-paths` input replaced the built-in defaults
  entirely instead of adding to them, unlike the CLI's `--critical`
  (additive) vs `--only-critical` (replace) split. Found while wiring up
  `env-auditor`/`standup-bot`. Added a separate `only-critical-paths`
  input for the replace case; `critical-paths` is additive now.

## [0.1.0]

### Added

- CLI (`chessreview`): parses a diff, classifies via fixed chess.com-style
  rule table, optional Gemini commentary, text/JSON/Markdown output.
- GitHub Action (composite): runs on `pull_request`, posts/updates one
  idempotent PR comment, force-push-aware via before/after ancestry.
- `docs/adr/0001-deterministic-classification.md`.

### Fixed

- Force-push detection assumed a `forced` field on the `pull_request`
  `synchronize` payload. It doesn't exist there (only on `push`). Detection
  never fired before this fix. Now uses `before`/`after` SHA ancestry via
  `git merge-base --is-ancestor`.
- `git` subprocess calls no longer inherit `GITHUB_TOKEN`/`GEMINI_API_KEY`
  from the parent environment.
- PR-comment lookup now paginates instead of only checking the first 100
  comments, avoiding duplicate comments on busy PRs.
- GitHub API calls retry once on `429`/`5xx` with backoff (`Retry-After`
  honored) instead of failing immediately on a transient blip.
- Credential regex never matched `Bearer <token>` (HTTP header convention
  is space-separated, not `=`/`:`-separated) -- a leaked Bearer token
  would have passed through unredacted. Added a dedicated pattern for it.

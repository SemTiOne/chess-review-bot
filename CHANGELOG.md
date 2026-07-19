# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/) loosely. No release
yet; everything below is Unreleased. Entries move out only once a version
is actually tagged and published.

## [Unreleased]

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

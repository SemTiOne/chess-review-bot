# ADR 0001: Classification is deterministic; the LLM only phrases it

## Status

Accepted.

## Context

Two ways to assign a category to a diff: (1) hand the diff to an LLM and ask
it to pick, or (2) compute deterministic signals and use a fixed rule table,
LLM optional and only for phrasing. `position-evaluator` tried something like
(1) first (LLM-generated confidence score) and hit a calibration problem —
the model's own sense of "how confident" drifted run to run. Fix there:
categorical `confidence_bucket` + severity from a lookup table, never
model-invented.

## Decision

Apply that lesson from the start. `classifier.py` is a pure function of
`FileSignals`/`PRSignals`. `commentary.py` is optional and only phrases a
`Category` already decided — it cannot change one.

## Consequences

- Every `test_classifier.py` test runs with `commentary.py` deleted from the
  import graph.
- Full functionality (classification, exit codes, JSON/Markdown) with zero
  LLM calls and no API key. Commentary is polish, never load-bearing.
- Trade-off: only as nuanced as the signals it's given. Won't catch subtle
  judgment calls an LLM reading full context might. Intentional ceiling, not
  an oversight — the alternative is the calibration failure this avoids.

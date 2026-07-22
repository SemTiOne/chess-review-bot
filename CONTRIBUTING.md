# Contributing

## Setup

```bash
git clone https://github.com/SemTiOne/chess-review-bot.git
cd chess-review-bot
pip install -e ".[dev]"
```

## Before opening a PR

```bash
pytest --cov=chessreview --cov-fail-under=85
```

## The one rule

`classifier.py`'s rule table decides the category. Nothing else does.
If you're adding a new signal, it goes in `signals.py` first, then a rule
in `classifier.py` references it; never the other way around, and never
inside `commentary.py`. See `docs/adr/0001-deterministic-classification.md`
for why.

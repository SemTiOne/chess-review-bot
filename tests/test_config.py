from __future__ import annotations

import pytest

from chessreview.config import Config, DEFAULT_BLOCKED_PLACEHOLDER_WORDS


def test_default_blocked_words_are_set():
    assert len(DEFAULT_BLOCKED_PLACEHOLDER_WORDS) > 0


def test_config_valid_defaults():
    config = Config()
    assert config.blocked_placeholder_words == DEFAULT_BLOCKED_PLACEHOLDER_WORDS


def test_config_custom_blocked_words():
    config = Config(blocked_placeholder_words=("foo", "bar"))
    assert config.blocked_placeholder_words == ("foo", "bar")


def test_config_negative_medium_threshold_raises():
    with pytest.raises(ValueError, match="thresholds must be non-negative"):
        Config(moderate_threshold=-1)


def test_config_negative_large_threshold_raises():
    with pytest.raises(ValueError, match="thresholds must be non-negative"):
        Config(large_threshold=-5)


def test_config_moderate_exceeds_large_raises():
    with pytest.raises(ValueError, match="moderate_threshold.*large_threshold"):
        Config(moderate_threshold=200, large_threshold=100)


def test_config_negative_max_commentary_calls_raises():
    with pytest.raises(
        ValueError, match="max_commentary_calls_per_run must be non-negative"
    ):
        Config(max_commentary_calls_per_run=-1)

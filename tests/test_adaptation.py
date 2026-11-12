"""自适应判定与记录。"""

from __future__ import annotations

import random

from app.core.adaptation import Params, effective, push, sanitize, should_skip, skip_probability
from app.models import Adaptation

PARAMS = Params(window=100, min_plays=10, base=0.95, skip_seconds=30)


def test_no_records_means_no_skip():
    assert skip_probability("", PARAMS) == 0.0


def test_under_min_plays_never_skips():
    assert skip_probability("1" * 10, PARAMS) == 0.0


def test_formula_matches_spec():
    records = "1" * 50 + "0" * 50

    assert skip_probability(records, PARAMS) == 0.95 * 50 / 100


def test_one_more_than_min_plays_applies_formula():
    assert skip_probability("1" * 11, PARAMS) == 0.95


def test_base_is_capped():
    params = Params(window=100, min_plays=0, base=1.5, skip_seconds=30)

    assert skip_probability("1" * 100, params) == 0.99


def test_zero_base_never_skips():
    params = Params(window=100, min_plays=0, base=0.0, skip_seconds=30)

    assert skip_probability("1" * 100, params) == 0.0
    assert should_skip("1" * 100, params, random.Random(1)) is False


def test_should_skip_follows_probability():
    records = "1" * 50 + "0" * 50

    assert should_skip(records, PARAMS, random.Random(1)) is True
    assert should_skip(records, PARAMS, random.Random(0)) is False


def test_push_appends_and_trims_from_front():
    records = "0" * 100

    updated = push(records, True, 100)

    assert len(updated) == 100
    assert updated.endswith("1")
    assert updated == "0" * 99 + "1"


def test_push_keeps_short_history():
    assert push("01", False, 100) == "010"


def test_sanitize_drops_noise():
    assert sanitize("0x1\n1") == "011"


def test_effective_falls_back_to_defaults():
    adaptation = Adaptation(enabled=True, window=None, min_plays=3, base=None, skip_seconds=12)

    params = effective(adaptation, PARAMS)

    assert params.window == 100
    assert params.min_plays == 3
    assert params.base == 0.95
    assert params.skip_seconds == 12

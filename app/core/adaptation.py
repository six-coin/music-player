"""自适应判定。

规则：某首歌在某个歌单里的最近 N 次播放，记录成 0/1 串。记录条数不超过
``min_plays`` 时永不跳过；超过之后，跳过概率是「基数 × 历史跳过比例」。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.models import (
    BASE_MAX,
    BASE_MIN,
    SKIP_SECONDS_MAX,
    SKIP_SECONDS_MIN,
    WINDOW_MAX,
    WINDOW_MIN,
    Adaptation,
)

DEFAULT_WINDOW = 100
DEFAULT_MIN_PLAYS = 10
DEFAULT_BASE = 0.95
DEFAULT_SKIP_SECONDS = 30


@dataclass(frozen=True, slots=True)
class Params:
    window: int
    min_plays: int
    base: float
    skip_seconds: int


def _as_int(value: object, fallback: int, low: int, high: int) -> int:
    """配置文件是人手写的，数字也可能是字符串，读不出来就回退默认值。"""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return fallback
    try:
        number = int(float(value)) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return fallback
    return min(high, max(low, number))


def _as_float(value: object, fallback: float, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number:  # NaN
        return fallback
    return min(high, max(low, number))


def params_from_dict(data: object) -> Params:
    """把 ``common.adaptation`` 那一段读成参数；manager 与 simple 共用这一份。"""
    raw = data if isinstance(data, dict) else {}
    window = _as_int(raw.get("window"), DEFAULT_WINDOW, WINDOW_MIN, WINDOW_MAX)
    return Params(
        window=window,
        min_plays=_as_int(raw.get("min_plays"), DEFAULT_MIN_PLAYS, 0, window),
        base=_as_float(raw.get("base"), DEFAULT_BASE, BASE_MIN, BASE_MAX),
        skip_seconds=_as_int(
            raw.get("skip_seconds"), DEFAULT_SKIP_SECONDS, SKIP_SECONDS_MIN, SKIP_SECONDS_MAX
        ),
    )


def effective(adaptation: Adaptation, defaults: Params) -> Params:
    """歌单没覆盖的字段回落到全局默认值。"""
    return Params(
        window=adaptation.window if adaptation.window is not None else defaults.window,
        min_plays=adaptation.min_plays if adaptation.min_plays is not None else defaults.min_plays,
        base=adaptation.base if adaptation.base is not None else defaults.base,
        skip_seconds=(
            adaptation.skip_seconds
            if adaptation.skip_seconds is not None
            else defaults.skip_seconds
        ),
    )


def sanitize(records: str) -> str:
    """只保留 0/1，防止手改文件带进非法字符。"""
    return "".join(char for char in records if char in "01")


def base_percent(base: float) -> int:
    """存储用的比例 → 界面上的整数百分比（1–99）。"""
    return min(99, max(1, round(float(base) * 100)))


def base_from_percent(percent: float) -> float:
    """界面上的整数百分比 → 存储用的比例；越界夹取，不做隐式取整。"""
    return min(BASE_MAX, max(BASE_MIN, float(percent) / 100.0))


def skip_probability(records: str, params: Params) -> float:
    total = len(records)
    if total <= params.min_plays:
        return 0.0
    skips = records.count("1")
    return min(params.base, BASE_MAX) * skips / total


def should_skip(records: str, params: Params, rng: random.Random | None = None) -> bool:
    probability = skip_probability(records, params)
    if probability <= 0.0:
        return False
    return (rng or random).random() < probability


def push(records: str, skipped: bool, window: int) -> str:
    """把这一次的结果压进环形缓冲区，超出窗口时从头部截断。"""
    updated = sanitize(records) + ("1" if skipped else "0")
    if window > 0 and len(updated) > window:
        updated = updated[-window:]
    return updated


def is_full_play(played_ms: int, skip_seconds: int, *, natural: bool) -> bool:
    """这一次播放够不够得上「播了一次」。

    自然播完永远算；手动切歌要看播放秒数有没有到阈值。总播放次数用它来判定，
    但阈值来自「当时正在播放的环境」：在歌单里用那个歌单的阈值，单曲循环用
    全局默认阈值。
    """
    if natural:
        return True
    return max(0, int(played_ms)) >= max(0, int(skip_seconds)) * 1000


def skip_rate(records: str) -> float:
    total = len(records)
    return records.count("1") / total if total else 0.0

"""T14: configurable per-call timeouts with a shared wall-clock budget for one retry."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 150.0
MIN_TIMEOUT_SEC = 30.0
MAX_TIMEOUT_SEC = 300.0

T = TypeVar("T")


def env_timeout_sec(name: str, default: float = DEFAULT_TIMEOUT_SEC) -> float:
    """Read a timeout from env; invalid -> default, out of range -> clamped (30–300 s)."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        logger.warning("%s=%r is not a number, using %.0fs", name, raw, default)
        return default
    if value < MIN_TIMEOUT_SEC or value > MAX_TIMEOUT_SEC:
        clamped = min(max(value, MIN_TIMEOUT_SEC), MAX_TIMEOUT_SEC)
        logger.warning(
            "%s=%r out of range [%.0f, %.0f], clamped to %.0fs",
            name, raw, MIN_TIMEOUT_SEC, MAX_TIMEOUT_SEC, clamped,
        )
        return clamped
    return value


class RetryBudget:
    """One retry sharing a total budget of ``2 × per_attempt_sec``.

    Each attempt is capped at ``per_attempt_sec`` and at whatever time is left, so a
    slow first attempt cannot extend the overall wait beyond the shared budget.
    """

    def __init__(self, per_attempt_sec: float) -> None:
        self.per_attempt_sec = per_attempt_sec
        self.total_sec = per_attempt_sec * 2
        self._deadline = time.monotonic() + self.total_sec

    def remaining(self) -> float:
        return max(0.0, self._deadline - time.monotonic())

    def next_timeout(self) -> float:
        return min(self.per_attempt_sec, self.remaining())

    def exhausted(self) -> bool:
        return self.remaining() <= 0.0


async def call_with_budget(
    factory: Callable[[float], Awaitable[T]], budget: RetryBudget
) -> T:
    """Run one attempt with its remaining share of the shared budget."""
    timeout = budget.next_timeout()
    if timeout <= 0:
        raise TimeoutError("retry budget exhausted")
    return await asyncio.wait_for(factory(timeout), timeout=timeout)

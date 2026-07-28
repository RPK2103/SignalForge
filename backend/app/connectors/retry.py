"""Bounded retry / backoff with injectable clock and sleeper."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.connectors.errors import ConnectorError
from app.domain.enterprise_enums import ConnectorErrorCategory


class Clock(Protocol):
    def now(self) -> datetime: ...


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class RandomSource(Protocol):
    def random(self) -> float: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SystemSleeper:
    def sleep(self, seconds: float) -> None:
        import time

        time.sleep(max(0.0, seconds))


class SystemRandom:
    def random(self) -> float:
        return random.random()


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)


class FakeSleeper:
    def __init__(self, clock: FakeClock | None = None) -> None:
        self.sleeps: list[float] = []
        self._clock = clock

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if self._clock is not None:
            self._clock.advance(seconds)


class FakeRandom:
    def __init__(self, values: list[float] | None = None) -> None:
        self._values = list(values or [0.5])
        self._i = 0

    def random(self) -> float:
        value = self._values[self._i % len(self._values)]
        self._i += 1
        return value


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0
    jitter_ratio: float = 0.1
    max_rate_limit_wait_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("invalid delay bounds")
        if not 0.0 <= self.jitter_ratio <= 1.0:
            raise ValueError("jitter_ratio must be in [0, 1]")


@dataclass(slots=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: float = 0.0
    reason: str = ""


class RetryExecutor:
    """Compute bounded backoff; never loops unboundedly."""

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        *,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
        random_source: RandomSource | None = None,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self.clock = clock or SystemClock()
        self.sleeper = sleeper or SystemSleeper()
        self.random_source = random_source or SystemRandom()

    def compute_delay(
        self,
        attempt: int,
        *,
        retry_after_seconds: float | None = None,
        reset_at: datetime | None = None,
    ) -> float:
        if retry_after_seconds is not None and retry_after_seconds >= 0:
            delay = min(retry_after_seconds, self.policy.max_rate_limit_wait_seconds)
        elif reset_at is not None:
            wait = (reset_at - self.clock.now()).total_seconds()
            delay = min(max(wait, 0.0), self.policy.max_rate_limit_wait_seconds)
        else:
            exp = self.policy.base_delay_seconds * (2 ** max(0, attempt - 1))
            delay = min(exp, self.policy.max_delay_seconds)
        jitter = delay * self.policy.jitter_ratio * self.random_source.random()
        return min(delay + jitter, self.policy.max_delay_seconds)

    def decide(
        self,
        error: ConnectorError,
        attempt: int,
        *,
        retry_after_seconds: float | None = None,
        reset_at: datetime | None = None,
    ) -> RetryDecision:
        if attempt >= self.policy.max_attempts:
            return RetryDecision(False, reason="max_attempts_exceeded")
        if not error.retryable:
            return RetryDecision(False, reason="non_retryable")
        delay = self.compute_delay(
            attempt, retry_after_seconds=retry_after_seconds, reset_at=reset_at
        )
        if (
            error.category == ConnectorErrorCategory.RATE_LIMITED
            and retry_after_seconds is not None
            and retry_after_seconds > self.policy.max_rate_limit_wait_seconds
        ):
            return RetryDecision(False, delay, reason="rate_limit_wait_exceeds_maximum")
        if (
            error.category == ConnectorErrorCategory.RATE_LIMITED
            and reset_at is not None
            and (reset_at - self.clock.now()).total_seconds()
            > self.policy.max_rate_limit_wait_seconds
        ):
            return RetryDecision(False, delay, reason="rate_limit_wait_exceeds_maximum")
        return RetryDecision(True, delay, reason="retryable")

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.sleeper.sleep(seconds)

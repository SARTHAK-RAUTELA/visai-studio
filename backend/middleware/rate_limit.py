"""
Rate limiting for Claude API calls — Phase 5.
Simple in-memory token bucket. Prevents hitting Anthropic rate limits.
Configure via CLAUDE_RATE_LIMIT_RPM env var (default: 50 requests/minute).
"""

import os
import time
from threading import Lock


class RateLimitError(Exception):
    pass


class ClaudeRateLimiter:
    def __init__(self, rpm: int = 50):
        self.rpm = rpm
        self._tokens = float(rpm)
        self._last_refill = time.time()
        self._lock = Lock()

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_refill
        # tokens per second = rpm / 60
        refill_amount = elapsed * (self.rpm / 60.0)
        self._tokens = min(float(self.rpm), self._tokens + refill_amount)
        self._last_refill = now

    def acquire(self, timeout: float = 30.0) -> bool:
        """
        Block until a token is available.
        Returns True when acquired.
        Raises RateLimitError if timeout is exceeded.
        """
        deadline = time.time() + timeout
        sleep_interval = 0.1

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True

            if time.time() >= deadline:
                raise RateLimitError(
                    f"Claude rate limit: could not acquire token within {timeout}s "
                    f"(limit: {self.rpm} RPM)"
                )
            time.sleep(sleep_interval)

    def get_status(self) -> dict:
        with self._lock:
            self._refill()
            tokens_per_second = self.rpm / 60.0
            deficit = max(0.0, 1.0 - self._tokens)
            next_refill_in = deficit / tokens_per_second if tokens_per_second > 0 else 0.0
            return {
                "tokens_remaining": round(self._tokens, 2),
                "rpm_limit": self.rpm,
                "next_refill_in_seconds": round(next_refill_in, 3),
            }


rate_limiter = ClaudeRateLimiter(rpm=int(os.getenv("CLAUDE_RATE_LIMIT_RPM", "50")))

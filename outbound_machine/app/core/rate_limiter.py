"""
Per-domain rate limiter. Ensures we don't hammer any single domain.
Thread-safe via threading.Lock.
"""
import time
import threading
from collections import defaultdict
import logging

from app.config.settings import settings

logger = logging.getLogger(__name__)


class DomainRateLimiter:
    """
    Tracks last-request time per domain and enforces a minimum delay.
    Usage:
        limiter = DomainRateLimiter()
        limiter.wait("example.com")   # blocks if needed
        # make request
    """

    def __init__(self, delay: float | None = None):
        self.delay = delay if delay is not None else settings.rate_limit_delay
        self._last_request: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def wait(self, domain: str) -> None:
        with self._lock:
            last = self._last_request[domain]
            now = time.monotonic()
            elapsed = now - last
            if elapsed < self.delay:
                sleep_for = self.delay - elapsed
                logger.debug("Rate limiting %s — sleeping %.2fs", domain, sleep_for)
                time.sleep(sleep_for)
            self._last_request[domain] = time.monotonic()


# Module-level singleton
_limiter = DomainRateLimiter()


def rate_limit(domain: str) -> None:
    """Call before every outbound request to the given domain."""
    _limiter.wait(domain)

"""
Retry wrappers using tenacity. Import and use these decorators on any
function that makes network calls.
"""
import logging
from functools import wraps
from typing import Callable, Type

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    RetryError,
)

logger = logging.getLogger(__name__)

# Standard network retry: exponential backoff, up to 3 attempts
def with_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator factory. Wraps a function with tenacity retry logic."""
    def decorator(func: Callable) -> Callable:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def http_retry(max_attempts: int = 3):
    """Convenience wrapper for HTTP calls."""
    import httpx
    return with_retry(
        max_attempts=max_attempts,
        min_wait=1.0,
        max_wait=8.0,
        exceptions=(httpx.HTTPError, httpx.TimeoutException, ConnectionError),
    )

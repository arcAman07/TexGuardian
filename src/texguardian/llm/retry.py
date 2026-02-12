"""Retry utilities for LLM API calls."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0  # seconds
DEFAULT_EXPONENTIAL_BASE = 2.0

# Exceptions that should trigger retry
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)

# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        exponential_base: float = DEFAULT_EXPONENTIAL_BASE,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter


def calculate_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """Calculate delay for retry attempt with exponential backoff.

    Args:
        attempt: Current attempt number (0-based)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    delay = config.base_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)

    if config.jitter:
        # Add random jitter of +/- 25%
        jitter_range = delay * 0.25
        delay += random.uniform(-jitter_range, jitter_range)

    return max(0.1, delay)  # Minimum 100ms


def is_retryable_exception(exc: Exception) -> bool:
    """Check if an exception should trigger a retry."""
    # Check direct exception type
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True

    # Check for httpx exceptions
    exc_name = type(exc).__name__
    if exc_name in ("ConnectError", "ReadTimeout", "WriteTimeout", "PoolTimeout"):
        return True

    # Check for HTTP status code in httpx responses
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        if exc.response.status_code in RETRYABLE_STATUS_CODES:
            return True

    # Check for boto3/botocore exceptions
    if "ThrottlingException" in exc_name or "ServiceUnavailable" in exc_name:
        return True

    # Check exception message for common patterns
    exc_str = str(exc).lower()
    retryable_patterns = [
        "rate limit",
        "too many requests",
        "temporarily unavailable",
        "connection reset",
        "connection refused",
        "timeout",
        "throttl",
    ]
    return any(pattern in exc_str for pattern in retryable_patterns)


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    config: RetryConfig | None = None,
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry logic.

    Args:
        func: Async function to call
        *args: Positional arguments for func
        config: Retry configuration (uses defaults if None)
        **kwargs: Keyword arguments for func

    Returns:
        Result of the function call

    Raises:
        Exception: The last exception if all retries are exhausted
    """
    config = config or RetryConfig()
    last_exception: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            # Check if we should retry
            if attempt >= config.max_retries:
                logger.warning(
                    "All %d retries exhausted for %s",
                    config.max_retries,
                    func.__name__,
                )
                raise

            if not is_retryable_exception(e):
                logger.debug("Non-retryable exception: %s", e)
                raise

            # Calculate delay and wait
            delay = calculate_delay(attempt, config)
            logger.info(
                "Retry %d/%d for %s after %.1fs: %s",
                attempt + 1,
                config.max_retries,
                func.__name__,
                delay,
                e,
            )
            await asyncio.sleep(delay)

    # Should never reach here, but satisfy type checker
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected state in retry loop")


def with_retry(
    config: RetryConfig | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to add retry logic to an async function.

    Usage:
        @with_retry()
        async def my_api_call():
            ...

        @with_retry(RetryConfig(max_retries=5))
        async def my_other_call():
            ...
    """
    config = config or RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await retry_async(func, *args, config=config, **kwargs)

        return wrapper

    return decorator

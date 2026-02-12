"""Tests for retry utilities."""

import asyncio

import pytest

from texguardian.llm.retry import (
    RetryConfig,
    calculate_delay,
    is_retryable_exception,
    retry_async,
)


class RetryableError(Exception):
    """Test exception that should trigger retry."""
    pass


class NonRetryableError(Exception):
    """Test exception that should not trigger retry."""
    pass


def test_calculate_delay_exponential():
    """Test exponential backoff calculation."""
    config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)

    assert calculate_delay(0, config) == 1.0
    assert calculate_delay(1, config) == 2.0
    assert calculate_delay(2, config) == 4.0
    assert calculate_delay(3, config) == 8.0


def test_calculate_delay_max_cap():
    """Test that delay is capped at max_delay."""
    config = RetryConfig(base_delay=1.0, max_delay=5.0, exponential_base=2.0, jitter=False)

    assert calculate_delay(0, config) == 1.0
    assert calculate_delay(3, config) == 5.0  # Capped at max
    assert calculate_delay(10, config) == 5.0  # Still capped


def test_calculate_delay_with_jitter():
    """Test that jitter adds variance."""
    config = RetryConfig(base_delay=1.0, jitter=True)

    # Run multiple times - results should vary
    delays = [calculate_delay(1, config) for _ in range(10)]
    unique_delays = set(delays)

    # With jitter, we should get different values
    assert len(unique_delays) > 1


def test_is_retryable_exception_connection():
    """Test that connection errors are retryable."""
    assert is_retryable_exception(ConnectionError("Connection refused"))
    assert is_retryable_exception(TimeoutError("Request timed out"))


def test_is_retryable_exception_rate_limit():
    """Test that rate limit errors are retryable."""
    exc = Exception("Rate limit exceeded")
    assert is_retryable_exception(exc)

    exc = Exception("Too many requests")
    assert is_retryable_exception(exc)


def test_is_retryable_exception_throttling():
    """Test that throttling errors are retryable."""
    exc = Exception("ThrottlingException: Request rate exceeded")
    assert is_retryable_exception(exc)


def test_is_not_retryable_exception():
    """Test that regular exceptions are not retryable."""
    exc = ValueError("Invalid value")
    assert not is_retryable_exception(exc)

    exc = KeyError("Missing key")
    assert not is_retryable_exception(exc)


@pytest.mark.asyncio
async def test_retry_async_success_first_try():
    """Test successful call on first attempt."""
    call_count = 0

    async def successful_call() -> str:
        nonlocal call_count
        call_count += 1
        return "success"

    result = await retry_async(successful_call)

    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_success_after_retry():
    """Test successful call after retry."""
    call_count = 0

    async def flaky_call() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Connection failed")
        return "success"

    config = RetryConfig(max_retries=3, base_delay=0.01)
    result = await retry_async(flaky_call, config=config)

    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_exhausted():
    """Test that retries are exhausted."""
    call_count = 0

    async def always_fails() -> str:
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Connection failed")

    config = RetryConfig(max_retries=2, base_delay=0.01)

    with pytest.raises(ConnectionError):
        await retry_async(always_fails, config=config)

    # Initial attempt + 2 retries = 3 calls
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_non_retryable():
    """Test that non-retryable exceptions are raised immediately."""
    call_count = 0

    async def non_retryable_error() -> str:
        nonlocal call_count
        call_count += 1
        raise ValueError("Invalid input")

    config = RetryConfig(max_retries=3, base_delay=0.01)

    with pytest.raises(ValueError):
        await retry_async(non_retryable_error, config=config)

    # Should only try once for non-retryable errors
    assert call_count == 1

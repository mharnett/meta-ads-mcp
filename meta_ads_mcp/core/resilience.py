"""Resilience utilities: retry with backoff + response size limiting."""
import asyncio
import functools
import json
import logging

logger = logging.getLogger("mcp-meta-ads")

MAX_RESPONSE_SIZE = 200_000  # 200KB
MAX_RETRIES = 3
BACKOFF_BASE = 0.1  # 100ms
BACKOFF_MAX = 5.0  # 5s


def safe_response(data: str, context: str, max_size: int = MAX_RESPONSE_SIZE) -> str:
    """Truncate JSON response if it exceeds max_size bytes.

    Tries to intelligently halve arrays or known list-valued keys
    (rows, items, results, data) before falling back to raw truncation.
    """
    size = len(data.encode("utf-8"))
    if size <= max_size:
        return data

    logger.warning(
        "Response exceeds size limit (%d > %d bytes), truncating [%s]",
        size, max_size, context,
    )

    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return data[:max_size]

    # Truncate top-level arrays
    if isinstance(parsed, list):
        parsed = parsed[: max(1, len(parsed) // 2)]
        return json.dumps(parsed, indent=2)

    if isinstance(parsed, dict):
        for key in ("rows", "items", "results", "data"):
            if isinstance(parsed.get(key), list):
                original_len = len(parsed[key])
                parsed[key] = parsed[key][: max(1, original_len // 2)]
                parsed["_truncated"] = True
                parsed["_original_count"] = original_len
                parsed["_returned_count"] = len(parsed[key])
                return json.dumps(parsed, indent=2)

    return data[:max_size]


async def with_resilience(fn, *args, operation_name: str = "api_call", **kwargs):
    """Execute a function with retry + exponential backoff.

    If *fn* is a coroutine function it is awaited directly; otherwise it is
    dispatched to the default executor via ``loop.run_in_executor``.

    Retries on transient errors (429, 500+, network timeouts).
    Non-retryable errors (400, invalid, permission, not found) raise immediately
    unless the message also contains '429' or 'rate' (throttle disguised as 400).
    """
    loop = asyncio.get_event_loop()
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.debug("Starting %s (attempt %d/%d)", operation_name, attempt, MAX_RETRIES)

            if asyncio.iscoroutinefunction(fn):
                coro = fn(*args, **kwargs)
            else:
                coro = loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))

            result = await asyncio.wait_for(coro, timeout=30.0)
            logger.debug("%s succeeded", operation_name)
            return result

        except asyncio.TimeoutError:
            last_error = TimeoutError(f"{operation_name} timed out after 30s")
            logger.warning("%s timed out (attempt %d/%d)", operation_name, attempt, MAX_RETRIES)

        except Exception as e:
            last_error = e
            err_str = str(e).lower()

            # Non-retryable errors -- raise immediately
            if any(code in err_str for code in ("400", "invalid", "not found", "permission")):
                if "429" not in err_str and "rate" not in err_str:
                    logger.error("%s failed (non-retryable): %s", operation_name, e)
                    raise

            logger.warning(
                "%s failed (attempt %d/%d): %s",
                operation_name, attempt, MAX_RETRIES, e,
            )

        if attempt < MAX_RETRIES:
            delay = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_MAX)
            await asyncio.sleep(delay)

    logger.error("%s failed after %d retries: %s", operation_name, MAX_RETRIES, last_error)
    raise last_error

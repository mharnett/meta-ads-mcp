"""Tests for resilience module: retry, backoff, safe_response, timeout."""
import asyncio
import json
import pytest
from meta_ads_mcp.core.resilience import safe_response, with_resilience


class TestSafeResponse:
    def test_small_data_unchanged(self):
        data = json.dumps({"name": "test", "count": 100})
        assert safe_response(data, "test") == data

    def test_truncates_large_array(self):
        large = [{"id": i, "x": "y" * 100} for i in range(10000)]
        data = json.dumps(large)
        result = safe_response(data, "test")
        parsed = json.loads(result)
        assert len(parsed) < len(large)

    def test_truncates_large_data_key(self):
        obj = {"data": [{"id": i, "payload": "x" * 200} for i in range(5000)]}
        data = json.dumps(obj)
        result = safe_response(data, "test")
        parsed = json.loads(result)
        assert len(parsed["data"]) < 5000
        assert parsed.get("_truncated") is True
        assert "_original_count" in parsed
        assert "_returned_count" in parsed

    def test_truncates_large_rows(self):
        obj = {"rows": [{"id": i, "data": "x" * 200} for i in range(5000)]}
        data = json.dumps(obj)
        result = safe_response(data, "test")
        parsed = json.loads(result)
        assert len(parsed["rows"]) < 5000
        assert parsed.get("_truncated") is True

    def test_custom_max_size(self):
        # Build a payload that is large enough for halving to meaningfully reduce it
        obj = {"items": [{"id": i, "payload": "x" * 200} for i in range(100)]}
        data = json.dumps(obj)
        result = safe_response(data, "test", max_size=5000)
        parsed = json.loads(result)
        assert len(parsed["items"]) == 50
        assert parsed.get("_truncated") is True

    def test_non_json_truncated_raw(self):
        data = "x" * 300_000
        result = safe_response(data, "test")
        assert len(result) == 200_000

    def test_dict_without_known_keys_truncated_raw(self):
        # A dict without rows/items/results/data falls through to raw truncation
        obj = {"custom_key": "v" * 300_000}
        data = json.dumps(obj)
        result = safe_response(data, "test")
        assert len(result) == 200_000


class TestWithResilience:
    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        def fn():
            return {"success": True}
        result = await with_resilience(fn, operation_name="test")
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        async def fn():
            return {"async": True}
        result = await with_resilience(fn, operation_name="test")
        assert result == {"async": True}

    @pytest.mark.asyncio
    async def test_retries_on_transient_failure(self):
        attempts = {"count": 0}
        def fn():
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise Exception("500 Internal Server Error")
            return {"success": True}
        result = await with_resilience(fn, operation_name="test")
        assert result == {"success": True}
        assert attempts["count"] == 2

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self):
        attempts = {"count": 0}
        def fn():
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise Exception("429 Too Many Requests")
            return {"ok": True}
        result = await with_resilience(fn, operation_name="test")
        assert result == {"ok": True}
        assert attempts["count"] == 2

    @pytest.mark.asyncio
    async def test_fails_after_max_retries(self):
        def fn():
            raise Exception("500 Server Error")
        with pytest.raises(Exception, match="Server Error"):
            await with_resilience(fn, operation_name="test")

    @pytest.mark.asyncio
    async def test_non_retryable_fails_immediately(self):
        attempts = {"count": 0}
        def fn():
            attempts["count"] += 1
            raise Exception("400 invalid request")
        with pytest.raises(Exception, match="invalid"):
            await with_resilience(fn, operation_name="test")
        assert attempts["count"] == 1

    @pytest.mark.asyncio
    async def test_non_retryable_permission_fails_immediately(self):
        attempts = {"count": 0}
        def fn():
            attempts["count"] += 1
            raise Exception("permission denied for this resource")
        with pytest.raises(Exception, match="permission"):
            await with_resilience(fn, operation_name="test")
        assert attempts["count"] == 1

    @pytest.mark.asyncio
    async def test_rate_limit_in_400_retries(self):
        """A 400 that mentions 'rate' should be retried, not treated as non-retryable."""
        attempts = {"count": 0}
        def fn():
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise Exception("400 rate limit exceeded")
            return {"ok": True}
        result = await with_resilience(fn, operation_name="test")
        assert result == {"ok": True}
        assert attempts["count"] == 2

    @pytest.mark.asyncio
    async def test_timeout(self):
        async def slow_fn():
            await asyncio.sleep(60)
            return {"never": "reached"}
        with pytest.raises(TimeoutError):
            await with_resilience(slow_fn, operation_name="test_timeout")

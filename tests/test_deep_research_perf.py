#!/usr/bin/env python3
"""Performance regression tests for openai_deep_research.

Covers two audit findings:
  1. N+1 serial API calls — campaigns must be fetched concurrently per account,
     bounded by a semaphore.
  2. Unbounded self._cache — cache must be capped (LRU eviction) so a single
     long-running search can't grow memory without bound.
"""

import asyncio
import time

import pytest

from meta_ads_mcp.core import openai_deep_research
from meta_ads_mcp.core.openai_deep_research import MetaAdsDataManager


# ---------------------------------------------------------------------------
# Parallelization tests
# ---------------------------------------------------------------------------

def _make_accounts(n):
    return [{"id": f"act_{i}", "name": "alpha campaign match", "account_status": "1"}
            for i in range(n)]


@pytest.mark.asyncio
async def test_campaigns_fetched_concurrently(monkeypatch):
    """With 10+ matching accounts, per-account campaign fetches must overlap.

    Each _get_campaigns sleeps 100ms. Serial => >=1.0s for 10 accounts.
    Concurrent => roughly one sleep window. Assert wall time proves overlap.
    """
    accounts = _make_accounts(10)

    concurrency = {"current": 0, "max": 0}

    async def fake_get_ad_accounts(self, access_token, limit=200):
        return accounts

    async def fake_get_campaigns(self, access_token, account_id, limit=25):
        concurrency["current"] += 1
        concurrency["max"] = max(concurrency["max"], concurrency["current"])
        try:
            await asyncio.sleep(0.1)
            return []
        finally:
            concurrency["current"] -= 1

    monkeypatch.setattr(MetaAdsDataManager, "_get_ad_accounts", fake_get_ad_accounts)
    monkeypatch.setattr(MetaAdsDataManager, "_get_campaigns", fake_get_campaigns)

    mgr = MetaAdsDataManager()
    start = time.monotonic()
    await mgr.search_records("alpha", access_token="tok")
    elapsed = time.monotonic() - start

    # Serial would be >= 1.0s; concurrent should be well under half that.
    assert elapsed < 0.5, f"campaign fetches ran serially (elapsed={elapsed:.2f}s)"
    # Concurrency actually happened (more than one in flight at once).
    assert concurrency["max"] > 1, "no overlap observed; calls were serial"


@pytest.mark.asyncio
async def test_campaign_call_count_matches_account_count(monkeypatch):
    """_get_campaigns must be invoked exactly once per matching account."""
    accounts = _make_accounts(15)
    calls = {"n": 0}

    async def fake_get_ad_accounts(self, access_token, limit=200):
        return accounts

    async def fake_get_campaigns(self, access_token, account_id, limit=25):
        calls["n"] += 1
        return []

    monkeypatch.setattr(MetaAdsDataManager, "_get_ad_accounts", fake_get_ad_accounts)
    monkeypatch.setattr(MetaAdsDataManager, "_get_campaigns", fake_get_campaigns)

    mgr = MetaAdsDataManager()
    await mgr.search_records("alpha", access_token="tok")

    assert calls["n"] == 15, f"expected 15 campaign fetches, got {calls['n']}"


@pytest.mark.asyncio
async def test_semaphore_caps_concurrency(monkeypatch):
    """No more than the configured limit of concurrent _get_campaigns calls."""
    accounts = _make_accounts(50)
    concurrency = {"current": 0, "max": 0}

    async def fake_get_ad_accounts(self, access_token, limit=200):
        return accounts

    async def fake_get_campaigns(self, access_token, account_id, limit=25):
        concurrency["current"] += 1
        concurrency["max"] = max(concurrency["max"], concurrency["current"])
        try:
            await asyncio.sleep(0.02)
            return []
        finally:
            concurrency["current"] -= 1

    monkeypatch.setattr(MetaAdsDataManager, "_get_ad_accounts", fake_get_ad_accounts)
    monkeypatch.setattr(MetaAdsDataManager, "_get_campaigns", fake_get_campaigns)

    mgr = MetaAdsDataManager()
    await mgr.search_records("alpha", access_token="tok")

    limit = openai_deep_research.MAX_CONCURRENT_REQUESTS
    assert concurrency["max"] <= limit, (
        f"semaphore breached: peak {concurrency['max']} > limit {limit}"
    )


# ---------------------------------------------------------------------------
# Bounded-cache test (shape: aggregate cardinality invariant)
# ---------------------------------------------------------------------------

def test_cache_is_bounded():
    """Inserting > CACHE_MAX_SIZE records must evict oldest; size stays capped."""
    mgr = MetaAdsDataManager()
    cap = openai_deep_research.CACHE_MAX_SIZE

    for i in range(cap + 100):
        mgr._cache[f"rec:{i}"] = {"id": f"rec:{i}", "type": "account"}

    assert len(mgr._cache) <= cap, (
        f"cache unbounded: {len(mgr._cache)} entries (cap={cap})"
    )
    # LRU: most-recent insert retained, oldest evicted.
    assert mgr.fetch_record(f"rec:{cap + 99}") is not None
    assert mgr.fetch_record("rec:0") is None

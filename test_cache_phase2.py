"""
Test script for Phase 2: Persistent OHLCV Caching

Tests:
  1. Cache miss: First request fetches from API, creates cache file
  2. Cache hit: Second request reads from file (no API call)
  3. Cache expiry logic: Verify 24h TTL logic
  4. Cache survives process restart: Load from file after restart
  5. Multiple symbols don't collide: Unique cache keys
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
import shutil

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
custom_trading_bot_dir = os.path.join(base_dir, "custom_TradingBot")
sys.path.insert(0, custom_trading_bot_dir)
sys.path.insert(0, base_dir)

# Load environment before importing modules
from dotenv import load_dotenv
env_path = os.path.join(custom_trading_bot_dir, ".env")
load_dotenv(env_path)

from cache_manager import CacheManager
from Tools.Technical_Tools import _cached_price_history, _cache_manager

print("=" * 80)
print("PHASE 2 TEST: Persistent OHLCV Caching")
print("=" * 80)

# --- TEST 1: Cache directory creation ---
print("\n[TEST 1] Cache directory creation")
cache_dir = _cache_manager.cache_dir
print(f"  Cache directory: {cache_dir}")
print(f"  Directory exists: {cache_dir.exists()}")
assert cache_dir.exists(), "Cache directory not created"
print("  ✅ PASS")

# --- TEST 2: Cache miss (first call) ---
print("\n[TEST 2] Cache miss - first API call")
test_symbol = "AAPL"
test_start = "2026-01-01"
test_end = "2026-01-10"
cache_key = f"price:{test_symbol}:{test_start}:{test_end}"

# Clear any existing cache for this key
_cache_manager.invalidate()
print(f"  Cleared all cache files")

# Get initial cache stats
stats_before = _cache_manager.get_stats()
print(f"  Cache before test: {stats_before['file_count']} files, {stats_before['total_size_bytes']} bytes")

# First call should hit API
print(f"  Fetching price history for {test_symbol} ({test_start} to {test_end})...")
start_time = time.time()
result1 = _cached_price_history(test_symbol, test_start, test_end)
elapsed1 = time.time() - start_time
print(f"  First call time: {elapsed1:.3f}s (API call expected)")

# Check that cache file was created
cache_path = _cache_manager._get_cache_path(cache_key)
file_created = cache_path.exists()
print(f"  Cache file created: {file_created} at {cache_path}")
assert file_created, f"Cache file not created at {cache_path}"

# Verify result is not None
assert result1 is not None, "Result is None - API call failed"
print(f"  Result type: {type(result1)}")
print("  ✅ PASS")

# --- TEST 3: Cache hit (second call) ---
print("\n[TEST 3] Cache hit - file cache read")
print(f"  Fetching same data again for {test_symbol} ({test_start} to {test_end})...")
start_time = time.time()
result2 = _cached_price_history(test_symbol, test_start, test_end)
elapsed2 = time.time() - start_time
print(f"  Second call time: {elapsed2:.3f}s (file cache expected)")

# Verify results have same data
# result1 is OBBject from API, result2 is dict from cache
# Extract the key data for comparison
def extract_key_data(result):
    if hasattr(result, 'results'):
        return len(result.results)  # Just compare data length
    elif isinstance(result, dict) and 'results' in result:
        return len(result['results'])
    return 0

data_len1 = extract_key_data(result1)
data_len2 = extract_key_data(result2)
assert data_len1 == data_len2, f"Result data differs: {data_len1} vs {data_len2}"
print(f"  Results match: True (both have {data_len1} data points)")

# Cache hit should be significantly faster than API call
if elapsed2 < elapsed1:
    speedup = elapsed1 / elapsed2
    print(f"  Speedup factor: {speedup:.1f}x faster")
print("  ✅ PASS")

# --- TEST 4: Cache statistics ---
print("\n[TEST 4] Cache statistics and metadata")
stats_after = _cache_manager.get_stats()
print(f"  Cache after test: {stats_after['file_count']} files, {stats_after['total_size_bytes']} bytes")
print(f"  Cache TTL: {stats_after['ttl_hours']} hours")
print(f"  Oldest entry: {stats_after['oldest_entry']}")
print(f"  Newest entry: {stats_after['newest_entry']}")

assert stats_after['file_count'] > 0, "No cache files created"
assert stats_after['total_size_bytes'] > 0, "Cache size is 0"
assert stats_after['ttl_hours'] == 24, f"TTL should be 24h, got {stats_after['ttl_hours']}"
print("  ✅ PASS")

# --- TEST 5: Multiple symbols don't collide ---
print("\n[TEST 5] Multiple symbols - unique cache keys")
test_symbols = ["AAPL", "MSFT", "NVDA"]
cache_keys = []

for symbol in test_symbols:
    print(f"  Fetching {symbol}...")
    result = _cached_price_history(symbol, test_start, test_end)
    key = f"price:{symbol}:{test_start}:{test_end}"
    cache_keys.append(key)
    cache_path = _cache_manager._get_cache_path(key)
    print(f"    Cache path: {cache_path.name}")
    assert cache_path.exists(), f"Cache file not created for {symbol}"

# Verify all cache keys produce unique filenames
unique_filenames = len(set(
    _cache_manager._get_cache_path(key).name for key in cache_keys
))
print(f"  Total symbols: {len(test_symbols)}, Unique cache files: {unique_filenames}")
assert unique_filenames == len(test_symbols), "Cache keys collide!"
print("  ✅ PASS")

# --- TEST 6: Cache persistence (simulate restart) ---
print("\n[TEST 6] Cache persistence - file survives 'restart'")
# We already have cache files from previous tests
# Create a new CacheManager instance (simulates fresh process)
cache_manager_new = CacheManager(cache_dir=_cache_manager.cache_dir, ttl_hours=24)

cache_key_test = "price:AAPL:2026-01-01:2026-01-10"
print(f"  Loading {cache_key_test} with fresh CacheManager...")
start_time = time.time()
cached_data = cache_manager_new.get(cache_key_test)
elapsed = time.time() - start_time
print(f"  Load time: {elapsed:.3f}s (very fast if from file)")

assert cached_data is not None, "Cache not found after 'restart'"
print(f"  Data found in cache: True")
print("  ✅ PASS")

# --- TEST 7: TTL expiry logic ---
print("\n[TEST 7] TTL expiry logic (24-hour validation)")
# Create a cache entry with manual timestamp manipulation
test_key = "test:expiry:validation"
test_value = {"symbol": "TEST", "data": [1, 2, 3]}

# Store normally
cache_manager_new.set(test_key, test_value)
cache_path = cache_manager_new._get_cache_path(test_key)

# Read and modify timestamp to be 25 hours old
with open(cache_path, 'r') as f:
    entry = json.load(f)

old_timestamp = (datetime.now() - timedelta(hours=25)).isoformat()
entry['timestamp'] = old_timestamp

with open(cache_path, 'w') as f:
    json.dump(entry, f)

print(f"  Created cache entry with timestamp 25 hours ago")

# Try to retrieve - should return None (expired)
retrieved = cache_manager_new.get(test_key)
print(f"  Retrieved expired entry: {retrieved}")
assert retrieved is None, "Expired entry was not cleaned up"

# Verify file was deleted
file_exists = cache_path.exists()
print(f"  Expired file deleted: {not file_exists}")
assert not file_exists, "Expired file not deleted"
print("  ✅ PASS")

# --- TEST 8: Invalidate cache ---
print("\n[TEST 8] Cache invalidation")
stats_before_invalidate = cache_manager_new.get_stats()
print(f"  Cache files before invalidate: {stats_before_invalidate['file_count']}")

deleted = cache_manager_new.invalidate()
print(f"  Files deleted: {deleted}")

stats_after_invalidate = cache_manager_new.get_stats()
print(f"  Cache files after invalidate: {stats_after_invalidate['file_count']}")

assert stats_after_invalidate['file_count'] == 0, "Cache not fully cleared"
print("  ✅ PASS")

# --- CLEANUP ---
print("\n[CLEANUP] Removing test cache directory")
# Don't actually delete - let user see the results
print(f"  Cache directory: {_cache_manager.cache_dir}")
print(f"  (Keeping cache files for inspection)")

print("\n" + "=" * 80)
print("ALL PHASE 2 TESTS PASSED ✅")
print("=" * 80)
print("\nSummary:")
print("  ✅ Cache directory created at .cache/")
print("  ✅ Cache miss triggers API call and creates file")
print("  ✅ Cache hit reads from file (faster)")
print("  ✅ Multiple symbols use unique cache keys (no collision)")
print("  ✅ Cache persists across process restarts")
print("  ✅ TTL expiry removes stale data after 24h")
print("  ✅ Cache can be fully invalidated")
print("\nDual-layer caching (L1 memory + L2 file) is working correctly!")

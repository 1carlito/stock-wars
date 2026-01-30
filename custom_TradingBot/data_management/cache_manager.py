"""
cache_manager.py: File-based cache for persistent OHLCV and technical indicator data.

Implements dual-layer caching:
  L1: @lru_cache (in-memory, fast, lost on restart)
  L2: File-based cache (persistent, survives restarts, 24-hour TTL)
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional, Dict


class CacheManager:
    """
    File-based cache manager with TTL support.

    Stores cache entries as JSON files with timestamp metadata.
    Implements 24-hour TTL by default (configurable).
    """

    def __init__(self, cache_dir: str = "./cache", ttl_hours: int = 24):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory to store cache files
            ttl_hours: Time-to-live for cached entries in hours (default: 24)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)

    def _hash_key(self, key: str) -> str:
        """
        Generate a safe filename from a cache key using SHA256.

        Args:
            key: Cache key string

        Returns:
            Hex digest of SHA256 hash (64 chars)
        """
        return hashlib.sha256(key.encode()).hexdigest()

    def _get_cache_path(self, key: str) -> Path:
        """Get the file path for a cache key."""
        hash_name = self._hash_key(key)
        return self.cache_dir / f"{hash_name}.json"

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from cache if it exists and hasn't expired.

        Args:
            key: Cache key

        Returns:
            Cached value if found and fresh, None otherwise
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r') as f:
                cache_entry = json.load(f)

            # Check if cache has expired
            timestamp_str = cache_entry.get("timestamp")
            if not timestamp_str:
                return None

            cache_time = datetime.fromisoformat(timestamp_str)
            if datetime.now() - cache_time > self.ttl:
                # Cache expired, delete it
                cache_path.unlink()
                return None

            return cache_entry.get("data")
        except (json.JSONDecodeError, OSError, KeyError):
            # Corrupted or invalid cache file
            return None

    def set(self, key: str, value: Any) -> None:
        """
        Store value in cache with current timestamp.

        Handles Pydantic models and OBBject types by converting to dict.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable, or Pydantic model with .dict())
        """
        cache_path = self._get_cache_path(key)

        # Convert Pydantic models to dict for serialization
        serializable_value = value
        if hasattr(value, 'dict'):
            # OBBject or Pydantic model - convert to dict
            try:
                serializable_value = value.dict()
            except Exception:
                # If .dict() fails, fall back to original value
                pass

        cache_entry = {
            "timestamp": datetime.now().isoformat(),
            "data": serializable_value
        }

        try:
            with open(cache_path, 'w') as f:
                json.dump(cache_entry, f, indent=2, default=str)
        except (TypeError, OSError) as e:
            # If value is not JSON serializable or file write fails, silently skip caching
            pass

    def invalidate(self, pattern: str = "*") -> int:
        """
        Delete cache entries matching a pattern.

        Args:
            pattern: Glob pattern (e.g., "*", "price:*", "technical:*")
                    If "*", deletes all cache files.

        Returns:
            Number of files deleted
        """
        if pattern == "*":
            # Delete all cache files
            cache_files = list(self.cache_dir.glob("*.json"))
        else:
            # For now, only support full key matching, not glob patterns
            # To match a pattern, caller should iterate and check keys manually
            hash_name = self._hash_key(pattern)
            cache_path = self.cache_dir / f"{hash_name}.json"
            cache_files = [cache_path] if cache_path.exists() else []

        deleted_count = 0
        for cache_file in cache_files:
            try:
                cache_file.unlink()
                deleted_count += 1
            except OSError:
                pass

        return deleted_count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache size, file count, oldest/newest entry timestamps
        """
        cache_files = list(self.cache_dir.glob("*.json"))

        total_size = sum(f.stat().st_size for f in cache_files)

        timestamps = []
        for cache_file in cache_files:
            try:
                with open(cache_file, 'r') as f:
                    entry = json.load(f)
                    timestamp_str = entry.get("timestamp")
                    if timestamp_str:
                        timestamps.append(datetime.fromisoformat(timestamp_str))
            except (json.JSONDecodeError, OSError):
                pass

        return {
            "file_count": len(cache_files),
            "total_size_bytes": total_size,
            "oldest_entry": min(timestamps).isoformat() if timestamps else None,
            "newest_entry": max(timestamps).isoformat() if timestamps else None,
            "ttl_hours": self.ttl.total_seconds() / 3600,
        }

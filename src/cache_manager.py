from typing import Dict, Any, Optional, Set, Tuple
import threading
import time
import logging
import json
import hashlib
from datetime import datetime, timedelta
import argparse
from enum import Enum
from dataclasses import dataclass
import redis
import pickle
from collections import OrderedDict


class CachePolicy(Enum):
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"


class ConsistencyLevel(Enum):
    STRONG = "strong"
    EVENTUAL = "eventual"


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: datetime
    ttl: Optional[int]  # in seconds
    version: int = 1
    last_accessed: Optional[datetime] = None
    access_count: int = 0


class CacheMetrics:
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.invalidations = 0
        self.total_items = 0
        self.total_size = 0  # in bytes
        self.operation_latencies: Dict[str, float] = {}

    def record_operation(self, operation: str, latency: float):
        if operation not in self.operation_latencies:
            self.operation_latencies[operation] = []
        self.operation_latencies[operation].append(latency)


class CacheManager:
    def __init__(self,
                 max_size: int = 1000,  # maximum number of items
                 policy: CachePolicy = CachePolicy.LRU,
                 redis_host: str = "localhost",
                 redis_port: int = 6379):
        self.max_size = max_size
        self.policy = policy
        self.metrics = CacheMetrics()
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

        # Local cache storage
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # Redis connection for distributed coordination
        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )

        # Start maintenance thread
        self.maintenance_thread = threading.Thread(target=self._maintenance_loop)
        self.maintenance_thread.daemon = True
        self.maintenance_thread.start()

        self._setup_logging()

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler('cache.log'),
                logging.StreamHandler()
            ]
        )

    def set(self, key: str, value: Any, ttl: Optional[int] = None,
            consistency: ConsistencyLevel = ConsistencyLevel.EVENTUAL) -> bool:
        """Set a value in the cache with optional TTL."""
        try:
            start_time = time.time()

            # Serialize value to calculate size
            serialized_value = pickle.dumps(value)
            entry_size = len(serialized_value)

            with self.lock:
                # Check if we need to evict items
                while len(self.cache) >= self.max_size:
                    self._evict_entry()

                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=datetime.now(),
                    ttl=ttl,
                    last_accessed=datetime.now()
                )

                self.cache[key] = entry
                self.metrics.total_items += 1
                self.metrics.total_size += entry_size

                # If strong consistency is required, synchronize with other instances
                if consistency == ConsistencyLevel.STRONG:
                    self._sync_entry(key, entry)

                latency = time.time() - start_time
                self.metrics.record_operation('set', latency)
                self.logger.info(f"Cache entry set: {key}")
                return True

        except Exception as e:
            self.logger.error(f"Error setting cache entry: {str(e)}")
            return False

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache."""
        try:
            start_time = time.time()

            with self.lock:
                if key not in self.cache:
                    self.metrics.misses += 1
                    latency = time.time() - start_time
                    self.metrics.record_operation('miss', latency)
                    return None

                entry = self.cache[key]

                # Check if entry has expired
                if entry.ttl and datetime.now() > entry.created_at + timedelta(seconds=entry.ttl):
                    del self.cache[key]
                    self.metrics.invalidations += 1
                    return None

                # Update access statistics
                entry.last_accessed = datetime.now()
                entry.access_count += 1

                # Move to end if using LRU
                if self.policy == CachePolicy.LRU:
                    self.cache.move_to_end(key)

                self.metrics.hits += 1
                latency = time.time() - start_time
                self.metrics.record_operation('hit', latency)
                return entry.value

        except Exception as e:
            self.logger.error(f"Error getting cache entry: {str(e)}")
            return None

    def delete(self, key: str,
               consistency: ConsistencyLevel = ConsistencyLevel.EVENTUAL) -> bool:
        """Delete a value from the cache."""
        try:
            start_time = time.time()

            with self.lock:
                if key in self.cache:
                    entry = self.cache[key]
                    entry_size = len(pickle.dumps(entry.value))

                    del self.cache[key]
                    self.metrics.total_items -= 1
                    self.metrics.total_size -= entry_size
                    self.metrics.invalidations += 1

                    # If strong consistency is required, notify other instances
                    if consistency == ConsistencyLevel.STRONG:
                        self._notify_deletion(key)

                    latency = time.time() - start_time
                    self.metrics.record_operation('delete', latency)
                    self.logger.info(f"Cache entry deleted: {key}")
                    return True

            return False

        except Exception as e:
            self.logger.error(f"Error deleting cache entry: {str(e)}")
            return False

    def clear(self) -> bool:
        """Clear all entries from the cache."""
        try:
            with self.lock:
                self.cache.clear()
                self.metrics.total_items = 0
                self.metrics.total_size = 0
                self.metrics.invalidations += 1

                # Notify other instances
                self.redis.publish('cache_clear', 'clear')

                self.logger.info("Cache cleared")
                return True

        except Exception as e:
            self.logger.error(f"Error clearing cache: {str(e)}")
            return False

    def _evict_entry(self):
        """Evict an entry based on the cache policy."""
        if not self.cache:
            return

        if self.policy == CachePolicy.LRU:
            # Evict least recently used
            key, entry = self.cache.popitem(last=False)
        elif self.policy == CachePolicy.LFU:
            # Evict least frequently used
            key = min(self.cache.keys(),
                      key=lambda k: self.cache[k].access_count)
            entry = self.cache.pop(key)
        else:  # FIFO
            key, entry = self.cache.popitem(last=False)

        entry_size = len(pickle.dumps(entry.value))
        self.metrics.total_size -= entry_size
        self.metrics.evictions += 1
        self.logger.info(f"Evicted cache entry: {key}")

    def _sync_entry(self, key: str, entry: CacheEntry):
        """Synchronize cache entry with other instances."""
        serialized_entry = pickle.dumps(entry)
        self.redis.set(f"cache:{key}", serialized_entry)
        self.redis.publish('cache_update', json.dumps({
            'key': key,
            'version': entry.version
        }))

    def _notify_deletion(self, key: str):
        """Notify other instances about entry deletion."""
        self.redis.delete(f"cache:{key}")
        self.redis.publish('cache_delete', key)

    def _maintenance_loop(self):
        """Background thread for cache maintenance."""
        while True:
            try:
                # Clean up expired entries
                with self.lock:
                    now = datetime.now()
                    expired_keys = [
                        key for key, entry in self.cache.items()
                        if entry.ttl and now > entry.created_at + timedelta(seconds=entry.ttl)
                    ]

                    for key in expired_keys:
                        self.delete(key)

                # Synchronize with other instances
                self._sync_with_cluster()

                time.sleep(60)  # Run maintenance every minute

            except Exception as e:
                self.logger.error(f"Error in maintenance loop: {str(e)}")
                time.sleep(60)  # Wait before retrying

    def _sync_with_cluster(self):
        """Synchronize cache state with other instances."""
        try:
            # Get all keys from Redis
            cluster_keys = self.redis.keys("cache:*")

            for cluster_key in cluster_keys:
                key = cluster_key.split(":", 1)[1]
                serialized_entry = self.redis.get(cluster_key)

                if serialized_entry:
                    entry = pickle.loads(serialized_entry)

                    # Update local cache if version is newer
                    if (key not in self.cache or
                            entry.version > self.cache[key].version):
                        self.cache[key] = entry

        except Exception as e:
            self.logger.error(f"Error syncing with cluster: {str(e)}")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            hit_rate = (
                self.metrics.hits / (self.metrics.hits + self.metrics.misses)
                if self.metrics.hits + self.metrics.misses > 0 else 0
            )

            avg_latencies = {
                op: sum(latencies) / len(latencies)
                for op, latencies in self.metrics.operation_latencies.items()
                if latencies
            }

            return {
                'total_items': self.metrics.total_items,
                'total_size': self.metrics.total_size,
                'hits': self.metrics.hits,
                'misses': self.metrics.misses,
                'hit_rate': hit_rate,
                'evictions': self.metrics.evictions,
                'invalidations': self.metrics.invalidations,
                'average_latencies': avg_latencies
            }


def main():
    """CLI entry point for the CacheManager."""
    parser = argparse.ArgumentParser(description='Cache Manager CLI')
    parser.add_argument('command', choices=['get', 'set', 'delete', 'clear', 'stats'])
    parser.add_argument('--key', help='Cache key')
    parser.add_argument('--value', help='Cache value')
    parser.add_argument('--ttl', type=int, help='Time to live in seconds')
    args = parser.parse_args()

    cache_manager = CacheManager()

    try:
        if args.command == 'get' and args.key:
            value = cache_manager.get(args.key)
            print(json.dumps({'value': value}, indent=2))

        elif args.command == 'set' and args.key and args.value:
            success = cache_manager.set(args.key, args.value, ttl=args.ttl)
            print(json.dumps({'success': success}, indent=2))

        elif args.command == 'delete' and args.key:
            success = cache_manager.delete(args.key)
            print(json.dumps({'success': success}, indent=2))

        elif args.command == 'clear':
            success = cache_manager.clear()
            print(json.dumps({'success': success}, indent=2))

        elif args.command == 'stats':
            print(json.dumps(cache_manager.get_stats(), indent=2))

    except Exception as e:
        print(json.dumps({'error': str(e)}, indent=2))
        exit(1)


if __name__ == '__main__':
    main()
import unittest
from unittest.mock import Mock, patch
import time
from datetime import datetime, timedelta
from cache_manager import (
    CacheManager,
    CachePolicy,
    ConsistencyLevel,
    CacheEntry
)


class TestCacheManager(unittest.TestCase):
    def setUp(self):
        self.cache_manager = CacheManager(max_size=5)

    def test_basic_operations(self):
        # Test set and get
        self.cache_manager.set('test_key', 'test_value')
        value = self.cache_manager.get('test_key')
        self.assertEqual(value, 'test_value')

        # Test delete
        self.cache_manager.delete('test_key')
        value = self.cache_manager.get('test_key')
        self.assertIsNone(value)

    def test_ttl(self):
        # Test TTL expiration
        self.cache_manager.set('ttl_key', 'ttl_value', ttl=1)
        value = self.cache_manager.get('ttl_key')
        self.assertEqual(value, 'ttl_value')

        # Wait for TTL to expire
        time.sleep(1.1)
        value = self.cache_manager.get('ttl_key')
        self.assertIsNone(value)

    def test_lru_eviction(self):
        # Fill cache to max size
        for i in range(5):
            self.cache_manager.set(f'key{i}', f'value{i}')

        # Verify all items present
        for i in range(5):
            self.assertEqual(self.cache_manager.get(f'key{i}'), f'value{i}')
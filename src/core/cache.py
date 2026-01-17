"""
LRU Cache implementation for storing preloaded media data.
Limits memory usage by automatically evicting oldest items when size limit exceeded.
"""

from collections import OrderedDict


class LRUCache:
    """Simple LRU (Least Recently Used) cache with maximum size limit"""
    
    def __init__(self, max_size=100):
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of items to store before evicting oldest
        """
        self.cache = OrderedDict()
        self.max_size = max_size
    
    def get(self, key):
        """
        Get value from cache and mark as recently used.
        
        Args:
            key: Cache key
            
        Returns:
            Value if key exists, None otherwise
        """
        if key in self.cache:
            # Move to end to mark as recently used
            self.cache.move_to_end(key)
            return self.cache[key]
        return None
    
    def set(self, key, value):
        """
        Set value in cache and evict oldest if needed.
        
        Args:
            key: Cache key
            value: Value to store
        """
        if key in self.cache:
            # Remove and re-add to mark as recently used
            del self.cache[key]
        self.cache[key] = value
        # If cache exceeds max size, remove oldest (first) item
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
    
    def clear(self):
        """Clear all items from cache"""
        self.cache.clear()
    
    def __contains__(self, key):
        """Check if key exists in cache"""
        return key in self.cache

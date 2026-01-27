"""
Playlist and queue management for the music player.
Handles adding, removing, filtering, and organizing tracks.
"""

from src.core.cache import LRUCache


class PlaylistManager:
    """Manages playlist state and operations"""
    
    def __init__(self, album_art_cache_size=100, color_cache_size=100):
        """
        Initialize playlist manager.
        
        Args:
            album_art_cache_size: Max album art cache entries
            color_cache_size: Max dominant color cache entries
        """
        self.playlist = []
        self.current_index = -1
        self.track_durations = {}
        
        # Caches for preloaded data
        self.album_art_pixmap_cache = LRUCache(album_art_cache_size)
        self.dominant_color_cache = LRUCache(color_cache_size)
    
    def add_track(self, file_path):
        """Add track to playlist"""
        if file_path not in self.playlist:
            self.playlist.append(file_path)
    
    def add_tracks(self, file_paths):
        """Add multiple tracks to playlist"""
        for path in file_paths:
            self.add_track(path)
    
    def remove_track(self, index):
        """Remove track at specified index"""
        if 0 <= index < len(self.playlist):
            removed_path = self.playlist.pop(index)
            self._clear_track_caches(removed_path)
            
            # Adjust current index if needed
            if self.current_index >= len(self.playlist) and self.current_index > 0:
                self.current_index -= 1
            
            return True
        return False
    
    def remove_tracks(self, files_to_remove):
        """Remove multiple tracks from playlist"""
        remove_set = set(files_to_remove)
        if not remove_set:
            return
        
        # Get current track path
        current_path = None
        if 0 <= self.current_index < len(self.playlist):
            current_path = self.playlist[self.current_index]
        removing_current = current_path in remove_set if current_path else False
        
        # Purge playlist
        self.playlist = [p for p in self.playlist if p not in remove_set]
        
        for path in remove_set:
            self._clear_track_caches(path)
        
        # Reset playback if removing current track
        if removing_current:
            self.current_index = -1
        
        return removing_current
    
    def clear(self):
        """Clear entire playlist and caches"""
        self.playlist.clear()
        self.current_index = -1
        self.track_durations.clear()
        self.album_art_pixmap_cache.clear()
        self.dominant_color_cache.clear()
    
    def get_current_track(self):
        """Get path of currently playing track"""
        if 0 <= self.current_index < len(self.playlist):
            return self.playlist[self.current_index]
        return None
    
    def get_track_count(self):
        """Get total number of tracks in playlist"""
        return len(self.playlist)
    
    def get_track_duration_ms(self, file_path):
        """
        Get cached duration or compute and cache it.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Duration in milliseconds, or 0 if unknown
        """
        if file_path in self.track_durations:
            return self.track_durations[file_path]
        return 0
    
    def set_track_duration_ms(self, file_path, duration_ms):
        """Cache duration for a track"""
        self.track_durations[file_path] = duration_ms
    
    def _clear_track_caches(self, file_path):
        """Clear all cached data for a track"""
        self.track_durations.pop(file_path, None)
        self.album_art_pixmap_cache.pop(file_path, None)
        self.dominant_color_cache.pop(file_path, None)

"""
Settings management for Aurion music player.
Handles saving and loading user preferences.
"""

import json
import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)


class SettingsManager:
    """Manages application settings persistence"""
    
    DEFAULT_SETTINGS = {
        'saved_folder': None,
        'crossfade_duration': 0,
        'shuffle_mode': False,
        'repeat_mode': 0,
        'volume': 50,
    }
    
    def __init__(self, settings_file=None):
        """
        Initialize settings manager.
        
        Args:
            settings_file: Path to settings JSON file. Defaults to ~/.amberol_settings.json
        """
        if settings_file is None:
            settings_file = os.path.join(Path.home(), '.amberol_settings.json')
        
        self.settings_file = settings_file
        self.settings = dict(self.DEFAULT_SETTINGS)
        self.load()
    
    def load(self):
        """Load settings from file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    saved = json.load(f)
                    # Merge with defaults (in case new keys were added)
                    self.settings.update(saved)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to load settings from %s: %s", self.settings_file, exc)
            # If loading fails, use defaults
            self.settings = dict(self.DEFAULT_SETTINGS)
    
    def save(self):
        """Save settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Failed to save settings to %s: %s", self.settings_file, exc)
    
    def get(self, key, default=None):
        """
        Get setting value.
        
        Args:
            key: Setting key
            default: Default value if key not found
            
        Returns:
            Setting value or default
        """
        return self.settings.get(key, default or self.DEFAULT_SETTINGS.get(key))
    
    def set(self, key, value):
        """
        Set setting value.
        
        Args:
            key: Setting key
            value: New value
        """
        self.settings[key] = value
    
    def set_saved_folder(self, folder_path):
        """Set the user's music folder"""
        self.set('saved_folder', folder_path)
    
    def get_saved_folder(self):
        """Get the user's music folder"""
        return self.get('saved_folder')
    
    def set_crossfade_duration(self, seconds):
        """Set crossfade duration in seconds"""
        self.set('crossfade_duration', seconds)
    
    def get_crossfade_duration(self):
        """Get crossfade duration in seconds"""
        return self.get('crossfade_duration', 0)
    
    def set_shuffle_mode(self, enabled):
        """Set shuffle mode state"""
        self.set('shuffle_mode', enabled)
    
    def get_shuffle_mode(self):
        """Get shuffle mode state"""
        return self.get('shuffle_mode', False)
    
    def set_repeat_mode(self, mode):
        """
        Set repeat mode.
        
        Args:
            mode: 0 = no repeat, 1 = repeat all, 2 = repeat one
        """
        self.set('repeat_mode', mode)
    
    def get_repeat_mode(self):
        """Get repeat mode (0=none, 1=all, 2=one)"""
        return self.get('repeat_mode', 0)
    
    def set_volume(self, volume):
        """Set volume level (0-100)"""
        self.set('volume', volume)
    
    def get_volume(self):
        """Get volume level (0-100)"""
        return self.get('volume', 50)

"""
FFmpeg/FFprobe detection and management.
Supports system-installed ffmpeg, local binaries, and user-specified paths.
Works cross-platform (Windows, Linux, macOS).
"""

from __future__ import annotations

import sys
import shutil
from pathlib import Path
from typing import Optional, List


class FFmpegManager:
    """Manages FFmpeg and FFprobe binary detection and usage"""
    
    def __init__(self):
        self.ffmpeg_path: Optional[str] = None
        self.ffprobe_path: Optional[str] = None
        self._detected = False
    
    def detect(self, local_ffmpeg_dir: Optional[Path] = None) -> bool:
        """
        Detect ffmpeg and ffprobe binaries.
        
        Priority order:
        1. Local ffmpeg folder (if provided)
        2. System PATH
        3. Return False if not found
        
        Args:
            local_ffmpeg_dir: Path to local ffmpeg folder (e.g., project/ffmpeg/)
            
        Returns:
            True if both ffmpeg and ffprobe are found, False otherwise
        """
        if self._detected:
            return self.ffmpeg_path is not None and self.ffprobe_path is not None
        
        # Try local ffmpeg folder first
        if local_ffmpeg_dir and local_ffmpeg_dir.exists():
            ffmpeg = self._find_in_directory(local_ffmpeg_dir, 'ffmpeg')
            ffprobe = self._find_in_directory(local_ffmpeg_dir, 'ffprobe')
            if ffmpeg and ffprobe:
                self.ffmpeg_path = str(ffmpeg)
                self.ffprobe_path = str(ffprobe)
                self._detected = True
                return True
        
        # Try system PATH
        ffmpeg = shutil.which('ffmpeg')
        ffprobe = shutil.which('ffprobe')
        if ffmpeg and ffprobe:
            self.ffmpeg_path = ffmpeg
            self.ffprobe_path = ffprobe
            self._detected = True
            return True
        
        self._detected = True
        return False
    
    def set_custom_path(self, ffmpeg_dir: Path) -> bool:
        """
        Set custom path to ffmpeg directory.
        
        Args:
            ffmpeg_dir: Path to directory containing ffmpeg and ffprobe binaries
            
        Returns:
            True if both binaries found at custom path, False otherwise
        """
        if not ffmpeg_dir.exists():
            return False
        
        ffmpeg = self._find_in_directory(ffmpeg_dir, 'ffmpeg')
        ffprobe = self._find_in_directory(ffmpeg_dir, 'ffprobe')
        
        if ffmpeg and ffprobe:
            self.ffmpeg_path = str(ffmpeg)
            self.ffprobe_path = str(ffprobe)
            return True
        
        return False
    
    def get_ffmpeg(self) -> Optional[str]:
        """Get path to ffmpeg binary"""
        return self.ffmpeg_path
    
    def get_ffprobe(self) -> Optional[str]:
        """Get path to ffprobe binary"""
        return self.ffprobe_path
    
    def is_available(self) -> bool:
        """Check if both ffmpeg and ffprobe are available"""
        return self.ffmpeg_path is not None and self.ffprobe_path is not None
    
    @staticmethod
    def _find_in_directory(directory: Path, binary_name: str) -> Optional[Path]:
        """
        Find binary in directory, accounting for OS-specific executable names.
        
        Args:
            directory: Directory to search
            binary_name: Name of binary (without .exe extension)
            
        Returns:
            Path to binary if found, None otherwise
        """
        # Windows uses .exe extension
        if sys.platform == 'win32':
            candidate = directory / f"{binary_name}.exe"
            if candidate.exists() and candidate.is_file():
                return candidate
        
        # Unix-like systems don't use extension
        candidate = directory / binary_name
        if candidate.exists() and candidate.is_file():
            return candidate
        
        return None
    
    @staticmethod
    def get_system_search_paths() -> List[str]:
        """Get list of standard system paths to search for ffmpeg"""
        paths = []
        
        if sys.platform == 'win32':
            # Windows common locations
            paths.extend([
                r"C:\ffmpeg\bin",
                r"C:\Program Files\ffmpeg\bin",
                r"C:\Program Files (x86)\ffmpeg\bin",
            ])
        elif sys.platform == 'darwin':
            # macOS common locations
            paths.extend([
                "/usr/local/bin",
                "/usr/bin",
                "/opt/homebrew/bin",  # M1/M2 Macs
            ])
        else:
            # Linux and other Unix-like systems
            paths.extend([
                "/usr/local/bin",
                "/usr/bin",
                "/snap/bin",
            ])
        
        return paths


# Global instance
_manager = FFmpegManager()


def init_ffmpeg(local_ffmpeg_dir: Optional[Path] = None) -> bool:
    """
    Initialize ffmpeg detection.
    
    Args:
        local_ffmpeg_dir: Path to local ffmpeg folder
        
    Returns:
        True if ffmpeg/ffprobe are available, False otherwise
    """
    return _manager.detect(local_ffmpeg_dir)


def get_ffmpeg_path() -> Optional[str]:
    """Get path to ffmpeg binary"""
    return _manager.get_ffmpeg()


def get_ffprobe_path() -> Optional[str]:
    """Get path to ffprobe binary"""
    return _manager.get_ffprobe()


def set_ffmpeg_path(ffmpeg_dir: Path) -> bool:
    """
    Set custom ffmpeg directory path.
    
    Args:
        ffmpeg_dir: Path to directory containing ffmpeg and ffprobe
        
    Returns:
        True if successful, False otherwise
    """
    return _manager.set_custom_path(ffmpeg_dir)


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg/ffprobe are available"""
    return _manager.is_available()


def get_search_suggestions() -> List[str]:
    """Get list of common system paths to suggest to user"""
    return _manager.get_system_search_paths()

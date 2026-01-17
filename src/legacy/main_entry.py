"""
Aurion - Modern Music Player
Main entry point for the application.
"""

import sys
import os
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from gui_config import init_config
from ffmpeg_manager import init_ffmpeg, set_ffmpeg_path, get_search_suggestions
from ffmpeg_locator_dialog import FFmpegLocatorDialog
from player_main import AmberolPlayer


def initialize_ffmpeg():
    """Initialize and detect FFmpeg installation"""
    local_ffmpeg_dir = Path(__file__).parent / "ffmpeg"
    if init_ffmpeg(local_ffmpeg_dir):
        return True
    
    # FFmpeg not found, prompt user
    dialog = FFmpegLocatorDialog(None, get_search_suggestions())
    if dialog.exec_() == FFmpegLocatorDialog.Accepted:
        if set_ffmpeg_path(dialog.get_selected_path()):
            return True
    
    return False


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Initialize GUI configuration based on screen
    init_config()
    
    # Check FFmpeg availability
    if not initialize_ffmpeg():
        print("ERROR: FFmpeg is required to run this application")
        sys.exit(1)
    
    # Set application icon
    icons_dir = (Path(__file__).parent / "Icons").resolve()
    logo_ico_path = str(icons_dir / "logo.ico")
    if os.path.exists(logo_ico_path):
        app.setWindowIcon(QIcon(logo_ico_path))
    
    # Create and show main window
    window = AmberolPlayer()
    window.show()
    
    # Run application
    exit_code = getattr(app, 'exec_', app.exec)()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Aurion - A sleek, feature-rich music player for Linux, Windows, and macOS

Main application entry point that launches the music player.
"""

import sys
import os
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

# Import FFmpeg initialization and configuration
from src.config.ffmpeg_manager import init_ffmpeg, set_ffmpeg_path, get_search_suggestions
from src.config.gui_config import init_config, get_config
from src.config.ffmpeg_locator_dialog import FFmpegLocatorDialog

# Import the main player window
from src.player_main import AmberolPlayer


# Set Windows AppUserModelID before creating QApplication
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.andrewdore.aurion")
except Exception:
    pass


def initialize_application():
    """Initialize application settings and FFmpeg"""
    init_config()
    
    # Initialize ffmpeg paths (try system first, then local, then prompt user)
    local_ffmpeg_dir = Path(__file__).parent / "ffmpeg"
    if not init_ffmpeg(local_ffmpeg_dir):
        # FFmpeg not found in system or local directory, prompt user
        dialog = FFmpegLocatorDialog(None, get_search_suggestions())
        if dialog.exec_() == FFmpegLocatorDialog.Accepted:
            if not set_ffmpeg_path(dialog.get_selected_path()):
                print("ERROR: Selected directory does not contain ffmpeg and ffprobe")
                sys.exit(1)
        else:
            print("ERROR: FFmpeg is required to run this application")
            sys.exit(1)


def setup_application_icon(app):
    """Set the application window icon"""
    try:
        icons_dir = (Path(__file__).parent / "src" / "Icons").resolve()
        logo_ico_path = str(icons_dir / "logo.ico")
        if os.path.exists(logo_ico_path):
            app.setWindowIcon(QIcon(logo_ico_path))
    except Exception:
        pass


def setup_gstreamer():
    """
    Configure GStreamer environment variables for Linux PyInstaller builds.
    This ensures that the bundled GStreamer plugins are correctly located.
    """
    if sys.platform.startswith('linux') and getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS
        
        # Set the GStreamer plugin path to the bundled 'gst-plugins' directory
        gst_plugins_path = os.path.join(bundle_dir, 'gst-plugins')
        if os.path.exists(gst_plugins_path):
            os.environ['GST_PLUGIN_SYSTEM_PATH'] = gst_plugins_path
        
        # Set the plugin scanner path
        gst_scanner_path = os.path.join(bundle_dir, 'gst-plugin-scanner')
        if os.path.exists(gst_scanner_path):
            os.environ['GST_PLUGIN_SCANNER'] = gst_scanner_path


def main():
    """Main application entry point"""
    # Configure GStreamer for Linux frozen builds
    setup_gstreamer()
    
    app = QApplication(sys.argv)
    
    # Initialize application settings and FFmpeg
    initialize_application()
    
    # Set application icon
    setup_application_icon(app)
    
    # Create and show main window
    player = AmberolPlayer()
    player.show()
    
    # Run application event loop
    exit_code = getattr(app, 'exec_', app.exec)()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

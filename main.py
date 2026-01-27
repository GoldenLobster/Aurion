#!/usr/bin/env python3
"""
Aurion - A sleek, feature-rich music player for Linux, Windows, and macOS

Main application entry point that launches the music player.
"""

import sys
import os
import tempfile
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

# Import FFmpeg initialization and configuration
from src.config.ffmpeg_manager import init_ffmpeg, set_ffmpeg_path, get_search_suggestions
from src.config.gui_config import init_config
from src.config.ffmpeg_locator_dialog import FFmpegLocatorDialog

# Import the main player window
from src.player_main import AmberolPlayer


# Set Windows AppUserModelID before creating QApplication
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.andrewdore.aurion")
except (AttributeError, OSError):
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
    except (OSError, RuntimeError):
        pass


def setup_gstreamer():
    """
    Configure GStreamer environment variables for Linux PyInstaller builds.
    This ensures that the bundled GStreamer plugins are correctly located.
    """
    if sys.platform.startswith('linux'):
        # For frozen builds (PyInstaller bundles)
        if getattr(sys, 'frozen', False):
            bundle_dir = sys._MEIPASS
            
            # Set the GStreamer plugin paths (check multiple locations)
            plugin_paths = [
                os.path.join(bundle_dir, 'gstreamer-1.0'),
                os.path.join(bundle_dir, 'lib', 'gstreamer-1.0'),
                os.path.join(bundle_dir, 'gst-plugins', 'gstreamer-1.0'),
                os.path.join(bundle_dir, 'gst-plugins'),
            ]
            
            valid_plugin_paths = [p for p in plugin_paths if os.path.exists(p)]
            
            if valid_plugin_paths:
                # Add system paths as fallback
                system_paths = [
                    '/usr/lib/gstreamer-1.0',
                    '/usr/lib/x86_64-linux-gnu/gstreamer-1.0',
                    '/usr/lib64/gstreamer-1.0',
                ]
                all_paths = ':'.join(valid_plugin_paths + system_paths)
                os.environ['GST_PLUGIN_SYSTEM_PATH'] = all_paths
            
            # Set the plugin scanner path
            scanner_paths = [
                os.path.join(bundle_dir, 'gstreamer-1.0', 'gst-plugin-scanner'),
                os.path.join(bundle_dir, 'lib', 'gstreamer-1.0', 'gst-plugin-scanner'),
                '/usr/lib/gstreamer-1.0/gst-plugin-scanner',
                '/usr/lib/x86_64-linux-gnu/gstreamer-1.0/gst-plugin-scanner',
            ]
            
            for scanner_path in scanner_paths:
                if os.path.exists(scanner_path):
                    os.environ['GST_PLUGIN_SCANNER'] = scanner_path
                    break
            
            # Set library path for bundled libraries
            lib_path = os.path.join(bundle_dir, 'lib')
            if os.path.exists(lib_path):
                existing_ld_path = os.environ.get('LD_LIBRARY_PATH', '')
                os.environ['LD_LIBRARY_PATH'] = lib_path + ':' + existing_ld_path if existing_ld_path else lib_path
        
        # Force a fresh registry in a writable location to prevent system conflicts
        registry_path = os.path.join(tempfile.gettempdir(), f'aurion_gst_registry_{os.getuid()}.bin')
        os.environ['GST_REGISTRY'] = registry_path
        
        # Disable plugin scanning delay (speeds up startup)
        os.environ['GST_PLUGIN_SCANNER_SHOULD_LOAD_MODULES'] = '0'
        
        # Clear GST_PLUGIN_PATH to avoid conflicts
        os.environ.pop('GST_PLUGIN_PATH', None)


def main():
    """Main application entry point"""
    # Configure GStreamer for Linux frozen builds
    setup_gstreamer()
    
    app = QApplication(sys.argv)
    
    # Set application metadata for all platforms
    app.setApplicationName("Aurion")
    app.setApplicationVersion("1.0.0")
    app.setApplicationDisplayName("Aurion")
    
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

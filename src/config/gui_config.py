"""
Dynamic GUI configuration system that adapts to system screen size and resolution.
All hardcoded GUI elements are now configurable based on the user's display properties.
"""

from PyQt5.QtWidgets import QApplication
from dataclasses import dataclass


@dataclass
class GUIConfig:
    """Dynamic GUI configuration based on screen dimensions"""
    
    # Window dimensions
    initial_window_width: int
    initial_window_height: int
    min_window_width: int
    min_window_height: int
    
    # Layout threshold - when to switch from sidebar queue to overlay queue
    # If window width >= this value, show queue as sidebar (40% of window)
    # Otherwise, show queue as overlay (full-screen modal)
    sidebar_overlay_threshold_width: int
    sidebar_overlay_threshold_height: int
    
    # Element sizes (relative to screen/window)
    queue_sidebar_width_percent: float  # 40% of window width
    album_art_size: int  # Fixed album art size
    header_height: int
    button_size: int  # Size of icon buttons
    window_control_button_size: int
    
    # Animation durations (in milliseconds)
    overlay_animation_duration: int
    queue_sidebar_animation_duration: int
    color_transition_duration: int
    
    # Spacing and margins
    header_margin_left: int
    header_margin_right: int
    header_margin_top: int
    header_margin_bottom: int
    button_spacing: int
    header_right_side_width: int
    header_right_side_padding: int
    
    # Resize margin for frameless window
    resize_margin: int
    
    # Timer intervals
    waveform_update_interval_ms: int  # Update waveform every N ms
    folder_watch_interval_ms: int  # Watch for new files every N ms


def calculate_gui_config() -> GUIConfig:
    """
    Calculate dynamic GUI configuration based on screen properties.
    Adapts to different monitor sizes and resolutions.
    """
    
    # Get screen geometry
    app = QApplication.instance()
    if not app:
        # Fallback if app not created yet
        return _get_default_config()
    
    screen = app.primaryScreen()
    if not screen:
        return _get_default_config()
    
    # Use availableGeometry to account for taskbars and other OS elements
    available_geom = screen.availableGeometry()
    screen_width = available_geom.width()
    screen_height = available_geom.height()
    screen_dpi = screen.logicalDotsPerInch()
    
    # Calculate scaling factor (assuming 96 DPI as baseline)
    dpi_scale = screen_dpi / 96.0
    
    # Determine window size based on screen size
    # Use 55-60% of screen width/height for default window (smaller to leave room, avoid fullscreen appearance)
    # But ensure it never exceeds available screen dimensions
    initial_width = max(700, min(int(screen_width * 0.55), screen_width - 100))
    initial_height = max(800, min(int(screen_height * 0.6), screen_height - 100))
    
    # Minimum window size (responsive for smaller screens)
    min_width = max(600, int(screen_width * 0.4))
    min_height = max(850, int(screen_height * 0.5))
    
    # Sidebar/overlay threshold - switch to overlay for narrower windows
    # Lower threshold so sidebar appears more easily (900px instead of 1100px)
    sidebar_threshold_width = int(900 * dpi_scale)
    sidebar_threshold_height = int(900 * dpi_scale)
    
    # Album art size - responsive to screen resolution
    # Small screens (1080p): ~300px, Large screens (4K): ~500px
    if screen_width >= 3840:  # 4K
        album_art = 500
    elif screen_width >= 2560:  # 2K
        album_art = 400
    elif screen_width >= 1920:  # 1080p
        album_art = 350
    else:  # 720p or smaller
        album_art = 300
    
    # Responsively scale button sizes based on screen DPI
    button_size = int(40 * dpi_scale)
    window_control_button_size = int(40 * dpi_scale)
    header_height = int(230 * dpi_scale)
    
    # Spacing and margins - scale with DPI
    header_margin = int(15 * dpi_scale)
    button_spacing = int(15 * dpi_scale)
    resize_margin = int(8 * dpi_scale)
    header_right_side_width = int(200 * dpi_scale)
    header_right_side_padding = int(20 * dpi_scale)
    
    return GUIConfig(
        initial_window_width=initial_width,
        initial_window_height=initial_height,
        min_window_width=min_width,
        min_window_height=min_height,
        
        sidebar_overlay_threshold_width=sidebar_threshold_width,
        sidebar_overlay_threshold_height=sidebar_threshold_height,
        
        queue_sidebar_width_percent=0.4,  # 40% of window width
        album_art_size=album_art,
        header_height=header_height,
        button_size=button_size,
        window_control_button_size=window_control_button_size,
        
        overlay_animation_duration=300,
        queue_sidebar_animation_duration=300,
        color_transition_duration=500,
        
        header_margin_left=header_margin,
        header_margin_right=header_margin,
        header_margin_top=int(10 * dpi_scale),
        header_margin_bottom=int(10 * dpi_scale),
        button_spacing=button_spacing,
        header_right_side_width=header_right_side_width,
        header_right_side_padding=header_right_side_padding,
        
        resize_margin=resize_margin,
        
        waveform_update_interval_ms=50,
        folder_watch_interval_ms=5000,
    )


def _get_default_config() -> GUIConfig:
    """Get default configuration for standard 1080p display"""
    return GUIConfig(
        initial_window_width=1056,
        initial_window_height=1130,
        min_window_width=700,
        min_window_height=1180,
        
        sidebar_overlay_threshold_width=900,
        sidebar_overlay_threshold_height=900,
        
        queue_sidebar_width_percent=0.4,
        album_art_size=300,
        header_height=230,
        button_size=40,
        window_control_button_size=40,
        
        overlay_animation_duration=300,
        queue_sidebar_animation_duration=300,
        color_transition_duration=500,
        
        header_margin_left=15,
        header_margin_right=15,
        header_margin_top=10,
        header_margin_bottom=10,
        button_spacing=15,
        header_right_side_width=200,
        header_right_side_padding=20,
        
        resize_margin=8,
        
        waveform_update_interval_ms=50,
        folder_watch_interval_ms=5000,
    )


# Global config instance (initialized after QApplication creation)
_config: GUIConfig = None


def init_config() -> GUIConfig:
    """Initialize global configuration. Call after QApplication is created."""
    global _config
    _config = calculate_gui_config()
    return _config


def get_config() -> GUIConfig:
    """Get current GUI configuration. Returns default if not initialized."""
    global _config
    if _config is None:
        _config = _get_default_config()
    return _config

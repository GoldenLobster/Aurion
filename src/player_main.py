#!/usr/bin/env python3
"""
Aurion Music Player - Main window implementation

This module contains the AmberolPlayer QMainWindow class which orchestrates
all the UI components, playback control, and application logic.
"""

import sys
import os
import wave
import struct
import time
import random
import io
import json
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QSlider, QLabel, QFileDialog,
                             QListWidgetItem, QScrollArea,
                             QGraphicsOpacityEffect,
                             QToolButton, QLineEdit, QDialog)
from PyQt5.QtCore import Qt, QUrl, QTimer, QSize, QPoint, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QRect, QEvent
from PyQt5.QtGui import QPixmap, QPainter, QColor, QIcon, QCursor
from PyQt5.QtWidgets import QAction
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from mutagen import File as MutagenFile
from PIL import Image

# Import helper modules
from src.core.cache import LRUCache
from src.core.playlist import PlaylistManager
from src.ui.ui_widgets import WaveformWidget, QueueItemWidget, QueueWidget, BlurredBackground, ScalableAlbumArtLabel
from src.ui.ui_dialogs import OverlayPanel, SettingsTab, MiniControlBar, DownloaderTab
from src.audio.audio_metadata import extract_album_art
from src.config.gui_config import get_config

# Set Windows AppUserModelID before creating QApplication
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.andrewdore.aurion")
except (AttributeError, OSError):
    pass

class AmberolPlayer(QMainWindow):
    # UI Constants
    ALBUM_ART_CACHE_SIZE = 100
    DOMINANT_COLOR_CACHE_SIZE = 100
    ALBUM_ART_SIZE = 300
    FALLBACK_COLORS = [
        QColor(82, 148, 226),    # Blue
        QColor(168, 82, 226),    # Purple
        QColor(226, 82, 141),    # Pink
        QColor(226, 141, 82),    # Orange
        QColor(82, 226, 168),    # Teal
        QColor(141, 226, 82),    # Green
    ]
    ALBUM_ART_CROSSFADE_DURATION = 800  # milliseconds
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aurion")
        
        # Make window frameless BEFORE setting size
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        # Get dynamic GUI configuration
        self.gui_config = get_config()
        
        # Set window size based on screen configuration
        self.setMinimumSize(self.gui_config.min_window_width, self.gui_config.min_window_height)
        self.resize(self.gui_config.initial_window_width, self.gui_config.initial_window_height)
        
        # Enable mouse tracking for cursor changes on edge hover (no click needed)
        self.setMouseTracking(True)

        # Track resize interactions for frameless window
        self.resize_margin = self.gui_config.resize_margin
        self.resizing = False
        self.resize_direction = None
        self.resize_start_geom = None
        self.resize_start_pos = None

        # Observe mouse events across the window so edge hover/drag works over children
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
        
        # Initialize dual media players for seamless preloading
        self.active_player = QMediaPlayer()
        self.preload_player = QMediaPlayer()
        self.active_player.setVolume(50)
        self.preload_player.setVolume(50)
        
        # Track which player is active
        self.using_primary = True
        
        # Cache for preloaded background data (decoded/scaled pixmaps) with size limits
        self.playlist_manager = PlaylistManager(self.ALBUM_ART_CACHE_SIZE, self.DOMINANT_COLOR_CACHE_SIZE)
        self.album_art_pixmap_cache = self.playlist_manager.album_art_pixmap_cache
        self.dominant_color_cache = self.playlist_manager.dominant_color_cache

        # Audio file detection helpers
        self.audio_extensions = ('.mp3', '.flac', '.ogg', '.wav', '.m4a', '.aac', '.opus')
        self.temp_markers = ('.tmp', '.temp', '.part', '.ytdl', '.download')
        self._new_file_min_age_secs = 3  # require files to be older than this before importing

        # Icon paths (resolved to absolute paths to avoid lookup issues)
        self.icons_dir = (Path(__file__).parent / "Icons").resolve()
        
        # Set window icon using .ico file for proper Windows support
        logo_ico_path = str(self.icons_dir / "logo.ico")
        if os.path.exists(logo_ico_path):
            self.setWindowIcon(QIcon(logo_ico_path))
        
        self.icon_play = QIcon(str(self.icons_dir / "play.svg"))
        self.icon_pause = QIcon(str(self.icons_dir / "pause.svg"))
        self.icon_skip_fwd = QIcon(str(self.icons_dir / "skip-forward.svg"))
        self.icon_skip_back = QIcon(str(self.icons_dir / "skip-back.svg"))
        self.icon_shuffle = QIcon(str(self.icons_dir / "shuffle.svg"))
        self.icon_repeat_all = QIcon(str(self.icons_dir / "repeat.svg"))
        self.icon_repeat_one = QIcon(str(self.icons_dir / "repeat-1.svg"))
        self.icon_menu = QIcon(str(self.icons_dir / "menu.svg"))
        self.icon_plus = QIcon(str(self.icons_dir / "plus.svg"))
        self.icon_folder = QIcon(str(self.icons_dir / "folder.svg"))
        self.icon_settings = QIcon(str(self.icons_dir / "settings.svg"))
        self.icon_playing = QIcon(str(self.icons_dir / "playing.svg"))
        self.icon_volume_none = QIcon(str(self.icons_dir / "no-volume.svg"))
        self.icon_volume_low = QIcon(str(self.icons_dir / "low-to-medium-volume.svg"))
        self.icon_volume_high = QIcon(str(self.icons_dir / "medium-to-high-volume.svg"))

        # Playlist data
        self.playlist = []
        self.current_index = -1
        # Cache per-track durations in milliseconds for quick total queue time
        self.track_durations = {}
        self.shuffle_mode = False
        self.repeat_mode = 0
        self.shuffle_history = []
        self.shuffle_pool = []
        self.shuffle_seeded = False
        self.shuffle_anchor = None
        self.saved_folder = None  # Store user's chosen music folder
        
        # Queue sidebar visibility state (for large windows)
        self.queue_sidebar_visible = False
        self.user_toggled_sidebar = False  # Track if user manually toggled sidebar (vs auto-open on startup)
        
        # Track background size for optimization
        self._last_background_size = None
        
        # Color animation for background transitions
        self.color_animation = None
        
        # Album art crossfade animation (no state tracking needed)
        self.album_art_animation = None
        
        # Text labels (title and artist) crossfade animations
        self.text_animation = None
        
        # Queue sidebar slide animation
        self.queue_animation = None
        
        # Track pending deferred updates to prevent stale operations
        self.pending_update_id = 0
        
        # Window interaction states (for frameless window dragging)
        self.drag_position = QPoint()
        self.is_dragging_header = False

        # Crossfade settings/state
        self.crossfade_duration_secs = 0
        self.crossfade_timer = None
        self.crossfade_in_progress = False
        self.crossfade_target_index = None
        self.crossfade_start_time = 0.0
        
        # Text transition animation setting
        self.text_fade_enabled = True
        
        # Settings
        self.settings_file = os.path.join(Path.home(), '.amberol_settings.json')
        self.load_settings()
        
        # Setup UI
        self.init_ui()
        
        # Connect signals to active player
        self._connect_player_signals(self.active_player)
        
        # Timer for waveform updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_waveform)
        self.timer.start(self.gui_config.waveform_update_interval_ms)

        # Timer to watch the saved music folder for newly added downloads
        self.folder_watch_timer = QTimer()
        self.folder_watch_timer.timeout.connect(self._scan_saved_folder_for_changes)
        self.folder_watch_timer.start(self.gui_config.folder_watch_interval_ms)
        
        # Load files from saved folder if available
        if self.saved_folder and os.path.exists(self.saved_folder):
            self.load_folder_files(self.saved_folder)
    
    def _connect_player_signals(self, player):
        """Connect media player signals"""
        player.positionChanged.connect(self.position_changed)
        player.durationChanged.connect(self.duration_changed)
        player.stateChanged.connect(self.state_changed)
        player.mediaStatusChanged.connect(self.media_status_changed)
    
    def _disconnect_player_signals(self, player):
        """Disconnect media player signals"""
        try:
            player.positionChanged.disconnect(self.position_changed)
            player.durationChanged.disconnect(self.duration_changed)
            player.stateChanged.disconnect(self.state_changed)
            player.mediaStatusChanged.disconnect(self.media_status_changed)
        except Exception:
            pass

    def _reseed_shuffle_pool(self, preserve_current=True, reset_history=False):
        """Rebuild shuffle order so every track plays once before repeating."""
        if reset_history:
            self.shuffle_history.clear()
        if not self.shuffle_mode or not self.playlist:
            self.shuffle_pool = []
            self.shuffle_seeded = False
            self.shuffle_anchor = None
            return

        indices = list(range(len(self.playlist)))
        if preserve_current and 0 <= self.current_index < len(self.playlist):
            try:
                indices.remove(self.current_index)
            except ValueError:
                pass

        random.shuffle(indices)
        self.shuffle_pool = indices
        self.shuffle_seeded = True

    def _prepare_shuffle_pool(self, allow_reseed=False, reset_history=False):
        """Keep shuffle helpers in sync with the playlist, optionally reseeding when empty."""
        if not self.shuffle_mode:
            self.shuffle_pool = []
            self.shuffle_seeded = False
            self.shuffle_anchor = None
            return

        max_index = len(self.playlist)
        self.shuffle_pool = [
            i for i in self.shuffle_pool
            if 0 <= i < max_index and i != self.current_index
        ]

        if not self.shuffle_pool and allow_reseed:
            self._reseed_shuffle_pool(preserve_current=True, reset_history=reset_history)
    
    def _get_next_track_index(self):
        """Calculate the next track index based on current state"""
        if not self.playlist or self.current_index == -1:
            return -1

        if self.repeat_mode == 2:
            return self.current_index
        
        if self.shuffle_mode:
            self._prepare_shuffle_pool(allow_reseed=(not self.shuffle_seeded) or self.repeat_mode == 1)
            if not self.shuffle_pool:
                return -1
            return self.shuffle_pool[-1]

        next_idx = self.current_index + 1
        if next_idx >= len(self.playlist):
            if self.repeat_mode == 1:
                return 0
            return -1
        return next_idx
    
    def _preload_next_track(self):
        """Preload the next track and its background data in the background"""
        next_idx = self._get_next_track_index()
        if next_idx != -1 and 0 <= next_idx < len(self.playlist):
            next_file = self.playlist[next_idx]
            # Preload media
            self.preload_player.setMedia(QMediaContent(QUrl.fromLocalFile(next_file)))
            # Preload background data (album art + color) asynchronously
            QTimer.singleShot(0, lambda: self._preload_background_data(next_file))
    
    def _preload_background_data(self, file_path):
        """Preload album art and dominant color for a track (runs in background)"""
        # Skip if already cached
        if self.album_art_pixmap_cache.get(file_path) and self.dominant_color_cache.get(file_path):
            return
        
        # Extract album art (blocking I/O - but happens in background)
        album_art = self.extract_album_art(file_path)
        if album_art:
            # Decode image (blocking - but happens in background)
            pixmap = QPixmap()
            pixmap.loadFromData(album_art)
            
            if not pixmap.isNull():
                # Scale pixmap (blocking - but happens in background)
                scaled_pixmap = pixmap.scaled(self.ALBUM_ART_SIZE, self.ALBUM_ART_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                # Cache the ready-to-use pixmap
                self.album_art_pixmap_cache.set(file_path, scaled_pixmap)
                
                # Calculate dominant color (blocking PIL work - but happens in background)
                dominant_color = self.get_dominant_color(album_art)
                if dominant_color:
                    self.dominant_color_cache.set(file_path, dominant_color)
    
    def init_ui(self):
        # Main container
        main_container = QWidget()
        main_container.setMouseTracking(True)
        self.setCentralWidget(main_container)
        
        # Main layout - will be vertical with stacked views (player or settings) + optional mini control bar
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create background that covers entire main container
        self.background = BlurredBackground()
        self.background.setParent(main_container)
        self.background.lower()
        # Defer geometry setup until window is shown and laid out
        self.background_initialized = False
        
        # === STACKED VIEWS (Player or Settings) ===
        stacked_container = QWidget()
        stacked_container.setStyleSheet("background-color: transparent;")
        stacked_layout = QHBoxLayout(stacked_container)
        stacked_layout.setContentsMargins(0, 0, 0, 0)
        stacked_layout.setSpacing(0)
        
        # === MAIN PLAYER VIEW ===
        player_view = QWidget()
        player_view.setStyleSheet("background-color: transparent;")
        player_layout = QVBoxLayout(player_view)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.setSpacing(0)
        
        # Header with queue button
        header = QWidget()
        header.setFixedHeight(self.gui_config.header_height)
        header.setStyleSheet("background-color: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(self.gui_config.header_margin_left, 
                                        self.gui_config.header_margin_top, 
                                        self.gui_config.header_margin_right, 
                                        self.gui_config.header_margin_bottom)

        # Left side vertical layout for folder button and queue button stacked
        left_side_layout = QVBoxLayout()
        left_side_layout.setContentsMargins(0, 0, 0, 0)
        left_side_layout.setSpacing(self.gui_config.button_spacing)
        
        self.change_folder_btn = QToolButton()
        self.change_folder_btn.setIcon(self.icon_folder)
        self.change_folder_btn.setIconSize(QSize(20, 20))
        self.change_folder_btn.setToolTip("Change Music Folder")
        self.change_folder_btn.setFixedSize(self.gui_config.button_size, self.gui_config.button_size)
        self.change_folder_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.change_folder_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 20px;
                font-size: 18px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.change_folder_btn.clicked.connect(self.choose_folder)
        self.change_folder_btn.setVisible(False)
        left_side_layout.addWidget(self.change_folder_btn, alignment=Qt.AlignLeft)
        
        self.add_btn = QToolButton()
        self.add_btn.setIcon(self.icon_plus)
        self.add_btn.setIconSize(QSize(20, 20))
        self.add_btn.setFixedSize(self.gui_config.button_size, self.gui_config.button_size)
        self.add_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.add_btn.setToolTip("YouTube Music Downloader")
        self.add_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 20px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.add_btn.clicked.connect(self.toggle_downloader_tab)
        left_side_layout.addWidget(self.add_btn, alignment=Qt.AlignLeft)

        self.queue_btn = QToolButton()
        self.queue_btn.setIcon(self.icon_menu)
        self.queue_btn.setIconSize(QSize(20, 20))
        self.queue_btn.setFixedSize(self.gui_config.button_size, self.gui_config.button_size)
        self.queue_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.queue_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 20px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.queue_btn.clicked.connect(self.show_queue)
        left_side_layout.addWidget(self.queue_btn, alignment=Qt.AlignLeft)

        self.settings_btn = QToolButton()
        self.settings_btn.setIcon(self.icon_settings)
        self.settings_btn.setIconSize(QSize(20, 20))
        self.settings_btn.setFixedSize(self.gui_config.button_size, self.gui_config.button_size)
        self.settings_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.settings_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 20px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.settings_btn.clicked.connect(self.show_settings_window)
        left_side_layout.addWidget(self.settings_btn, alignment=Qt.AlignLeft)
        
        header_layout.addLayout(left_side_layout)

        header_layout.addStretch()

        
        # Create a vertical layout for the right side (window controls on top, menu below)
        right_side_layout = QVBoxLayout()
        right_side_layout.setContentsMargins(0, 0, 0, 0)
        right_side_layout.setSpacing(0)
        
        # Window control buttons (minimize, maximize, close)
        btn_style = """
            QToolButton {
                background-color: transparent;
                border: none;
                color: white;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """
        
        window_controls_layout = QHBoxLayout()
        window_controls_layout.setContentsMargins(0, 0, 0, 0)
        window_controls_layout.setSpacing(0)
        
        btn_size = self.gui_config.window_control_button_size
        icon_size = int(btn_size * 0.5)
        
        self.minimize_btn = QToolButton()
        self.minimize_btn.setIcon(QIcon(str(self.icons_dir / "minimize.svg")))

        self.minimize_btn.setIconSize(QSize(icon_size, icon_size))
        self.minimize_btn.setFixedSize(btn_size, btn_size)
        self.minimize_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.minimize_btn.setStyleSheet(btn_style)
        self.minimize_btn.clicked.connect(self.showMinimized)
        window_controls_layout.addWidget(self.minimize_btn)
        
        self.maximize_btn = QToolButton()
        self.maximize_btn.setIcon(QIcon(str(self.icons_dir / "maximize.svg")))
        self.maximize_btn.setIconSize(QSize(icon_size, icon_size))
        self.maximize_btn.setFixedSize(btn_size, btn_size)
        self.maximize_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.maximize_btn.setStyleSheet(btn_style)
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        window_controls_layout.addWidget(self.maximize_btn)
        
        self.close_btn = QToolButton()
        self.close_btn.setIcon(QIcon(str(self.icons_dir / "close.svg")))
        self.close_btn.setIconSize(QSize(icon_size, icon_size))
        self.close_btn.setFixedSize(btn_size, btn_size)
        self.close_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.close_btn.setStyleSheet(btn_style)
        self.close_btn.clicked.connect(self.close)
        window_controls_layout.addWidget(self.close_btn)
        
        right_side_layout.addLayout(window_controls_layout)
        right_side_layout.addStretch()
        
        header_layout.addLayout(right_side_layout)
        
        player_layout.addWidget(header)
        
        # Spacer
        player_layout.addStretch()
        
        # Album art
        art_container = QWidget()
        art_container.setStyleSheet("background-color: transparent;")
        art_layout = QVBoxLayout(art_container)
        art_layout.setAlignment(Qt.AlignCenter)
        
        # Store reference for layout updates during resize
        self.art_container = art_container

        art_widget = QWidget()
        # Don't set fixed size - will be calculated in resizeEvent
        self.art_widget = art_widget  # Store reference for resizing

        # Create two labels for crossfading
        self.art_a = ScalableAlbumArtLabel()
        self.art_a.setParent(art_widget)
        # Don't set fixed size - will be calculated in resizeEvent
        self.art_a.move(0, 0)  # Position at top-left of parent
        self.art_a.setAlignment(Qt.AlignCenter)
        self.art_a.setStyleSheet("""
            background-color: transparent;
            border-radius: 20px;
            font-size: 100px;
        """)
        self.art_a.setText("🎵")

        self.art_b = ScalableAlbumArtLabel()
        self.art_b.setParent(art_widget)
        # Don't set fixed size - will be calculated in resizeEvent
        self.art_b.move(0, 0)  # Position at same top-left of parent (overlay)
        self.art_b.setAlignment(Qt.AlignCenter)
        self.art_b.setStyleSheet(self.art_a.styleSheet())

        # Create opacity effects for each
        self.opacity_a = QGraphicsOpacityEffect(self.art_a)
        self.opacity_a.setOpacity(1.0)  # A starts visible
        self.art_a.setGraphicsEffect(self.opacity_a)

        self.opacity_b = QGraphicsOpacityEffect(self.art_b)
        self.opacity_b.setOpacity(0.0)  # B starts hidden
        self.art_b.setGraphicsEffect(self.opacity_b)
        # Track which art label is currently the visible/front label
        self._art_front = 'A'
        # Ensure stacking order aligns with initial opacities
        self.art_a.raise_()
        self.art_b.lower()
        
        art_layout.addWidget(art_widget)
        player_layout.addWidget(art_container)
        
        # Song info
        info_container = QWidget()
        info_container.setStyleSheet("background-color: transparent;")
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(30, 20, 30, 10)
        
        # Title labels with crossfade support (stacked)
        title_widget = QWidget()
        title_widget.setStyleSheet("background-color: transparent;")
        title_layout = QVBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        
        self.title_a = QLabel("No track playing")
        self.title_a.setAlignment(Qt.AlignCenter)
        self.title_a.setWordWrap(True)
        self.title_a.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: white;
            background-color: transparent;
        """)
        title_layout.addWidget(self.title_a)
        
        self.title_b = QLabel("No track playing")
        self.title_b.setAlignment(Qt.AlignCenter)
        self.title_b.setWordWrap(True)
        self.title_b.setStyleSheet(self.title_a.styleSheet())
        
        # Create opacity effects for title labels
        self.title_opacity_a = QGraphicsOpacityEffect(self.title_a)
        self.title_opacity_a.setOpacity(1.0)
        self.title_a.setGraphicsEffect(self.title_opacity_a)
        
        self.title_opacity_b = QGraphicsOpacityEffect(self.title_b)
        self.title_opacity_b.setOpacity(0.0)
        self.title_b.setGraphicsEffect(self.title_opacity_b)
        
        # Add title_b as overlay (absolute positioning within title_widget)
        self.title_b.setParent(title_widget)
        self.title_b.setGeometry(0, 0, title_widget.width(), title_widget.height())
        
        # Keep main title_a in layout for size reference
        self.title_front = 'A'
        
        info_layout.addWidget(title_widget)
        
        # Artist labels with crossfade support (stacked)
        artist_widget = QWidget()
        artist_widget.setStyleSheet("background-color: transparent;")
        artist_layout = QVBoxLayout(artist_widget)
        artist_layout.setContentsMargins(0, 0, 0, 0)
        artist_layout.setSpacing(0)
        
        self.artist_a = QLabel("")
        self.artist_a.setAlignment(Qt.AlignCenter)
        self.artist_a.setWordWrap(True)
        self.artist_a.setStyleSheet("""
            font-size: 16px;
            color: rgba(255, 255, 255, 0.7);
            margin-top: 5px;
            background-color: transparent;
        """)
        artist_layout.addWidget(self.artist_a)
        
        self.artist_b = QLabel("")
        self.artist_b.setAlignment(Qt.AlignCenter)
        self.artist_b.setWordWrap(True)
        self.artist_b.setStyleSheet(self.artist_a.styleSheet())
        
        # Create opacity effects for artist labels
        self.artist_opacity_a = QGraphicsOpacityEffect(self.artist_a)
        self.artist_opacity_a.setOpacity(1.0)
        self.artist_a.setGraphicsEffect(self.artist_opacity_a)
        
        self.artist_opacity_b = QGraphicsOpacityEffect(self.artist_b)
        self.artist_opacity_b.setOpacity(0.0)
        self.artist_b.setGraphicsEffect(self.artist_opacity_b)
        
        # Add artist_b as overlay
        self.artist_b.setParent(artist_widget)
        self.artist_b.setGeometry(0, 0, artist_widget.width(), artist_widget.height())
        
        self.artist_front = 'A'
        
        info_layout.addWidget(artist_widget)
        
        # Empty-state message (appears below artist label)
        self.empty_label = QLabel("No music loaded. Add files or choose a folder to get started.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("""
            font-size: 16px;
            color: rgba(255, 255, 255, 0.6);
            margin-top: 15px;
        """)
        self.empty_label.setVisible(False)
        info_layout.addWidget(self.empty_label)

        self.add_file_btn = QPushButton("Add File")
        self.add_file_btn.setFixedHeight(36)
        self.add_file_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.12);
                border: none;
                border-radius: 8px;
                color: white;
                font-size: 14px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.add_file_btn.clicked.connect(self.open_files)
        self.add_file_btn.setVisible(False)
        info_layout.addWidget(self.add_file_btn, alignment=Qt.AlignCenter)
        
        self.choose_folder_btn = QPushButton("Choose Folder")
        self.choose_folder_btn.setFixedHeight(36)
        self.choose_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.12);
                border: none;
                border-radius: 8px;
                color: white;
                font-size: 14px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.choose_folder_btn.clicked.connect(self.choose_folder)
        self.choose_folder_btn.setVisible(False)
        info_layout.addWidget(self.choose_folder_btn, alignment=Qt.AlignCenter)
        
        player_layout.addWidget(info_container)
        
        player_layout.addStretch()
        
        # Waveform
        waveform_container = QWidget()
        waveform_container.setStyleSheet("background-color: transparent;")
        waveform_layout = QVBoxLayout(waveform_container)
        waveform_layout.setContentsMargins(20, 10, 20, 10)
        
        self.waveform = WaveformWidget()
        self.waveform.seekRequested.connect(self.seek_to_position)
        waveform_layout.addWidget(self.waveform)
        
        # Time labels
        time_widget = QWidget()
        time_widget.setStyleSheet("background-color: transparent;")
        time_layout = QHBoxLayout(time_widget)
        time_layout.setContentsMargins(0, 5, 0, 0)
        
        self.current_time_label = QLabel("0:00")
        self.current_time_label.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.7);")
        time_layout.addWidget(self.current_time_label)
        
        time_layout.addStretch()
        
        self.total_time_label = QLabel("0:00")
        self.total_time_label.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.7);")
        time_layout.addWidget(self.total_time_label)
        
        waveform_layout.addWidget(time_widget)
        player_layout.addWidget(waveform_container)
        
        # Hide waveform initially (until music is added)
        waveform_container.setVisible(False)
        self.waveform_container = waveform_container
        
        # Controls
        controls_container = QWidget()
        controls_container.setStyleSheet("background-color: transparent;")
        controls_layout = QHBoxLayout(controls_container)
        controls_layout.setContentsMargins(20, 20, 20, 30)
        controls_layout.setAlignment(Qt.AlignCenter)
        controls_layout.setSpacing(15)
        
        btn_style = """
            QToolButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 20px;
                color: white;
                font-size: 14px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
            QToolButton:checked {
                background-color: rgba(82, 148, 226, 0.5);
            }
        """

        self.shuffle_btn = QToolButton()
        self.shuffle_btn.setIcon(self.icon_shuffle)
        self.shuffle_btn.setIconSize(QSize(20, 20))
        self.shuffle_btn.setFixedSize(40, 40)
        self.shuffle_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setStyleSheet(btn_style)
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        controls_layout.addWidget(self.shuffle_btn)
        
        self.prev_btn = QToolButton()
        self.prev_btn.setIcon(self.icon_skip_back)
        self.prev_btn.setIconSize(QSize(22, 22))
        self.prev_btn.setFixedSize(40, 40)
        self.prev_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.prev_btn.setStyleSheet(btn_style)
        self.prev_btn.clicked.connect(self.previous_track)
        controls_layout.addWidget(self.prev_btn)
        
        self.play_btn = QToolButton()
        self.play_btn.setIcon(self.icon_play)
        self.play_btn.setIconSize(QSize(26, 26))
        self.play_btn.setFixedSize(48, 48)
        self.play_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.play_btn.setStyleSheet(btn_style)
        self.play_btn.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.play_btn)
        
        self.next_btn = QToolButton()
        self.next_btn.setIcon(self.icon_skip_fwd)
        self.next_btn.setIconSize(QSize(22, 22))
        self.next_btn.setFixedSize(40, 40)
        self.next_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.next_btn.setStyleSheet(btn_style)
        self.next_btn.clicked.connect(self.next_track)
        controls_layout.addWidget(self.next_btn)
        
        self.repeat_btn = QToolButton()
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.setIcon(self.icon_repeat_all)
        self.repeat_btn.setIconSize(QSize(20, 20))
        self.repeat_btn.setFixedSize(36, 36)
        self.repeat_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.repeat_btn.setStyleSheet(btn_style)
        self.repeat_btn.clicked.connect(self.toggle_repeat)
        controls_layout.addWidget(self.repeat_btn)

        # Set initial icon states
        self._update_play_icon()
        self._update_shuffle_icon()
        self._update_repeat_icon()
        
        player_layout.addWidget(controls_container)
        
        # Volume
        volume_container = QWidget()
        volume_container.setStyleSheet("background-color: transparent;")
        volume_layout = QHBoxLayout(volume_container)
        volume_layout.setContentsMargins(30, 0, 30, 20)
        
        self.volume_icon = QLabel()
        self.volume_icon.setFixedSize(24, 24)
        self.volume_icon.setScaledContents(True)
        volume_icon_pixmap = self.icon_volume_low.pixmap(24, 24)
        self.volume_icon.setPixmap(volume_icon_pixmap)
        volume_layout.addWidget(self.volume_icon)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(82, 148, 226, 0.8);
                border-radius: 3px;
            }
        """)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_slider.valueChanged.connect(self._update_volume_icon)
        volume_layout.addWidget(self.volume_slider)
        
        player_layout.addWidget(volume_container)
        
        # === QUEUE WIDGET (reusable for both side-panel and overlay) ===
        self.queue_widget = QueueWidget()
        self.queue_widget.itemClicked.connect(self.play_selected)
        
        # === QUEUE CONTAINER (side-panel, shown only in large windows) ===
        queue_container = QWidget()
        # Width will be set dynamically to 40% of window width
        queue_container.setStyleSheet("background-color: rgba(30, 30, 30, 0.95);")
        queue_container_layout = QVBoxLayout(queue_container)
        queue_container_layout.setContentsMargins(0, 0, 0, 0)
        queue_container_layout.setSpacing(0)
        
        # Queue header for side panel
        queue_header = QWidget()
        queue_header.setFixedHeight(60)
        queue_header.setStyleSheet("background-color: transparent;")
        queue_header_layout = QHBoxLayout(queue_header)
        queue_header_layout.setContentsMargins(15, 10, 15, 10)
        
        queue_title = QLabel("Queue")
        queue_title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        queue_header_layout.addWidget(queue_title)
        
        # Search input
        self.queue_search = QLineEdit()
        self.queue_search.setPlaceholderText("Search")
        self.queue_search.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 15px;
                color: white;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                background-color: rgba(255, 255, 255, 0.15);
            }
        """)
        self.queue_search.setMaximumWidth(200)
        self.queue_search.textChanged.connect(self.filter_queue)
        queue_header_layout.addWidget(self.queue_search)
        
        queue_header_layout.addStretch()

        # Remaining playtime display for side queue
        self.queue_total_label = QLabel("Remaining 0:00")
        self.queue_total_label.setStyleSheet("color: rgba(255, 255, 255, 0.75); font-size: 13px;")
        queue_header_layout.addWidget(self.queue_total_label)
        
        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 100, 100, 0.2);
                border: none;
                border-radius: 5px;
                color: white;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: rgba(255, 100, 100, 0.3);
            }
        """)
        reset_btn.clicked.connect(self.reset_app)
        queue_header_layout.addWidget(reset_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 5px;
                color: white;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        clear_btn.clicked.connect(self.clear_playlist)
        queue_header_layout.addWidget(clear_btn)
        
        queue_container_layout.addWidget(queue_header)
        
        # Queue list in scroll area (side panel)
        self.side_scroll_area = QScrollArea()
        self.side_scroll_area.setWidgetResizable(True)
        self.side_scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.side_scroll_area.setWidget(self.queue_widget)
        
        queue_container_layout.addWidget(self.side_scroll_area)
        
        # === ADD PLAYER AND QUEUE TO STACKED LAYOUT ===
        stacked_layout.addWidget(player_view, 1)  # Player view takes most space
        stacked_layout.addWidget(queue_container, 0)  # Queue doesn't stretch
        queue_container.setVisible(False)
        
        # === SETTINGS TAB ===
        self.settings_tab = SettingsTab(parent=None, initial_value=self.crossfade_duration_secs, text_fade_enabled=self.text_fade_enabled)
        self.settings_tab.crossfadeChanged.connect(self.set_crossfade_duration)
        self.settings_tab.textFadeChanged.connect(self.set_text_fade_enabled)
        self.settings_tab.closeRequested.connect(self.close_settings_tab)
        self.settings_tab.setVisible(False)
        stacked_layout.addWidget(self.settings_tab, 1)  # Stretch to fill
        
        # === DOWNLOADER TAB ===
        self.downloader_tab = DownloaderTab(parent=None)
        self.downloader_tab.closeRequested.connect(self.close_downloader_tab)
        self.downloader_tab.setVisible(False)
        stacked_layout.addWidget(self.downloader_tab, 1)  # Stretch to fill
        
        # === MINI CONTROL BAR ===
        # Prepare icons dict for mini control bar
        icons_dict = {
            'play': self.icon_play,
            'pause': self.icon_pause,
            'skip_fwd': self.icon_skip_fwd,
            'skip_back': self.icon_skip_back,
            'shuffle': self.icon_shuffle,
            'repeat_all': self.icon_repeat_all,
            'repeat_one': self.icon_repeat_one,
            'volume_none': self.icon_volume_none,
            'volume_low': self.icon_volume_low,
            'volume_high': self.icon_volume_high,
        }
        self.mini_control_bar = MiniControlBar(icons=icons_dict)
        self.mini_control_bar.playPauseRequested.connect(self.toggle_play)
        self.mini_control_bar.nextTrackRequested.connect(self.next_track)
        self.mini_control_bar.previousTrackRequested.connect(self.previous_track)
        self.mini_control_bar.shuffleToggleRequested.connect(self.toggle_shuffle)
        self.mini_control_bar.repeatToggleRequested.connect(self.toggle_repeat)
        self.mini_control_bar.volumeChanged.connect(self._on_mini_volume_changed)
        self.mini_control_bar.setVisible(False)  # Hidden until settings tab is opened
        # Sync mini control bar volume to match main window
        self.mini_control_bar.volume_slider.blockSignals(True)
        self.mini_control_bar.volume_slider.setValue(self.volume_slider.value())
        self.mini_control_bar.volume_slider.blockSignals(False)
        self.mini_control_bar.update_volume_icon(self.volume_slider.value())
        
        # Add stacked container and mini control bar to main layout
        main_layout.addWidget(stacked_container, 1)  # Stretch to fill
        main_layout.addWidget(self.mini_control_bar, 0)  # Mini bar at bottom
        
        # Store references for responsive behavior
        self.queue_container = queue_container
        self.player_view = player_view
        self.stacked_container = stacked_container
        self.stacked_layout = stacked_layout
        self.main_layout = main_layout
        
        # Create dark backdrop for overlay mode
        self.overlay_backdrop = QLabel(main_container)
        self.overlay_backdrop.setStyleSheet("background-color: rgba(0, 0, 0, 0.7);")
        self.overlay_backdrop.setVisible(False)
        self.overlay_backdrop.lower()  # Keep below overlay but above player
        
        # Opacity effect for backdrop fade animation
        self.backdrop_opacity = QGraphicsOpacityEffect(self.overlay_backdrop)
        self.backdrop_opacity.setOpacity(0.0)
        self.overlay_backdrop.setGraphicsEffect(self.backdrop_opacity)
        self.backdrop_animation = None
        
        # Create overlay panel (for small windows)
        self.overlay_panel = OverlayPanel(self.queue_widget)
        # Parent overlay to main container so it can cover it entirely
        self.overlay_panel.setParent(main_container)
        # Connect overlay panel buttons to main player methods
        self.overlay_panel.reset_btn.clicked.connect(self.reset_app)
        self.overlay_panel.clear_btn.clicked.connect(self.clear_playlist)
        # Connect overlay search to queue filter
        try:
            self.overlay_panel.search_input.textChanged.connect(self.filter_queue)
        except Exception:
            pass
        # Reattach queue to side panel when overlay hides
        try:
            self.overlay_panel.overlayClosed.connect(self._reattach_queue_to_side_panel)
            self.overlay_panel.overlayClosed.connect(self._hide_overlay_backdrop)
        except Exception:
            pass
        
        # Ensure overlay is hidden on startup without animation
        self.overlay_panel.setVisible(False)
        
        # Start with sidebar queue closed (will be opened when user clicks menu button)
        self.queue_container.setVisible(False)
        self.queue_sidebar_visible = False
        self._reattach_queue_to_side_panel()
        
        # Hide legacy menu bar; use on-screen button instead
        self.menuBar().setVisible(False)

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Track settings tab state
        self.settings_tab_open = False
        
        # Track downloader tab state
        self.downloader_tab_open = False

        self.update_empty_state()
    
    def _is_in_header_area(self, global_pos):
        local_pos = self.mapFromGlobal(global_pos)
        
        # Don't allow dragging if in the mini control bar area
        if self.mini_control_bar.isVisible():
            mini_bar_y = self.height() - self.mini_control_bar.height()
            if local_pos.y() >= mini_bar_y:
                return False
        
        # If settings or downloader tab is open, allow dragging at the top (title area with close button)
        # but don't allow dragging over sliders and interactive controls
        if self.settings_tab_open or self.downloader_tab_open:
            # Only allow dragging in the top 100px where the title and close button are
            if local_pos.y() < 100:
                # Check if we're clicking on the close button area
                close_button_area = 1200  # Approximate x position of close button
                if local_pos.x() > close_button_area:
                    return False
                return True
            return False
        
        header_height = 230
        window_width = self.width()
        right_side_width = 200
        return local_pos.y() < header_height and local_pos.x() < (window_width - right_side_width - 20)

    def _is_over_header_control(self, global_pos):
        """Return True when the cursor is over any header control button."""
        controls = [
            getattr(self, "change_folder_btn", None),
            getattr(self, "add_btn", None),
            getattr(self, "queue_btn", None),
            getattr(self, "settings_btn", None),
            getattr(self, "minimize_btn", None),
            getattr(self, "maximize_btn", None),
            getattr(self, "close_btn", None),
        ]
        for btn in controls:
            if btn is None or not btn.isVisible():
                continue
            try:
                if btn.rect().contains(btn.mapFromGlobal(global_pos)):
                    return True
            except Exception:
                continue
        return False

    def _get_resize_region(self, global_pos):
        if self.isMaximized():
            return None
        local_pos = self.mapFromGlobal(global_pos)
        margin = self.resize_margin
        rect = self.rect()
        on_left = local_pos.x() <= margin
        on_right = local_pos.x() >= rect.width() - margin
        on_top = local_pos.y() <= margin
        on_bottom = local_pos.y() >= rect.height() - margin
        if on_top and on_left:
            return "top_left"
        if on_top and on_right:
            return "top_right"
        if on_bottom and on_left:
            return "bottom_left"
        if on_bottom and on_right:
            return "bottom_right"
        if on_left:
            return "left"
        if on_right:
            return "right"
        if on_top:
            return "top"
        if on_bottom:
            return "bottom"
        return None

    def _update_cursor_shape(self, global_pos):
        if self.resizing:
            return
        region = self._get_resize_region(global_pos)
        if not region:
            self.unsetCursor()
            return
        cursor_map = {
            "left": Qt.SizeHorCursor,
            "right": Qt.SizeHorCursor,
            "top": Qt.SizeVerCursor,
            "bottom": Qt.SizeVerCursor,
            "top_left": Qt.SizeFDiagCursor,
            "bottom_right": Qt.SizeFDiagCursor,
            "top_right": Qt.SizeBDiagCursor,
            "bottom_left": Qt.SizeBDiagCursor,
        }
        self.setCursor(cursor_map.get(region, Qt.ArrowCursor))

    def _start_resize(self, global_pos, direction):
        self.resizing = True
        self.resize_direction = direction
        self.resize_start_geom = self.geometry()
        self.resize_start_pos = global_pos
        self.grabMouse()
        self._update_cursor_shape(global_pos)

    def _perform_resize(self, global_pos):
        if not self.resize_start_geom or not self.resize_direction:
            return
        delta = global_pos - self.resize_start_pos
        geom = QRect(self.resize_start_geom)
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()

        if "left" in self.resize_direction:
            new_x = geom.x() + delta.x()
            max_x = geom.right() - min_w
            new_x = min(new_x, max_x)
            geom.setLeft(new_x)
        if "right" in self.resize_direction:
            new_width = max(min_w, geom.width() + delta.x())
            geom.setWidth(new_width)
        if "top" in self.resize_direction:
            new_y = geom.y() + delta.y()
            max_y = geom.bottom() - min_h
            new_y = min(new_y, max_y)
            geom.setTop(new_y)
        if "bottom" in self.resize_direction:
            new_height = max(min_h, geom.height() + delta.y())
            geom.setHeight(new_height)

        self.setGeometry(geom)

    def _perform_header_drag(self, global_pos):
        if not self.isMaximized():
            self.move(global_pos - self.drag_position)

    def _handle_mouse_press_common(self, event):
        if event.button() != Qt.LeftButton:
            return False

        global_pos = event.globalPos()
        resize_region = self._get_resize_region(global_pos)
        if resize_region:
            self._start_resize(global_pos, resize_region)
            return True

        if self._is_in_header_area(global_pos) and not self.isMaximized():
            target_widget = self.childAt(self.mapFromGlobal(global_pos))
            if isinstance(target_widget, (QToolButton, QPushButton)):
                return False
            if self._is_over_header_control(global_pos):
                return False
            self.drag_position = global_pos - self.frameGeometry().topLeft()
            self.is_dragging_header = True
            return True

        return False

    def _handle_mouse_move_common(self, event):
        global_pos = event.globalPos()
        if self.resizing:
            self._perform_resize(global_pos)
            return True
        if self.is_dragging_header:
            self._perform_header_drag(global_pos)
            return True
        self._update_cursor_shape(global_pos)
        return False

    def _handle_mouse_release_common(self, event):
        if event.button() != Qt.LeftButton:
            return False

        handled = False
        if self.resizing:
            self.resizing = False
            self.resize_direction = None
            self.resize_start_geom = None
            self.resize_start_pos = None
            try:
                self.releaseMouse()
            except Exception:
                pass
            handled = True

        if self.is_dragging_header:
            self.is_dragging_header = False
            handled = True

        self._update_cursor_shape(QCursor.pos())
        return handled

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            if isinstance(obj, QWidget) and obj.window() is self:
                if event.type() == QEvent.MouseButtonPress and self._handle_mouse_press_common(event):
                    event.accept()
                    return True
                if event.type() == QEvent.MouseMove and self._handle_mouse_move_common(event):
                    event.accept()
                    return True
                if event.type() == QEvent.MouseButtonRelease and self._handle_mouse_release_common(event):
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        """Initialize background after window is shown and laid out"""
        super().showEvent(event)
        
        # Force the correct window size - the window manager or frameless hint might have overridden it
        self.resize(self.gui_config.initial_window_width, self.gui_config.initial_window_height)
        
        if not self.background_initialized:
            # Now window and main container are properly sized
            main_container = self.centralWidget()
            self.background.setGeometry(0, 0, main_container.width(), main_container.height())
            self.background.set_from_color(QColor(30, 30, 30, 200), use_gradient=False)
            self.background.show()
            self.background_initialized = True
            
            # Force layout processing to ensure all widget geometries are properly calculated
            # This fixes issues with button hitboxes and album art sizing on startup
            main_container.updateGeometry()
            QApplication.processEvents()
            
            # Initialize responsive layout after UI is fully set up
            self._update_responsive_layout()
            
            # Defer final geometry updates to ensure everything is fully laid out
            # This is critical for button hitboxes and album art sizing
            QTimer.singleShot(0, self._finalize_startup_geometry)

        # Set initial album art size based on available space
        self._update_art_size()
    
    def _finalize_startup_geometry(self):
        """Final geometry updates after the event loop has fully processed the initial layout."""
        # Force all widgets to recalculate their geometry
        self.centralWidget().updateGeometry()
        self._update_art_size()
        QApplication.processEvents()
    
    def toggle_maximize(self):
        """Toggle between maximized and normal window state"""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
    
    def mousePressEvent(self, event):
        handled = self._handle_mouse_press_common(event)
        if handled:
            return
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        handled = self._handle_mouse_move_common(event)
        if handled:
            event.accept()
            return
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        handled = self._handle_mouse_release_common(event)
        if handled:
            event.accept()
            return
        super().mouseReleaseEvent(event)
    
    def init_menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: rgba(30, 30, 30, 0.95);
                color: white;
            }
            QMenuBar::item:selected {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QMenu {
                background-color: rgba(30, 30, 30, 0.95);
                color: white;
            }
            QMenu::item:selected {
                background-color: rgba(82, 148, 226, 0.5);
            }
        """)
        
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open Files", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_files)
        file_menu.addAction(open_action)
        
        open_folder_action = QAction("Open Folder", self)
        open_folder_action.setShortcut("Ctrl+Shift+O")
        open_folder_action.triggered.connect(self.open_folder)
        file_menu.addAction(open_folder_action)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        main_container = self.centralWidget()
        if hasattr(self, 'background') and main_container:
            new_size = (main_container.width(), main_container.height())
            # Only update background if size actually changed
            if self._last_background_size != new_size:
                self._last_background_size = new_size
                self.background.setGeometry(0, 0, new_size[0], new_size[1])
                use_gradient = getattr(self.background, "last_use_gradient", True)
                self.background.set_from_color(self.background.base_color, use_gradient=use_gradient)
                # Update overlay geometry if visible
                if hasattr(self, 'overlay_panel') and self.overlay_panel.isVisible():
                    self.overlay_panel.update_geometry_to_parent()
                # Update backdrop geometry
                if hasattr(self, 'overlay_backdrop'):
                    self.overlay_backdrop.setGeometry(0, 0, new_size[0], new_size[1])
        
        # Update queue sidebar width based on config percentage of window
        if hasattr(self, 'queue_container'):
            queue_width = int(self.width() * self.gui_config.queue_sidebar_width_percent)
            self.queue_container.setFixedWidth(queue_width)
        
        # Resize album art proportionally with window and available width
        self._update_art_size()
        
        # Update responsive layout
        self._update_responsive_layout()
    
    def _update_responsive_layout(self):
        """Update responsive layout based on window width only (dynamic threshold from config)"""
        if not hasattr(self, 'queue_container') or not hasattr(self, 'overlay_panel'):
            return

        # When the settings or downloader tab is open, keep all queue UIs hidden so they cannot overlap
        if getattr(self, 'settings_tab_open', False) or getattr(self, 'downloader_tab_open', False):
            self.queue_container.setVisible(False)
            self.queue_container.setFixedWidth(0)
            self.overlay_panel.hide()
            return
        
        window_width = self.width()
        
        # Use dynamic threshold from config (width only, height doesn't matter)
        threshold_width = self.gui_config.sidebar_overlay_threshold_width
        
        if window_width >= threshold_width:
            # Wide window: show queue as side panel
            # Only auto-enable sidebar on startup (if user hasn't toggled yet)
            # If user has manually toggled, respect their choice
            if not self.user_toggled_sidebar:
                # Auto-open sidebar on startup if window is wide enough
                target_width = int(self.width() * self.gui_config.queue_sidebar_width_percent)
                self.queue_container.setFixedWidth(target_width)
                self.queue_container.setVisible(True)
                self.queue_sidebar_visible = True
            else:
                # User has toggled before - respect their choice
                if self.queue_sidebar_visible:
                    target_width = int(self.width() * self.gui_config.queue_sidebar_width_percent)
                    self.queue_container.setFixedWidth(target_width)
                    self.queue_container.setVisible(True)
                else:
                    # User toggled OFF - keep it off
                    self.queue_container.setVisible(False)
                    self.queue_container.setFixedWidth(0)
            
            # Make sure overlay is hidden in wide window mode
            self.overlay_panel.hide()
            # Ensure queue is attached to side panel in wide layouts
            self._reattach_queue_to_side_panel()
        else:
            # Small window: hide side panel, use overlay mode
            self.queue_container.setVisible(False)
            self.queue_container.setFixedWidth(0)
            self.queue_sidebar_visible = False
            # Note: overlay_panel.show() is controlled by show_queue() method
            # If overlay is visible, ensure it holds the queue widget
            if self.overlay_panel.isVisible():
                try:
                    current = self.overlay_panel.scroll_area.widget()
                except Exception:
                    current = None
                if current is None:
                    # Move from side panel if present
                    w = None
                    try:
                        w = self.side_scroll_area.takeWidget()
                    except Exception:
                        pass
                    if w is None:
                        w = self.queue_widget
                    self.overlay_panel.attach_queue_widget(w)
        
        # Recompute album art size when layout mode changes
        self._update_art_size()

    def _reattach_queue_to_side_panel(self):
        # Move queue widget back to side panel if not already attached
        try:
            current = self.side_scroll_area.widget()
        except Exception:
            current = None
        if current is None:
            w = None
            try:
                w = self.overlay_panel.detach_queue_widget()
            except Exception:
                pass
            if w is None:
                w = self.queue_widget
            try:
                self.side_scroll_area.setWidget(w)
            except Exception:
                pass
    
    def _animate_queue_sidebar(self, show):
        """Animate queue sidebar sliding in/out from the right side"""
        # Stop any existing animation
        if self.queue_animation and self.queue_animation.state() == QPropertyAnimation.Running:
            self.queue_animation.stop()
        
        target_width = int(self.width() * self.gui_config.queue_sidebar_width_percent)
        anim_duration = self.gui_config.queue_sidebar_animation_duration
        
        if show:
            # Slide in from right
            self.queue_container.setVisible(True)
            self.queue_animation = QPropertyAnimation(self.queue_container, b"maximumWidth")
            self.queue_animation.setDuration(anim_duration)
            self.queue_animation.setStartValue(0)
            self.queue_animation.setEndValue(target_width)
            self.queue_animation.setEasingCurve(QEasingCurve.OutCubic)
            
            # Update minimum width during animation
            min_anim = QPropertyAnimation(self.queue_container, b"minimumWidth")
            min_anim.setDuration(anim_duration)
            min_anim.setStartValue(0)
            min_anim.setEndValue(target_width)
            min_anim.setEasingCurve(QEasingCurve.OutCubic)
            
            # Group animations
            anim_group = QParallelAnimationGroup()
            anim_group.addAnimation(self.queue_animation)
            anim_group.addAnimation(min_anim)
            
            def on_show_finished():
                self.queue_container.setFixedWidth(target_width)
                self._update_art_size()
            
            anim_group.finished.connect(on_show_finished)
            self.queue_animation = anim_group
            self.queue_animation.start()
        else:
            # Slide out to right
            current_width = self.queue_container.width()
            self.queue_animation = QPropertyAnimation(self.queue_container, b"maximumWidth")
            self.queue_animation.setDuration(anim_duration)
            self.queue_animation.setStartValue(current_width)
            self.queue_animation.setEndValue(0)
            self.queue_animation.setEasingCurve(QEasingCurve.InCubic)
            
            # Update minimum width during animation
            min_anim = QPropertyAnimation(self.queue_container, b"minimumWidth")
            min_anim.setDuration(anim_duration)
            min_anim.setStartValue(current_width)
            min_anim.setEndValue(0)
            min_anim.setEasingCurve(QEasingCurve.InCubic)
            
            # Group animations
            anim_group = QParallelAnimationGroup()
            anim_group.addAnimation(self.queue_animation)
            anim_group.addAnimation(min_anim)
            
            def on_hide_finished():
                self.queue_container.setVisible(False)
                self.queue_container.setFixedWidth(0)
                # Force layout update before updating art size
                if hasattr(self, 'player_view'):
                    self.player_view.updateGeometry()
                QTimer.singleShot(0, self._update_art_size)
            
            anim_group.finished.connect(on_hide_finished)
            self.queue_animation = anim_group
            self.queue_animation.start()
        
        # Trigger art size update during animation
        QTimer.singleShot(150, self._update_art_size)
    
    def show_queue(self):
        """Toggle queue visibility. In narrow windows, show overlay. In wide windows, toggle side panel with animation."""
        window_width = self.width()
        
        # Use dynamic threshold from config (width only)
        threshold_width = self.gui_config.sidebar_overlay_threshold_width
        
        if window_width >= threshold_width:
            # Wide window: toggle queue sidebar with smooth animation
            self.queue_sidebar_visible = not self.queue_sidebar_visible
            self.user_toggled_sidebar = True  # Mark that user manually toggled
            if self.queue_sidebar_visible:
                # Ensure queue is attached to side panel when showing
                self._reattach_queue_to_side_panel()
            # Animate the sidebar
            self._animate_queue_sidebar(self.queue_sidebar_visible)
        else:
            # Narrow window: toggle overlay queue visibility
            if self.overlay_panel.isVisible():
                # Already showing overlay - close it
                self.show_player()
            else:
                # Not showing overlay - open it
                # Move queue widget into overlay
                w = None
                try:
                    w = self.side_scroll_area.takeWidget()
                except Exception:
                    pass
                if w is None:
                    try:
                        w = self.overlay_panel.detach_queue_widget()
                    except Exception:
                        w = None
                if w is None:
                    w = self.queue_widget
                self.overlay_panel.attach_queue_widget(w)
                # Show and animate backdrop
                self._show_overlay_backdrop()
                # Ensure overlay fills the player area
                self.overlay_panel.update_geometry_to_parent()
                self.overlay_panel.show()
    
    def show_player(self):
        """Hide overlay queue (side panel queue is always visible in large windows)"""
        self._hide_overlay_backdrop()
        self._reattach_queue_to_side_panel()
        self.overlay_panel.hide()
    
    def _show_overlay_backdrop(self):
        """Show and fade in the dark backdrop behind overlay"""
        if not hasattr(self, 'overlay_backdrop'):
            return
        
        # Stop any existing animation
        if self.backdrop_animation and self.backdrop_animation.state() == QPropertyAnimation.Running:
            self.backdrop_animation.stop()
        
        # Position backdrop to fill main container
        main_container = self.centralWidget()
        if main_container:
            self.overlay_backdrop.setGeometry(0, 0, main_container.width(), main_container.height())
        
        # Show backdrop and raise it above player but below overlay
        self.overlay_backdrop.setVisible(True)
        self.overlay_backdrop.raise_()
        if hasattr(self, 'overlay_panel'):
            self.overlay_panel.raise_()  # Ensure overlay is on top
        
        # Animate fade in
        self.backdrop_animation = QPropertyAnimation(self.backdrop_opacity, b"opacity")
        self.backdrop_animation.setDuration(300)
        self.backdrop_animation.setStartValue(0.0)
        self.backdrop_animation.setEndValue(1.0)
        self.backdrop_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.backdrop_animation.start()
    
    def _hide_overlay_backdrop(self):
        """Fade out and hide the dark backdrop"""
        if not hasattr(self, 'overlay_backdrop') or not self.overlay_backdrop.isVisible():
            return
        
        # Stop any existing animation
        if self.backdrop_animation and self.backdrop_animation.state() == QPropertyAnimation.Running:
            self.backdrop_animation.stop()
        
        # Animate fade out
        self.backdrop_animation = QPropertyAnimation(self.backdrop_opacity, b"opacity")
        self.backdrop_animation.setDuration(300)
        self.backdrop_animation.setStartValue(1.0)
        self.backdrop_animation.setEndValue(0.0)
        self.backdrop_animation.setEasingCurve(QEasingCurve.InCubic)
        
        def on_finished():
            self.overlay_backdrop.setVisible(False)
            self.overlay_backdrop.lower()
        
        self.backdrop_animation.finished.connect(on_finished)
        self.backdrop_animation.start()
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.isfile(file_path):
                files.append(file_path)
            elif os.path.isdir(file_path):
                for root, dirs, filenames in os.walk(file_path):
                    for f in filenames:
                        if f.lower().endswith(('.mp3', '.flac', '.ogg', '.wav', '.m4a', '.aac', '.opus')):
                            files.append(os.path.join(root, f))
        if files:
            self.add_files_to_playlist(files)
            if self.shuffle_mode and self.shuffle_anchor is None and self.current_index != -1:
                self.shuffle_anchor = self.current_index

    def open_downloader_app(self):
        app_path = Path(__file__).parent / "apps" / "app.py"
        if not app_path.exists():
            print(f"ERROR: Downloader app not found at {app_path}")
            return
        try:
            env = os.environ.copy()
            env["AURION_CHILD"] = "1"
            env["AURION_PARENT_PID"] = str(os.getpid())
            creationflags = 0
            if sys.platform.startswith("win"):
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            print(f"Launching downloader: {app_path}")
            proc = subprocess.Popen([sys.executable, str(app_path)], env=env, creationflags=creationflags)
            self.downloader_proc = proc
            print(f"Downloader process started with PID {proc.pid}")
        except Exception as e:
            print(f"ERROR launching downloader: {e}")
            import traceback
            traceback.print_exc()
    
    def open_files(self):
        try:
            dlg = QFileDialog(self, "Open Audio Files")
            dlg.setFileMode(QFileDialog.ExistingFiles)
            dlg.setNameFilter("Audio Files (*.mp3 *.flac *.ogg *.wav *.m4a *.aac *.opus);;All Files (*)")
            dlg.setOption(QFileDialog.DontUseNativeDialog, True)
            dlg.setStyleSheet(
                """
                QFileDialog { background-color: #10151f; color: white; }
                QListView, QTreeView { background-color: rgba(255,255,255,0.08); color: white; }
                QLineEdit { background-color: rgba(255,255,255,0.12); color: white; }
                QLabel { color: white; }
                QComboBox, QComboBox:editable { background-color: rgba(255,255,255,0.12); color: white; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; padding: 4px 8px; }
                QComboBox::drop-down { border: none; width: 22px; }
                QComboBox QAbstractItemView { background-color: #1a2332; color: white; selection-background-color: #5294e2; }
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    border: none; border-radius: 6px; color: white; padding: 6px 12px;
                }
                QPushButton:hover { background-color: rgba(255, 255, 255, 0.14); }
                """
            )
            if dlg.exec_() == QDialog.Accepted:
                files = dlg.selectedFiles()
                if files:
                    self.add_files_to_playlist(files)
        except Exception:
            files, _ = QFileDialog.getOpenFileNames(
                self, "Open Audio Files", "",
                "Audio Files (*.mp3 *.flac *.ogg *.wav *.m4a *.aac *.opus);;All Files (*)"
            )
            if files:
                self.add_files_to_playlist(files)
    
    def open_folder(self):
        try:
            dlg = QFileDialog(self, "Open Folder")
            dlg.setFileMode(QFileDialog.Directory)
            dlg.setOption(QFileDialog.ShowDirsOnly, True)
            dlg.setOption(QFileDialog.DontUseNativeDialog, True)
            dlg.setStyleSheet(
                """
                QFileDialog { background-color: #10151f; color: white; }
                QListView, QTreeView { background-color: rgba(255,255,255,0.08); color: white; }
                QLineEdit { background-color: rgba(255,255,255,0.12); color: white; }
                QLabel { color: white; }
                QComboBox, QComboBox:editable { background-color: rgba(255,255,255,0.12); color: white; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; padding: 4px 8px; }
                QComboBox::drop-down { border: none; width: 22px; }
                QComboBox QAbstractItemView { background-color: #1a2332; color: white; selection-background-color: #5294e2; }
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    border: none; border-radius: 6px; color: white; padding: 6px 12px;
                }
                QPushButton:hover { background-color: rgba(255, 255, 255, 0.14); }
                """
            )
            if dlg.exec_() == QDialog.Accepted:
                files = dlg.selectedFiles()
                folder = files[0] if files else ""
                if folder:
                    self.load_folder_files(folder)
        except Exception:
            folder = QFileDialog.getExistingDirectory(self, "Open Folder")
            if folder:
                self.load_folder_files(folder)
    
    def choose_folder(self):
        """Choose a folder and remember it for future sessions"""
        folder = ""
        try:
            dlg = QFileDialog(self, "Choose Music Folder")
            dlg.setFileMode(QFileDialog.Directory)
            dlg.setOption(QFileDialog.ShowDirsOnly, True)
            dlg.setOption(QFileDialog.DontUseNativeDialog, True)
            dlg.setStyleSheet(
                """
                QFileDialog { background-color: #10151f; color: white; }
                QListView, QTreeView { background-color: rgba(255,255,255,0.08); color: white; }
                QLineEdit { background-color: rgba(255,255,255,0.12); color: white; }
                QLabel { color: white; }
                QComboBox, QComboBox:editable { background-color: rgba(255,255,255,0.12); color: white; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; padding: 4px 8px; }
                QComboBox::drop-down { border: none; width: 22px; }
                QComboBox QAbstractItemView { background-color: #1a2332; color: white; selection-background-color: #5294e2; }
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    border: none; border-radius: 6px; color: white; padding: 6px 12px;
                }
                QPushButton:hover { background-color: rgba(255, 255, 255, 0.14); }
                """
            )
            if dlg.exec_() == QDialog.Accepted:
                files = dlg.selectedFiles()
                folder = files[0] if files else ""
        except Exception:
            folder = QFileDialog.getExistingDirectory(self, "Choose Music Folder")
        if folder:
            # Clear current playlist before loading new folder
            self.playlist.clear()
            self.queue_widget.clear()
            self.current_index = -1
            self.active_player.stop()
            self.preload_player.stop()
            self.shuffle_history.clear()
            self.shuffle_pool = []
            self.shuffle_seeded = False
            self.shuffle_anchor = None
            
            # Set new folder and load files
            self.saved_folder = folder
            self.save_settings()
            self.load_folder_files(folder)
    
    def load_folder_files(self, folder):
        """Load all audio files from a folder"""
        files = []
        for root, dirs, filenames in os.walk(folder):
            for f in filenames:
                file_path = os.path.join(root, f)
                if self._is_final_audio_file(file_path):
                    files.append(file_path)
        if files:
            self.add_files_to_playlist(files)

    def _scan_saved_folder_for_changes(self):
        """Poll the saved folder for added or removed audio files and sync the queue."""
        if not self.saved_folder or not os.path.isdir(self.saved_folder):
            return

        # Collect current finalized audio files on disk
        files = []
        for root, dirs, filenames in os.walk(self.saved_folder):
            for f in filenames:
                file_path = os.path.join(root, f)
                if self._is_final_audio_file(file_path):
                    files.append(file_path)

        disk_set = set(files)
        playlist_set = set(self.playlist)

        # Add newly appeared files
        new_files = [f for f in disk_set if f not in playlist_set]
        if new_files:
            self.add_files_to_playlist(new_files)

        # Remove files that were deleted from disk
        removed_files = [f for f in playlist_set if f not in disk_set]
        if removed_files:
            self._remove_files_from_playlist(removed_files)
    
    def add_files_to_playlist(self, files):
        for file in files:
            if file not in self.playlist:
                self.playlist.append(file)
                
                # Create list item
                item = QListWidgetItem()
                item.setData(Qt.UserRole, file)
                item.setSizeHint(QSize(0, 76))  # Set height for custom widget
                self.queue_widget.addItem(item)
                
                # Create custom widget
                widget = QueueItemWidget(file, is_playing=False)
                
                # Set playing icon from main player (make it white)
                if hasattr(self, 'icon_playing'):
                    pixmap = self.icon_playing.pixmap(QSize(20, 20))
                    # Create white version of the icon
                    white_pixmap = QPixmap(pixmap.size())
                    white_pixmap.fill(Qt.transparent)
                    painter = QPainter(white_pixmap)
                    painter.setCompositionMode(QPainter.CompositionMode_Source)
                    painter.drawPixmap(0, 0, pixmap)
                    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                    painter.fillRect(white_pixmap.rect(), QColor(255, 255, 255))
                    painter.end()
                    widget.playing_icon.setPixmap(white_pixmap)
                
                # Extract and set metadata
                title, artist = self.extract_metadata(file)
                if not title:
                    title = os.path.splitext(os.path.basename(file))[0]
                widget.set_metadata(title, artist)
                
                # Extract and set album art asynchronously
                QTimer.singleShot(0, lambda f=file, w=widget: self._load_queue_album_art(f, w))

                # Refresh metadata a few times in case the file was still being finalized
                self._schedule_metadata_refresh(file, widget, attempts=3, delay_ms=3000)
                
                # Set widget for item
                self.queue_widget.setItemWidget(item, widget)
                
                # Warm cache with track duration for queue total
                self._get_track_duration_ms(file)
        
        if len(self.playlist) == len(files) and self.current_index == -1:
            self.current_index = 0
            self.play_track(0)
        self.update_queue_duration_label()
        self.update_empty_state()
        self._reseed_shuffle_pool(preserve_current=True, reset_history=True)
    
    def _load_queue_album_art(self, file_path, widget):
        """Load album art for queue item widget"""
        try:
            album_art = self.extract_album_art(file_path)
            if album_art:
                pixmap = QPixmap()
                pixmap.loadFromData(album_art)
                if not pixmap.isNull():
                    widget.set_album_art(pixmap)
        except Exception:
            pass

    def _schedule_metadata_refresh(self, file_path, widget, attempts=3, delay_ms=2000):
        """Retry metadata/art refresh a few times in case the file finishes late."""

        def _attempt(remaining):
            self._refresh_queue_item_metadata(file_path, widget)
            if remaining > 1:
                QTimer.singleShot(delay_ms, lambda: _attempt(remaining - 1))

        QTimer.singleShot(delay_ms, lambda: _attempt(attempts))

    def _refresh_queue_item_metadata(self, file_path, widget):
        """Re-read metadata/album art for a queue item after the file finishes writing."""
        if not os.path.exists(file_path):
            return

        try:
            title, artist = self.extract_metadata(file_path)
            if not title:
                title = os.path.splitext(os.path.basename(file_path))[0]
            widget.set_metadata(title, artist)
        except Exception:
            pass

        # Refresh album art if available now
        self._load_queue_album_art(file_path, widget)

        # Refresh duration cache and labels
        try:
            self._get_track_duration_ms(file_path)
            self.update_queue_duration_label()
        except Exception:
            pass

    def _is_final_audio_file(self, file_path):
        """Return True if the path looks like a completed audio file (not temp/partial)."""
        try:
            name_lower = os.path.basename(file_path).lower()
            ext = Path(name_lower).suffix
            if ext not in self.audio_extensions:
                return False
            if any(marker in name_lower for marker in self.temp_markers):
                return False

            # Skip files that are very recent; may still be in-flight
            try:
                stat = os.stat(file_path)
                if time.time() - stat.st_mtime < self._new_file_min_age_secs:
                    return False
                if stat.st_size <= 0:
                    return False
            except Exception:
                return False

            return True
        except Exception:
            return False

    def _remove_files_from_playlist(self, files_to_remove):
        """Remove missing files from playlist and queue, and handle playback if needed."""
        remove_set = set(files_to_remove)
        if not remove_set:
            return

        # Stop playback if current track is being removed
        current_path = None
        if 0 <= self.current_index < len(self.playlist):
            current_path = self.playlist[self.current_index]
        removing_current = current_path in remove_set if current_path else False

        # Purge playlist entries
        self.playlist = [p for p in self.playlist if p not in remove_set]

        # Purge duration cache and art cache entries
        for p in list(self.track_durations.keys()):
            if p in remove_set:
                self.track_durations.pop(p, None)
        # For LRU caches, we need to rebuild without the removed items
        if remove_set:
            # Rebuild album art cache without removed items
            old_pixmap_cache = self.album_art_pixmap_cache
            self.album_art_pixmap_cache = LRUCache(old_pixmap_cache.max_size)
            self.playlist_manager.album_art_pixmap_cache = self.album_art_pixmap_cache
            for key, val in old_pixmap_cache.cache.items():
                if key not in remove_set:
                    self.album_art_pixmap_cache.set(key, val)
            
            # Rebuild dominant color cache without removed items
            old_color_cache = self.dominant_color_cache
            self.dominant_color_cache = LRUCache(old_color_cache.max_size)
            self.playlist_manager.dominant_color_cache = self.dominant_color_cache
            for key, val in old_color_cache.cache.items():
                if key not in remove_set:
                    self.dominant_color_cache.set(key, val)

        # Remove queue items
        for i in range(self.queue_widget.count() - 1, -1, -1):
            item = self.queue_widget.item(i)
            path = item.data(Qt.UserRole)
            if path in remove_set:
                self.queue_widget.takeItem(i)

        # Reset or advance playback
        if removing_current:
            self.active_player.stop()
            self.preload_player.stop()
            self.current_index = -1
            if self.playlist:
                self.current_index = 0
                self.play_track(0)
            else:
                self.update_metadata_labels(None, self.pending_update_id)
                self.update_empty_state()

        # Ensure current_index still valid
        if self.current_index >= len(self.playlist):
            self.current_index = len(self.playlist) - 1

        if self.shuffle_anchor is not None:
            if self.shuffle_anchor >= len(self.playlist) or self.shuffle_anchor < 0:
                self.shuffle_anchor = self.current_index if self.current_index != -1 else None

        self._reseed_shuffle_pool(preserve_current=True, reset_history=True)

        self.update_queue_duration_label()
        self.update_empty_state()
    
    def _get_track_duration_ms(self, file_path):
        """Return track duration in ms, caching results for reuse."""
        if file_path in self.track_durations:
            return self.track_durations[file_path]

        duration_ms = 0
        try:
            audio = MutagenFile(file_path)
            if audio and hasattr(audio, 'info') and getattr(audio.info, 'length', None):
                duration_ms = int(audio.info.length * 1000)
        except Exception:
            duration_ms = 0

        self.track_durations[file_path] = duration_ms
        return duration_ms

    def update_queue_duration_label(self):
        """Update total queue playtime labels for side panel and overlay."""
        try:
            # Default: sum all tracks
            total_ms = sum(self._get_track_duration_ms(p) for p in self.playlist)
            remaining_ms = total_ms

            if 0 <= self.current_index < len(self.playlist):
                try:
                    position_ms = int(self.active_player.position())
                except Exception:
                    position_ms = 0

                try:
                    current_duration = int(self.active_player.duration())
                except Exception:
                    current_duration = 0
                if current_duration <= 0:
                    current_duration = self._get_track_duration_ms(self.playlist[self.current_index])

                position_ms = max(0, min(position_ms, current_duration))
                current_remaining = max(0, current_duration - position_ms)

                if self.shuffle_mode:
                    # Keep pool clean without reseeding; future tracks are the pool contents
                    self._prepare_shuffle_pool(allow_reseed=False)
                    pool_remaining = sum(self._get_track_duration_ms(self.playlist[i]) for i in self.shuffle_pool if 0 <= i < len(self.playlist))
                    remaining_ms = current_remaining + pool_remaining
                else:
                    elapsed_ms = 0
                    for i in range(self.current_index):
                        elapsed_ms += self._get_track_duration_ms(self.playlist[i])
                    elapsed_ms += position_ms
                    remaining_ms = max(0, total_ms - elapsed_ms)

            text = f"Remaining {self.format_time(remaining_ms)}"
            if hasattr(self, 'queue_total_label'):
                self.queue_total_label.setText(text)
            if hasattr(self, 'overlay_panel') and hasattr(self.overlay_panel, 'total_duration_label'):
                self.overlay_panel.total_duration_label.setText(text)
        except Exception:
            pass

    def clear_playlist(self):
        self.playlist.clear()
        self.queue_widget.clear()
        self.current_index = -1
        self.active_player.stop()
        self.preload_player.stop()
        # Reset text labels to default state (directly, no animation needed for clearing)
        self.title_a.setText("No track playing")
        self.title_b.setText("No track playing")
        self.artist_a.setText("")
        self.artist_b.setText("")
        self.title_front = 'A'
        self.artist_front = 'A'
        self.title_opacity_a.setOpacity(1.0)
        self.title_opacity_b.setOpacity(0.0)
        self.artist_opacity_a.setOpacity(1.0)
        self.artist_opacity_b.setOpacity(0.0)
        self.background.set_from_color(QColor(30, 30, 30, 200), use_gradient=False)
        # Reset queue panel colors to default dark tone when clearing
        self.update_queue_colors(QColor(30, 30, 30))
        # Clear caches
        self.album_art_pixmap_cache.clear()
        self.dominant_color_cache.clear()
        self.track_durations.clear()
        self.shuffle_history.clear()
        self.shuffle_pool = []
        self.shuffle_seeded = False
        self.shuffle_anchor = None
        # hide waveform when playlist is cleared
        if hasattr(self, 'waveform_container'):
            self.waveform_container.setVisible(False)
        # Reset album art to default
        self.art_a.clear()
        self.art_a.setText("🎵")
        self.art_b.clear()
        self.opacity_a.setOpacity(1.0)
        self.opacity_b.setOpacity(0.0)
        # Reset explicit front state and stacking order
        self._art_front = 'A'
        self.art_a.raise_()
        self.art_b.lower()
        self.update_queue_duration_label()
        self.update_empty_state()
    
    def reset_app(self):
        """Reset the app to defaults and forget folder selection"""
        # Clear playlist
        self.clear_playlist()
        
        # Reset saved folder
        self.saved_folder = None
        
        # Reset settings to defaults
        self.shuffle_mode = False
        self.repeat_mode = 0
        self.shuffle_history.clear()
        self.shuffle_pool = []
        self.shuffle_seeded = False
        self.shuffle_anchor = None
        self._update_shuffle_icon()
        self._update_repeat_icon()
        # Reset queue backgrounds to default gray
        default_color = QColor(30, 30, 30)
        self.update_queue_colors(default_color)
        if hasattr(self, 'background'):
            self.background.set_from_color(QColor(30, 30, 30, 200), use_gradient=False)
        
        # Save the reset settings
        self.save_settings()
        
        # Update UI
        self.update_empty_state()
    
    def filter_queue(self, text):
        """Filter queue items by song name or artist"""
        search_text = text.lower().strip()
        
        for i in range(self.queue_widget.count()):
            item = self.queue_widget.item(i)
            widget = self.queue_widget.itemWidget(item)
            
            if not search_text:
                # Show all items if search is empty
                item.setHidden(False)
            else:
                # Get song name and artist from widget
                if widget:
                    song_name = widget.song_label.text().lower()
                    artist_name = widget.artist_label.text().lower()
                    
                    # Show item if search text matches song name or artist
                    matches = search_text in song_name or search_text in artist_name
                    item.setHidden(not matches)
                else:
                    # Fallback: hide if no widget
                    item.setHidden(True)
    
    def play_selected(self, item):
        index = self.queue_widget.row(item)
        self.play_track(index, user_triggered=True)
        self.show_player()
        # Clear selection highlight after playing
        self.queue_widget.clearSelection()
    
    def play_track(self, index, *, user_triggered=False, start_paused=False):
        self._cancel_crossfade()
        if 0 <= index < len(self.playlist):
            # Increment update ID exactly once per track change
            self.pending_update_id += 1
            current_update_id = self.pending_update_id
            self.current_index = index
            if self.shuffle_mode:
                if user_triggered or self.shuffle_anchor is None:
                    self.shuffle_anchor = index
                if user_triggered:
                    self._reseed_shuffle_pool(preserve_current=True, reset_history=True)
            self.update_queue_duration_label()
            # hide empty-state overlay when playing
            if hasattr(self, 'empty_label'):
                self.empty_label.setVisible(False)
            # show waveform when playing
            if hasattr(self, 'waveform_container'):
                self.waveform_container.setVisible(True)
            file_path = self.playlist[index]
            
            # --- DEFER METADATA ---
            # Immediately update the destination (hidden) label to show filename as placeholder,
            # then defer real metadata read to trigger the fade animation.
            # This avoids showing the filename on screen before fading to metadata.
            filename = os.path.basename(file_path)
            name_without_ext = os.path.splitext(filename)[0]
            
            # Update only the destination (hidden) labels, not the visible ones
            if self.title_front == 'A':
                self.title_b.setText(name_without_ext)
                self.artist_b.setText("...")
            else:
                self.title_a.setText(name_without_ext)
                self.artist_a.setText("...")

            # Update dynamic background (animations start immediately)
            self.update_dynamic_background(update_id=current_update_id)

            # Defer the potentially slow metadata read
            QTimer.singleShot(50, lambda: self.update_metadata_labels(file_path, current_update_id))

            # Defer waveform computation to avoid blocking UI
            QTimer.singleShot(0, lambda: self._deferred_compute_waveform(file_path, current_update_id))
            
            # Defer media loading and playback to avoid blocking UI
            QTimer.singleShot(0, lambda: self._deferred_start_playback(file_path, current_update_id, start_paused=start_paused))
            
            # Show playing icon in queue
            for i in range(self.queue_widget.count()):
                item = self.queue_widget.item(i)
                widget = self.queue_widget.itemWidget(item)
                if widget:
                    widget.set_playing(i == index)

    def update_metadata_labels(self, file_path, update_id):
        """Update title and artist labels after deferred metadata extraction with fade animation."""
        # Check if this update is still valid (i.e., user hasn't skipped again)
        if update_id != self.pending_update_id:
            return

        title, artist = self.extract_metadata(file_path)
        
        # Prepare title (use filename without extension as fallback)
        display_title = title if title else os.path.splitext(os.path.basename(file_path))[0]
        
        # Prepare artist
        display_artist = artist if artist else "Unknown Artist"
        
        # Ensure sizes and geometries are up to date before animating to avoid jumps/clipping
        try:
            self._sync_text_label_sizes()
            self._update_text_label_geometries()
        except Exception:
            pass

        # Update labels with or without animation based on setting
        if self.text_fade_enabled:
            # Animate the text change
            self._animate_text_crossfade(new_title=display_title, new_artist=display_artist)
        else:
            # Direct update without animation
            self.title_a.setText(display_title)
            self.title_b.setText(display_title)
            self.artist_a.setText(display_artist)
            self.artist_b.setText(display_artist)
            try:
                self._sync_text_label_sizes()
                self._update_text_label_geometries()
            except Exception:
                pass
        
        # Update mini control bar if settings or downloader tab is open
        if self.settings_tab_open or self.downloader_tab_open:
            self._update_mini_control_bar()

    def update_empty_state(self):
        # Show the empty overlay if there are no tracks and nothing playing
        try:
            visible = (len(self.playlist) == 0 and self.current_index == -1)
            if hasattr(self, 'empty_label'):
                self.empty_label.setVisible(visible)
            if hasattr(self, 'add_file_btn'):
                self.add_file_btn.setVisible(visible)
            if hasattr(self, 'choose_folder_btn'):
                self.choose_folder_btn.setVisible(visible)
            # Show change folder button when music is loaded and there's a saved folder
            if hasattr(self, 'change_folder_btn'):
                self.change_folder_btn.setVisible(not visible and self.saved_folder is not None)
        except Exception:
            pass

    def _calculate_art_size(self):
        """Compute album art size based on window height and available player width."""
        try:
            player_height = self.player_view.height()
            
            # Sum the heights of all other widgets in the player layout
            other_widgets_height = 0
            # Access layout items directly to check visibility and get geometry
            player_layout = self.player_view.layout()
            if player_layout:
                for i in range(player_layout.count()):
                    item = player_layout.itemAt(i)
                    widget = item.widget()
                    if widget and widget.isVisible() and widget != self.art_container:
                        other_widgets_height += widget.height()
            
            # Estimate vertical spacing from the layout
            spacing = 0
            if player_layout:
                spacing = player_layout.spacing() * (player_layout.count() - 1)

            # Available height for the art container is the player height minus other widgets and spacing
            available_height = player_height - other_widgets_height - spacing
            
            # Use a percentage of the available height for the art, with a max cap
            height_limited = int(min(500, available_height * 0.85))
        except Exception:
            # Fallback to original simple calculation in case of errors
            height_limited = int(min(500, self.height() * 0.35))
        
        # Width-driven limit to avoid clipping when the queue sidebar is visible
        available_width = self.width()
        try:
            main_container = self.centralWidget()
            if main_container:
                available_width = main_container.width()
        except Exception:
            pass

        queue_width = 0
        if hasattr(self, 'queue_container') and self.queue_container.isVisible():
            queue_width = self.queue_container.width()

        player_width = available_width - queue_width
        # Reserve some padding so art doesn't touch edges
        player_width = max(160, player_width - 80)

        return max(120, min(height_limited, player_width))

    def _update_art_size(self):
        """Apply the calculated album art size to art widgets."""
        if not hasattr(self, 'art_widget'):
            return

        art_size = self._calculate_art_size()
        self.art_widget.setFixedSize(art_size, art_size)
        self.art_a.setFixedSize(art_size, art_size)
        self.art_b.setFixedSize(art_size, art_size)
        self.art_a.move(0, 0)
        self.art_b.move(0, 0)
        if hasattr(self, 'art_container'):
            self.art_container.updateGeometry()
            self.art_widget.updateGeometry()
            # Force the art labels to update their geometry as well
            self.art_a.updateGeometry()
            self.art_b.updateGeometry()
        
        # Update text label overlay geometries
        self._update_text_label_geometries()
    
    def _update_text_label_geometries(self):
        """Update the geometry of overlay text labels to match their parent widgets."""
        try:
            # Update title label B geometry
            if hasattr(self, 'title_b') and hasattr(self, 'title_a'):
                # Get parent widget from title_a
                parent = self.title_a.parentWidget()
                if parent:
                    self.title_b.setGeometry(0, 0, parent.width(), parent.height())
            
            # Update artist label B geometry
            if hasattr(self, 'artist_b') and hasattr(self, 'artist_a'):
                # Get parent widget from artist_a
                parent = self.artist_a.parentWidget()
                if parent:
                    self.artist_b.setGeometry(0, 0, parent.width(), parent.height())
        except Exception:
            pass

    def _sync_text_label_sizes(self):
        """Ensure stacked title/artist labels share the same height to prevent clipping."""
        try:
            if hasattr(self, 'title_a') and hasattr(self, 'title_b'):
                title_height = max(self.title_a.sizeHint().height(), self.title_b.sizeHint().height())
                self.title_a.setFixedHeight(title_height)
                self.title_b.setFixedHeight(title_height)
                parent = self.title_a.parentWidget()
                if parent:
                    parent.setFixedHeight(title_height)
            if hasattr(self, 'artist_a') and hasattr(self, 'artist_b'):
                artist_height = max(self.artist_a.sizeHint().height(), self.artist_b.sizeHint().height())
                self.artist_a.setFixedHeight(artist_height)
                self.artist_b.setFixedHeight(artist_height)
                parent = self.artist_a.parentWidget()
                if parent:
                    parent.setFixedHeight(artist_height)
        except Exception:
            pass
    
    def update_dynamic_background(self, update_id=None):
        # Ensure background has correct size before updating color
        main_container = self.centralWidget()
        if main_container:
            self.background.setGeometry(0, 0, main_container.width(), main_container.height())
        
        # Use the update id passed from play_track to keep all deferred work in sync
        current_update_id = update_id if update_id is not None else self.pending_update_id
        
        if 0 <= self.current_index < len(self.playlist):
            file_path = self.playlist[self.current_index]
            
            # Check if data is cached - if so, apply immediately without deferral
            cached_pixmap = self.album_art_pixmap_cache.get(file_path)
            cached_color = self.dominant_color_cache.get(file_path)
            if cached_pixmap and cached_color:
                # Cached - apply immediately for instant response
                # Create a deep copy of the pixmap to avoid both labels sharing the same object
                scaled_pixmap = cached_pixmap.copy()
                dominant_color = cached_color
                
                self._animate_album_art_crossfade(new_pixmap=scaled_pixmap)
                self._animate_background_color(dominant_color)
            else:
                # Not cached - defer to avoid blocking
                QTimer.singleShot(0, lambda: self._apply_background_update(file_path, current_update_id))
        else:
            # No tracks, use default color
            self._animate_background_color(QColor(30, 30, 30))
    
    def _apply_background_update(self, file_path, update_id):
        """Apply background update using cached data if available, otherwise load"""
        # Check if this update is still valid
        if update_id != self.pending_update_id:
            return
        
        # Check if we have preloaded pixmap (already decoded and scaled)
        cached_pixmap = self.album_art_pixmap_cache.get(file_path)
        cached_color = self.dominant_color_cache.get(file_path)
        if cached_pixmap and cached_color:
            # Use cached data - no I/O or heavy processing needed!
            # Create a deep copy to avoid both labels sharing the same pixmap object
            scaled_pixmap = cached_pixmap.copy()
            dominant_color = cached_color
            
            # Display album art
            self._animate_album_art_crossfade(new_pixmap=scaled_pixmap)
            
            # Animate to dominant color
            self._animate_background_color(dominant_color)
        else:
            # Not cached - fallback to loading with placeholder color
            fallback_color = self.FALLBACK_COLORS[self.current_index % len(self.FALLBACK_COLORS)]
            self._animate_background_color(fallback_color)
            
            # Load in background
            self._deferred_update_background(file_path, update_id)
    
    def _deferred_update_background(self, file_path, update_id):
        """Deferred heavy work: album art extraction and color analysis (with caching)"""
        # Check if this update is still valid (not superseded by rapid track changes)
        if update_id != self.pending_update_id:
            return
        
        # Extract album art (blocking I/O)
        album_art = self.extract_album_art(file_path)
        
        # Check again after I/O
        if update_id != self.pending_update_id:
            return
        
        if album_art:
            # Decode image (blocking)
            pixmap = QPixmap()
            pixmap.loadFromData(album_art)
            
            # Check again after decoding
            if update_id != self.pending_update_id:
                return
            
            if not pixmap.isNull():
                # Scale pixmap (blocking)
                scaled_pixmap = pixmap.scaled(self.ALBUM_ART_SIZE, self.ALBUM_ART_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                # Cache the decoded and scaled pixmap for future use
                self.album_art_pixmap_cache.set(file_path, scaled_pixmap)
                
                # Display album art with smooth crossfade
                # Use QTimer to ensure animation runs on next event loop
                QTimer.singleShot(0, lambda: self._animate_album_art_crossfade(new_pixmap=scaled_pixmap))
                
                # Calculate dominant color from album art (blocking PIL work)
                dominant_color = self.get_dominant_color(album_art)
                
                # Final check before applying
                if update_id != self.pending_update_id:
                    return
                
                if dominant_color:
                    # Cache the dominant color
                    self.dominant_color_cache.set(file_path, dominant_color)
                    self._animate_background_color(dominant_color)
        else:
            # No album art, show default icon
            if update_id == self.pending_update_id:
                self._animate_album_art_crossfade(new_text="🎵")
    
    def _deferred_compute_waveform(self, file_path, update_id):
        """Deferred waveform computation to avoid blocking UI thread"""
        # Check if this update is still valid
        if update_id != self.pending_update_id:
            return
        
        # Compute waveform (potentially blocking for WAV files)
        try:
            waveform = self.compute_waveform(file_path)
            
            # Check again after computation
            if update_id != self.pending_update_id:
                return
            
            if waveform:
                self.waveform.set_waveform_data(waveform)
        except Exception:
            pass
    
    def _deferred_start_playback(self, file_path, update_id, start_paused=False):
        """Deferred media loading and playback start - uses preloaded player if available."""
        # Check if this update is still valid (not superseded by rapid track changes)
        if update_id != self.pending_update_id:
            return
        
        # Check if the preload player already has this track loaded
        preload_media = self.preload_player.media()
        preload_ready = (preload_media is not None and 
                        preload_media.canonicalUrl().toLocalFile() == file_path)
        
        if preload_ready:
            # Swap players - instant playback with no decoder init!
            self._disconnect_player_signals(self.active_player)
            self.active_player.stop()
            
            # Swap references
            self.active_player, self.preload_player = self.preload_player, self.active_player
            
            # Connect signals to new active player
            self._connect_player_signals(self.active_player)
            
            if start_paused:
                self.active_player.pause()
                self.active_player.setPosition(0)
            else:
                # Start playback immediately - no blocking!
                self.active_player.play()
        else:
            # Fallback: load and play normally (first track, backward skip, etc.)
            self.active_player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            
            # Check again after setMedia
            if update_id != self.pending_update_id:
                return
            
            if start_paused:
                self.active_player.pause()
                self.active_player.setPosition(0)
            else:
                self.active_player.play()
        
        # Preload the next track in the background
        QTimer.singleShot(100, self._preload_next_track)
    
    def _animate_background_color(self, target_color):
        """Animate background color transition"""
        if self.color_animation and self.color_animation.state() == QPropertyAnimation.Running:
            self.color_animation.stop()
        
        self.color_animation = QPropertyAnimation(self.background, b"animatedColor")
        self.color_animation.setDuration(800)
        # Set start value to current color to ensure smooth transition from current state
        self.color_animation.setStartValue(self.background.base_color)
        self.color_animation.setEndValue(target_color)
        self.color_animation.setEasingCurve(QEasingCurve.InOutCubic)

        # Drive queue gradients with the same color tween so they update in lockstep
        try:
            self.color_animation.valueChanged.connect(lambda value: self.update_queue_colors(value))
        except Exception:
            pass

        self.color_animation.start()
        
        # Ensure final state matches target even if animation is interrupted
        try:
            self.color_animation.finished.connect(lambda: self.update_queue_colors(target_color))
        except Exception:
            pass
    
    def update_queue_colors(self, color):
        """Update queue container backgrounds with gradient matching the main background"""
        # Create darker gradient for queue (more subtle, distinguishable)
        r = int(color.red() * 0.8)
        g = int(color.green() * 0.8)
        b = int(color.blue() * 0.8)
        
        # Even darker for bottom
        r_dark = int(r * 0.4)
        g_dark = int(g * 0.4)
        b_dark = int(b * 0.4)
        
        # Create gradient stylesheet for queue containers (fully opaque)
        gradient_style = f"""
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba({r}, {g}, {b}, 255),
                stop:0.4 rgba({int(r*0.7)}, {int(g*0.7)}, {int(b*0.7)}, 255),
                stop:0.7 rgba({int(r*0.5)}, {int(g*0.5)}, {int(b*0.5)}, 255),
                stop:1 rgba({r_dark}, {g_dark}, {b_dark}, 255)
            );
        """
        
        # Update side queue container
        if hasattr(self, 'queue_container'):
            self.queue_container.setStyleSheet(gradient_style)
        
        # Update overlay panel
        if hasattr(self, 'overlay_panel'):
            self.overlay_panel.setStyleSheet(gradient_style)
    
    def _animate_album_art_crossfade(self, new_pixmap=None, new_text=None):
        """Deterministic, state-driven album art crossfade.
        Always fade from the current front label to the back label.
        Does not infer state from opacity or text and does not clear labels."""

        # Stop and reset any existing animation to deterministic state
        if self.album_art_animation is not None:
            try:
                self.album_art_animation.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            # Stop unconditionally to avoid overlap regardless of animation type
            try:
                self.album_art_animation.stop()
            except Exception:
                pass
            self.album_art_animation = None

        # Resolve source (front) and dest (back) by explicit state
        if self._art_front == 'A':
            source_label = self.art_a
            source_opacity = self.opacity_a
            dest_label = self.art_b
            dest_opacity = self.opacity_b
        else:
            source_label = self.art_b
            source_opacity = self.opacity_b
            dest_label = self.art_a
            dest_opacity = self.opacity_a

        # Reset opacities deterministically before starting animation
        source_opacity.setOpacity(1.0)
        dest_opacity.setOpacity(0.0)

        # Set new content on the destination label
        if new_pixmap is not None:
            # ScalableAlbumArtLabel handles automatic scaling on resize
            dest_label.setPixmap(new_pixmap)
            dest_label.setText("")
        elif new_text is not None:
            dest_label.setText(new_text)
            dest_label.setPixmap(QPixmap())
        else:
            # If no new content provided, keep existing dest content
            pass

        # Ensure stacking order: destination on top, source below
        dest_label.raise_()
        source_label.lower()

        # Create animation for fade out (source) and fade in (dest)
        fade_out = QPropertyAnimation(source_opacity, b"opacity")
        fade_out.setDuration(self.ALBUM_ART_CROSSFADE_DURATION)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InOutQuad)

        fade_in = QPropertyAnimation(dest_opacity, b"opacity")
        fade_in.setDuration(self.ALBUM_ART_CROSSFADE_DURATION)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InOutQuad)

        group = QParallelAnimationGroup()
        group.addAnimation(fade_out)
        group.addAnimation(fade_in)

        def on_finished():
            # Ensure final values are deterministic
            source_opacity.setOpacity(0.0)
            dest_opacity.setOpacity(1.0)
            # Update explicit front state to destination
            self._art_front = 'B' if self._art_front == 'A' else 'A'
            # Keep both labels' content (do not clear)
            self.album_art_animation = None

        group.finished.connect(on_finished)
        self.album_art_animation = group
        self.album_art_animation.start()
    
    def _animate_text_crossfade(self, new_title=None, new_artist=None):
        """Animate title and artist label crossfade for seamless song changes."""
        
        # Stop and reset any existing animation
        if self.text_animation is not None:
            try:
                self.text_animation.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self.text_animation.stop()
            except Exception:
                pass
            self.text_animation = None

        # Resolve source (front) and dest (back) for title labels
        if self.title_front == 'A':
            title_source_opacity = self.title_opacity_a
            title_dest_label = self.title_b
            title_dest_opacity = self.title_opacity_b
        else:
            title_source_opacity = self.title_opacity_b
            title_dest_label = self.title_a
            title_dest_opacity = self.title_opacity_a

        # Resolve source and dest for artist labels
        if self.artist_front == 'A':
            artist_source_opacity = self.artist_opacity_a
            artist_dest_label = self.artist_b
            artist_dest_opacity = self.artist_opacity_b
        else:
            artist_source_opacity = self.artist_opacity_b
            artist_dest_label = self.artist_a
            artist_dest_opacity = self.artist_opacity_a

        # Reset opacities deterministically
        title_source_opacity.setOpacity(1.0)
        title_dest_opacity.setOpacity(0.0)
        artist_source_opacity.setOpacity(1.0)
        artist_dest_opacity.setOpacity(0.0)

        # Set new content on destination labels
        if new_title is not None:
            title_dest_label.setText(new_title)
        if new_artist is not None:
            artist_dest_label.setText(new_artist)

        # Create animations for title fade out and fade in
        title_fade_out = QPropertyAnimation(title_source_opacity, b"opacity")
        title_fade_out.setDuration(self.ALBUM_ART_CROSSFADE_DURATION)
        title_fade_out.setStartValue(1.0)
        title_fade_out.setEndValue(0.0)
        title_fade_out.setEasingCurve(QEasingCurve.InOutQuad)

        title_fade_in = QPropertyAnimation(title_dest_opacity, b"opacity")
        title_fade_in.setDuration(self.ALBUM_ART_CROSSFADE_DURATION)
        title_fade_in.setStartValue(0.0)
        title_fade_in.setEndValue(1.0)
        title_fade_in.setEasingCurve(QEasingCurve.InOutQuad)

        # Create animations for artist fade out and fade in
        artist_fade_out = QPropertyAnimation(artist_source_opacity, b"opacity")
        artist_fade_out.setDuration(self.ALBUM_ART_CROSSFADE_DURATION)
        artist_fade_out.setStartValue(1.0)
        artist_fade_out.setEndValue(0.0)
        artist_fade_out.setEasingCurve(QEasingCurve.InOutQuad)

        artist_fade_in = QPropertyAnimation(artist_dest_opacity, b"opacity")
        artist_fade_in.setDuration(self.ALBUM_ART_CROSSFADE_DURATION)
        artist_fade_in.setStartValue(0.0)
        artist_fade_in.setEndValue(1.0)
        artist_fade_in.setEasingCurve(QEasingCurve.InOutQuad)

        # Group all animations together
        group = QParallelAnimationGroup()
        group.addAnimation(title_fade_out)
        group.addAnimation(title_fade_in)
        group.addAnimation(artist_fade_out)
        group.addAnimation(artist_fade_in)

        def on_finished():
            # Ensure final values are deterministic
            title_source_opacity.setOpacity(0.0)
            title_dest_opacity.setOpacity(1.0)
            artist_source_opacity.setOpacity(0.0)
            artist_dest_opacity.setOpacity(1.0)
            # Update explicit front state to destination
            self.title_front = 'B' if self.title_front == 'A' else 'A'
            self.artist_front = 'B' if self.artist_front == 'A' else 'A'
            self.text_animation = None

        group.finished.connect(on_finished)
        self.text_animation = group
        self.text_animation.start()
    
    def toggle_play(self):
        if self.active_player.state() == QMediaPlayer.PlayingState:
            self.active_player.pause()
        else:
            if self.current_index == -1 and self.playlist:
                self.play_track(0)
            else:
                self.active_player.play()
        self._update_play_icon()

    def show_settings_window(self):
        """Toggle the settings tab on/off"""
        if self.settings_tab_open:
            self.close_settings_tab()
        else:
            self.open_settings_tab()
    
    def open_settings_tab(self):
        """Open the settings tab and show mini control bar"""
        self.settings_tab_open = True
        self.settings_tab.setVisible(True)
        self.player_view.setVisible(False)
        self.queue_container.setVisible(False)
        self.queue_container.setFixedWidth(0)
        self.overlay_panel.hide()
        self.mini_control_bar.setVisible(True)
        
        # Update mini control bar with current playback state
        self._update_mini_control_bar()
    
    def close_settings_tab(self):
        """Close the settings tab and hide mini control bar"""
        self.settings_tab_open = False
        self.settings_tab.setVisible(False)
        self.player_view.setVisible(True)
        self.mini_control_bar.setVisible(False)
        
        # Restore queue visibility if it was visible
        if self.queue_sidebar_visible:
            try:
                target_width = int(self.width() * self.gui_config.queue_sidebar_width_percent)
                self.queue_container.setFixedWidth(target_width)
            except Exception:
                self.queue_container.setFixedWidth(0)
            self.queue_container.setVisible(True)

    def toggle_downloader_tab(self):
        """Toggle the downloader tab on/off"""
        if self.downloader_tab_open:
            self.close_downloader_tab()
        else:
            self.open_downloader_tab()
    
    def open_downloader_tab(self):
        """Open the downloader tab and show mini control bar"""
        # Close settings tab if open
        if self.settings_tab_open:
            self.close_settings_tab()
        
        self.downloader_tab_open = True
        self.downloader_tab.setVisible(True)
        self.player_view.setVisible(False)
        self.queue_container.setVisible(False)
        self.queue_container.setFixedWidth(0)
        self.overlay_panel.hide()
        self.mini_control_bar.setVisible(True)
        
        # Update mini control bar with current playback state
        self._update_mini_control_bar()
    
    def close_downloader_tab(self):
        """Close the downloader tab and hide mini control bar"""
        self.downloader_tab_open = False
        self.downloader_tab.setVisible(False)
        self.player_view.setVisible(True)
        self.mini_control_bar.setVisible(False)
        
        # Restore queue visibility if it was visible
        if self.queue_sidebar_visible:
            try:
                target_width = int(self.width() * self.gui_config.queue_sidebar_width_percent)
                self.queue_container.setFixedWidth(target_width)
            except Exception:
                self.queue_container.setFixedWidth(0)
            self.queue_container.setVisible(True)

        # Refresh layout to fix any displaced UI elements
        try:
            self._update_art_size()
        except Exception:
            pass
        try:
            self._update_responsive_layout()
        except Exception:
            pass

        # Re-run sizing after the event loop updates geometries (avoids shrunken album art)
        QTimer.singleShot(0, self._update_art_size)
    
    def _update_mini_control_bar(self):
        """Update mini control bar with current playback information"""
        if not (self.settings_tab_open or self.downloader_tab_open):
            return
        
        # Update play state
        is_playing = self.active_player.state() == QMediaPlayer.PlayingState
        self.mini_control_bar.set_play_state(is_playing)
        
        # Update shuffle and repeat states
        self.mini_control_bar.update_shuffle_state(self.shuffle_mode)
        self.mini_control_bar.update_repeat_state(self.repeat_mode)
        
        # Update volume
        self.mini_control_bar.volume_slider.blockSignals(True)
        self.mini_control_bar.volume_slider.setValue(self.active_player.volume())
        self.mini_control_bar.volume_slider.blockSignals(False)
        self.mini_control_bar.update_volume_icon(self.active_player.volume())
        
        # Update song info if available
        if 0 <= self.current_index < len(self.playlist):
            file_path = self.playlist[self.current_index]
            title, artist = self.extract_metadata(file_path)
            if not title:
                title = os.path.basename(file_path)
            
            # Get or load album art (larger for mini control bar)
            pixmap = self.album_art_pixmap_cache.get(file_path)
            if not pixmap:
                album_art = extract_album_art(file_path)
                if album_art:
                    pixmap = QPixmap()
                    pixmap.loadFromData(album_art)
                    if not pixmap.isNull():
                        pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.album_art_pixmap_cache.set(file_path, pixmap)
            
            self.mini_control_bar.set_album_art(pixmap)
            self.mini_control_bar.set_song_info(title, artist or "")
        else:
            self.mini_control_bar.set_song_info("No song playing", "")
            self.mini_control_bar.set_album_art(None)

    def _update_play_icon(self):
        try:
            if self.active_player.state() == QMediaPlayer.PlayingState:
                self.play_btn.setIcon(self.icon_pause)
            else:
                self.play_btn.setIcon(self.icon_play)
        except Exception:
            pass
    
    def next_track(self):
        self._cancel_crossfade()
        if not self.playlist:
            return
        
        if self.repeat_mode == 2:
            self.active_player.setPosition(0)
            self.active_player.play()
            return
        
        if self.shuffle_mode:
            if len(self.playlist) == 1:
                if self.repeat_mode == 1:
                    self.active_player.setPosition(0)
                    self.active_player.play()
                else:
                    self.active_player.pause()
                    self.active_player.setPosition(0)
                return

            if not self.shuffle_seeded:
                self._reseed_shuffle_pool(preserve_current=True, reset_history=False)

            self._prepare_shuffle_pool(allow_reseed=False)

            if not self.shuffle_pool:
                self.shuffle_history.clear()
                if self.repeat_mode == 1:
                    self._reseed_shuffle_pool(preserve_current=True, reset_history=True)
                else:
                    target = None
                    if self.shuffle_anchor is not None and 0 <= self.shuffle_anchor < len(self.playlist):
                        target = self.shuffle_anchor
                    elif self.playlist:
                        target = 0
                        self.shuffle_anchor = target

                    if target is not None:
                        self.play_track(target, start_paused=True)
                        self._reseed_shuffle_pool(preserve_current=True, reset_history=True)
                    return

            if not self.shuffle_pool:
                return

            if self.current_index != -1:
                self.shuffle_history.append(self.current_index)

            next_index = self.shuffle_pool.pop()
            self.play_track(next_index)
        else:
            next_index = self.current_index + 1
            if next_index >= len(self.playlist):
                if self.repeat_mode == 1:
                    next_index = 0
                else:
                    return
            self.play_track(next_index)
    
    def previous_track(self):
        self._cancel_crossfade()
        if not self.playlist:
            return
        
        if self.shuffle_mode and self.shuffle_history:
            prev_index = self.shuffle_history.pop()
            self.play_track(prev_index)
        else:
            prev_index = (self.current_index - 1) % len(self.playlist)
            self.play_track(prev_index)
    
    def toggle_shuffle(self):
        self.shuffle_mode = not self.shuffle_mode
        if self.shuffle_mode:
            self.shuffle_anchor = self.current_index if self.current_index != -1 else None
            self._reseed_shuffle_pool(preserve_current=True, reset_history=True)
        else:
            self.shuffle_history.clear()
            self.shuffle_pool = []
            self.shuffle_seeded = False
            self.shuffle_anchor = None
        self._update_shuffle_icon()
        
        # Update mini control bar if settings or downloader tab is open
        if self.settings_tab_open or self.downloader_tab_open:
            self.mini_control_bar.update_shuffle_state(self.shuffle_mode)

    def _update_shuffle_icon(self):
        try:
            self.shuffle_btn.setChecked(self.shuffle_mode)
        except Exception:
            pass
    
    def toggle_repeat(self):
        self.repeat_mode = (self.repeat_mode + 1) % 3
        self._update_repeat_icon()
        
        # Update mini control bar if settings or downloader tab is open
        if self.settings_tab_open or self.downloader_tab_open:
            self.mini_control_bar.update_repeat_state(self.repeat_mode)

    def _update_repeat_icon(self):
        try:
            if self.repeat_mode == 0:
                self.repeat_btn.setChecked(False)
                self.repeat_btn.setIcon(self.icon_repeat_all)
            elif self.repeat_mode == 1:
                self.repeat_btn.setChecked(True)
                self.repeat_btn.setIcon(self.icon_repeat_all)
            else:
                self.repeat_btn.setChecked(True)
                self.repeat_btn.setIcon(self.icon_repeat_one)
        except Exception:
            pass
    
    def seek_to_position(self, position):
        self.active_player.setPosition(position)
    
    def change_volume(self, value):
        self.active_player.setVolume(value)
        self.preload_player.setVolume(value)
        self.save_settings()
    
    def _on_mini_volume_changed(self, value):
        """Handle volume change from mini control bar"""
        self.change_volume(value)
        # Update main volume slider
        if hasattr(self, 'volume_slider'):
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(value)
            self.volume_slider.blockSignals(False)
        self._update_volume_icon(value)
    
    def _update_volume_icon(self, value):
        """Update volume icon based on slider value"""
        if value == 0:
            icon = self.icon_volume_none
        elif value <= 50:
            icon = self.icon_volume_low
        else:
            icon = self.icon_volume_high
        
        # Update main control bar volume icon
        if hasattr(self, 'volume_icon'):
            self.volume_icon.setPixmap(icon.pixmap(24, 24))
        
        # Update mini control bar volume icon if visible
        if hasattr(self, 'mini_control_bar') and self.mini_control_bar.isVisible():
            self.mini_control_bar.update_volume_icon(value)

    def set_crossfade_duration(self, seconds):
        seconds = max(0, min(12, int(seconds)))
        self.crossfade_duration_secs = seconds
        self.save_settings()
        if self.settings_tab:
            try:
                self.settings_tab.crossfade_slider.blockSignals(True)
                self.settings_tab.crossfade_slider.setValue(seconds)
                self.settings_tab.crossfade_slider.blockSignals(False)
            except Exception:
                pass
            try:
                self.settings_tab.value_label.setText(f"{seconds} s")
            except Exception:
                pass
        # Cancel any in-flight crossfade if duration is set to zero mid-transition
        if seconds == 0 and self.crossfade_in_progress:
            self._cancel_crossfade()

    def set_text_fade_enabled(self, enabled):
        """Toggle text fade animation setting"""
        self.text_fade_enabled = enabled
        self.save_settings()

    def _cancel_crossfade(self):
        if self.crossfade_timer:
            try:
                self.crossfade_timer.stop()
            except Exception:
                pass
            self.crossfade_timer = None
        if self.crossfade_in_progress:
            target_volume = self.volume_slider.value() if hasattr(self, 'volume_slider') else 50
            try:
                self.active_player.setVolume(target_volume)
                self.preload_player.setVolume(target_volume)
                if self.preload_player.state() == QMediaPlayer.PlayingState:
                    self.preload_player.stop()
            except Exception:
                pass
        self.crossfade_in_progress = False
        self.crossfade_target_index = None
        self.crossfade_start_time = 0.0

    def _maybe_start_crossfade(self, position_ms):
        if self.crossfade_duration_secs <= 0:
            return
        if self.crossfade_in_progress:
            return
        if self.active_player.state() != QMediaPlayer.PlayingState:
            return
        duration = self.active_player.duration()
        if duration <= 0:
            return
        remaining = duration - position_ms
        threshold_ms = self.crossfade_duration_secs * 1000
        if remaining > threshold_ms + 200:
            return
        next_idx = self._get_next_track_index()
        if next_idx == -1:
            return
        self._start_crossfade_to(next_idx)

    def _start_crossfade_to(self, next_index):
        if self.crossfade_in_progress or not (0 <= next_index < len(self.playlist)):
            return

        next_file = self.playlist[next_index]
        target_player = self.preload_player

        preload_media = target_player.media()
        if preload_media is None or preload_media.canonicalUrl().toLocalFile() != next_file:
            target_player.setMedia(QMediaContent(QUrl.fromLocalFile(next_file)))
        try:
            target_player.setPosition(0)
        except Exception:
            pass

        target_player.setVolume(0)
        target_player.play()

        self.crossfade_in_progress = True
        self.crossfade_target_index = next_index
        self.crossfade_start_time = time.monotonic()

        duration_ms = max(1, self.crossfade_duration_secs * 1000)
        if self.crossfade_timer:
            try:
                self.crossfade_timer.stop()
            except Exception:
                pass
        self.crossfade_timer = QTimer(self)
        self.crossfade_timer.timeout.connect(lambda: self._update_crossfade_step(duration_ms))
        self.crossfade_timer.start(30)

    def _update_crossfade_step(self, duration_ms):
        if not self.crossfade_in_progress:
            return
        elapsed_ms = int((time.monotonic() - self.crossfade_start_time) * 1000)
        ratio = min(1.0, elapsed_ms / duration_ms)
        target_volume = self.volume_slider.value() if hasattr(self, 'volume_slider') else 50
        fading_out = max(0, int(target_volume * (1.0 - ratio)))
        fading_in = max(0, int(target_volume * ratio))
        try:
            self.active_player.setVolume(fading_out)
            self.preload_player.setVolume(fading_in)
        except Exception:
            pass

        if ratio >= 1.0:
            if self.crossfade_timer:
                try:
                    self.crossfade_timer.stop()
                except Exception:
                    pass
                self.crossfade_timer = None
            self._finalize_crossfade()

    def _finalize_crossfade(self):
        if self.crossfade_target_index is None:
            self._cancel_crossfade()
            return

        new_player = self.preload_player
        old_player = self.active_player

        # Detach signals from the old active player
        self._disconnect_player_signals(old_player)
        try:
            old_player.stop()
        except Exception:
            pass

        # Swap references so the new track becomes active
        self.active_player = new_player
        self._connect_player_signals(self.active_player)
        self.preload_player = old_player

        # Restore user volume on the new active player
        target_volume = self.volume_slider.value() if hasattr(self, 'volume_slider') else 50
        try:
            self.active_player.setVolume(target_volume)
            self.preload_player.setVolume(target_volume)
        except Exception:
            pass

        next_idx = self.crossfade_target_index
        self.crossfade_in_progress = False
        self.crossfade_target_index = None
        self.crossfade_start_time = 0.0

        # Update UI/state to the new track without interrupting playback
        if 0 <= next_idx < len(self.playlist):
            self.pending_update_id += 1
            update_id = self.pending_update_id
            self.current_index = next_idx
            self.update_queue_duration_label()
            if hasattr(self, 'empty_label'):
                self.empty_label.setVisible(False)
            if hasattr(self, 'waveform_container'):
                self.waveform_container.setVisible(True)

            file_path = self.playlist[next_idx]
            self.update_dynamic_background(update_id=update_id)
            QTimer.singleShot(50, lambda: self.update_metadata_labels(file_path, update_id))
            QTimer.singleShot(0, lambda: self._deferred_compute_waveform(file_path, update_id))
            
            # Show playing icon in queue
            for i in range(self.queue_widget.count()):
                item = self.queue_widget.item(i)
                widget = self.queue_widget.itemWidget(item)
                if widget:
                    widget.set_playing(i == next_idx)

        # Ensure the play button reflects the active, playing state after swap
        self._update_play_icon()

        # Preload the subsequent track for future transitions
        QTimer.singleShot(150, self._preload_next_track)
    
    def position_changed(self, position):
        # Update waveform and time labels when position changes
        if self.active_player.duration() > 0:
            self.waveform.set_position(position, self.active_player.duration())
            self.current_time_label.setText(self.format_time(position))
        self.update_queue_duration_label()
        self._maybe_start_crossfade(position)
    
    def duration_changed(self, duration):
        # Update total time label when duration changes
        if duration > 0:
            self.total_time_label.setText(self.format_time(duration))
            self.waveform.set_position(self.active_player.position(), duration)
        self.update_queue_duration_label()

    def state_changed(self, state):
        try:
            # Ignore state flips from the fading-out player during crossfade
            if self.crossfade_in_progress:
                return
            # Update play/pause button text based on player state
            if state == QMediaPlayer.PlayingState:
                self._update_play_icon()
            else:
                self._update_play_icon()
            
            # Update mini control bar play state if settings or downloader tab is open
            if self.settings_tab_open or self.downloader_tab_open:
                is_playing = state == QMediaPlayer.PlayingState
                self.mini_control_bar.set_play_state(is_playing)
        except Exception:
            pass

    def media_status_changed(self, status):
        try:
            # Advance to next track when media finishes
            if status == QMediaPlayer.EndOfMedia:
                if self.crossfade_in_progress:
                    return
                self.next_track()
        except Exception:
            pass
    
    def update_waveform(self):
        if self.active_player.duration() > 0:
            current = self.active_player.position()
            total = self.active_player.duration()
            
            self.waveform.set_position(current, total)
            self.current_time_label.setText(self.format_time(current))
            self.total_time_label.setText(self.format_time(total))

    def extract_metadata(self, file_path):
        """Extract title and artist metadata from audio file"""
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return None, None
            
            title = None
            artist = None
            
            # Try to get title and artist from tags
            if hasattr(audio, 'tags') and audio.tags:
                # MP3 ID3 tags
                title = audio.tags.get('TIT2', [None])[0] if 'TIT2' in audio.tags else None
                artist = audio.tags.get('TPE1', [None])[0] if 'TPE1' in audio.tags else None
                
                # Convert to string if needed
                if title:
                    title = str(title)
                if artist:
                    artist = str(artist)
            
            # MP4/M4A tags
            if not title and '©nam' in audio:
                title = str(audio['©nam'][0])
            if not artist and '©ART' in audio:
                artist = str(audio['©ART'][0])
            
            # Vorbis comments (FLAC, OGG)
            if not title and 'title' in audio:
                title = str(audio['title'][0])
            if not artist and 'artist' in audio:
                artist = str(audio['artist'][0])
            
            return title, artist
            
        except Exception:
            return None, None
    
    def extract_album_art(self, file_path):
        """Extract album art from audio file metadata"""
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return None
            
            # Try different tag formats
            # MP3 (ID3)
            if hasattr(audio, 'tags') and audio.tags:
                for key in audio.tags.keys():
                    if 'APIC' in key:  # Attached Picture
                        return audio.tags[key].data
            
            # MP4/M4A
            if 'covr' in audio:
                return bytes(audio['covr'][0])
            
            # FLAC
            if hasattr(audio, 'pictures') and audio.pictures:
                return audio.pictures[0].data
            
            # OGG Vorbis
            if 'metadata_block_picture' in audio:
                import base64
                data = base64.b64decode(audio['metadata_block_picture'][0])
                # Parse FLAC picture block
                return data[32:]  # Skip header
            
        except Exception as e:
            pass
        
        return None
    
    def get_dominant_color(self, image_data):
        """Calculate dominant color from image data"""
        try:
            # Load image
            img = Image.open(io.BytesIO(image_data))
            
            # Resize for faster processing
            img = img.resize((150, 150))
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Get pixel data (using get_flattened_data instead of deprecated getdata)
            try:
                # Try new method first (Pillow 10.0.0+)
                pixels = list(img.get_flattened_data())
            except AttributeError:
                # Fallback to old method for older Pillow versions
                pixels = list(img.getdata())
            
            # Filter out very dark and very light pixels for better color extraction
            filtered_pixels = [p for p in pixels if sum(p) > 50 and sum(p) < 700]
            if not filtered_pixels:
                filtered_pixels = pixels
            
            # Calculate average color
            r_avg = sum(p[0] for p in filtered_pixels) // len(filtered_pixels)
            g_avg = sum(p[1] for p in filtered_pixels) // len(filtered_pixels)
            b_avg = sum(p[2] for p in filtered_pixels) // len(filtered_pixels)
            
            # Enhance saturation for more vibrant colors
            max_val = max(r_avg, g_avg, b_avg)
            min_val = min(r_avg, g_avg, b_avg)
            
            if max_val > 0:
                # Boost saturation by increasing the difference between colors
                mid = (max_val + min_val) / 2
                factor = 1.5
                
                r_avg = int(mid + (r_avg - mid) * factor)
                g_avg = int(mid + (g_avg - mid) * factor)
                b_avg = int(mid + (b_avg - mid) * factor)
                
                # Clamp values
                r_avg = max(0, min(255, r_avg))
                g_avg = max(0, min(255, g_avg))
                b_avg = max(0, min(255, b_avg))
            
            return QColor(r_avg, g_avg, b_avg)
            
        except Exception as e:
            return None
    
    def compute_waveform(self, file_path, target_samples=1000):
        # Try to read WAV files for real waveform data; otherwise generate deterministic fallback
        try:
            if file_path.lower().endswith('.wav'):
                with wave.open(file_path, 'rb') as wf:
                    nframes = wf.getnframes()
                    nch = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    raw = wf.readframes(nframes)

                total_values = nframes * nch
                if sampwidth == 1:
                    fmt = f"{total_values}B"
                    vals = struct.unpack(fmt, raw)
                    # convert unsigned to signed
                    vals = [v - 128 for v in vals]
                elif sampwidth == 2:
                    fmt = f"<{total_values}h"
                    vals = struct.unpack(fmt, raw)
                else:
                    raise ValueError("Unsupported sample width")

                # compute per-frame amplitude (average across channels)
                amplitudes = []
                for i in range(nframes):
                    offset = i * nch
                    s = 0
                    for c in range(nch):
                        s += abs(vals[offset + c])
                    amplitudes.append(s / nch)

                max_amp = max(amplitudes) if amplitudes else 1
                if max_amp == 0:
                    max_amp = 1
                normalized = [a / max_amp for a in amplitudes]

                # downsample to target_samples
                step = max(1, len(normalized) // target_samples)
                out = []
                for i in range(0, len(normalized), step):
                    chunk = normalized[i:i+step]
                    out.append(sum(chunk) / len(chunk))

                # trim/pad
                if len(out) > target_samples:
                    out = out[:target_samples]
                elif len(out) < target_samples:
                    out += [0.0] * (target_samples - len(out))

                return out
        except Exception:
            pass

        # Fallback: deterministic pseudo-random waveform based on file path
        try:
            seed = abs(hash(file_path)) % (2**32)
            rng = random.Random(seed)
            out = []
            last = rng.random()
            for i in range(target_samples):
                # smooth values a bit
                v = (last * 0.8) + (rng.random() * 0.2)
                last = v
                out.append(max(0.02, v))
            return out
        except Exception:
            return [0.1] * target_samples

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                self.shuffle_mode = data.get('shuffle_mode', False)
                self.repeat_mode = data.get('repeat_mode', 0)
                self.saved_folder = data.get('saved_folder', None)
                self.text_fade_enabled = data.get('text_fade_enabled', True)
                vol = data.get('volume', 50)
                try:
                    self.active_player.setVolume(vol)
                    self.preload_player.setVolume(vol)
                    if hasattr(self, 'volume_slider'):
                        self.volume_slider.setValue(vol)
                        self._update_volume_icon(vol)
                    if hasattr(self, 'mini_control_bar'):
                        self.mini_control_bar.volume_slider.blockSignals(True)
                        self.mini_control_bar.volume_slider.setValue(vol)
                        self.mini_control_bar.volume_slider.blockSignals(False)
                        self.mini_control_bar.update_volume_icon(vol)
                except Exception:
                    pass
                # Don't restore playlist - only saved_folder is remembered
                # Files added via "Add File" are not persisted
            else:
                self.shuffle_mode = False
                self.repeat_mode = 0
                self.text_fade_enabled = True
        except Exception as e:
            print("Failed to load settings:", e)
            self.shuffle_mode = False
            self.repeat_mode = 0
            self.text_fade_enabled = True
    
    def save_settings(self):
        """Save current settings to file"""
        try:
            data = {
                'shuffle_mode': self.shuffle_mode,
                'repeat_mode': self.repeat_mode,
                'volume': self.active_player.volume(),
                'saved_folder': self.saved_folder,
                'text_fade_enabled': self.text_fade_enabled
            }
            # Don't save playlist - only saved_folder is remembered
            # Files added via "Add File" are not persisted, app resets on close
            with open(self.settings_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("Failed to save settings:", e)

    def format_time(self, ms):
        try:
            seconds = int(ms // 1000)
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            if h > 0:
                return f"{h}:{m:02d}:{s:02d}"
            return f"{m}:{s:02d}"
        except Exception:
            return "0:00"
    
    def closeEvent(self, event):
        """Save settings and clean up resources before closing"""
        try:
            if hasattr(self, "downloader_proc") and self.downloader_proc:
                if self.downloader_proc.poll() is None:
                    self.downloader_proc.terminate()
        except Exception:
            pass
        
        # Clear caches to prevent memory leaks
        try:
            if hasattr(self, "album_art_pixmap_cache"):
                self.album_art_pixmap_cache.clear()
            if hasattr(self, "dominant_color_cache"):
                self.dominant_color_cache.clear()
            if hasattr(self, "track_durations"):
                self.track_durations.clear()
        except Exception:
            pass

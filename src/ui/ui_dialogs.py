"""Dialog components for the Aurion music player"""

import os
import re
import threading
import subprocess
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QSlider, QLabel, QLineEdit, QToolButton,
                             QScrollArea, QCheckBox, QComboBox, QMessageBox,
                             QProgressBar, QFileDialog, QSizePolicy, QInputDialog,
                             QSplitter)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize
from PyQt5.QtGui import QPixmap
from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
from src.config.ffmpeg_manager import get_ffmpeg_path
from src.ui.ui_widgets import ScalableAlbumArtLabel


class OverlayPanel(QWidget):
    """Overlay panel that appears above the player when queue is shown in small windows"""
    overlayClosed = pyqtSignal()
    
    def __init__(self, queue_widget):
        super().__init__()
        self.queue_widget = queue_widget
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: rgba(30, 30, 30, 0.95);")
        self.overlay_animation = None
        
        # Create layout for overlay
        overlay_layout = QVBoxLayout(self)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(0)
        
        # Queue header
        queue_header = QWidget()
        queue_header.setFixedHeight(60)
        queue_header.setStyleSheet("background-color: transparent;")
        queue_header_layout = QHBoxLayout(queue_header)
        queue_header_layout.setContentsMargins(15, 10, 15, 10)
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(40, 40)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: white;
                font-size: 24px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 20px;
            }
        """)
        close_btn.clicked.connect(self.hide)
        queue_header_layout.addWidget(close_btn)
        
        queue_title = QLabel("Queue")
        queue_title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        queue_header_layout.addWidget(queue_title)
        
        # Search input (overlay)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search songs or artists...")
        self.search_input.setStyleSheet("""
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
        self.search_input.setMaximumWidth(200)
        queue_header_layout.addWidget(self.search_input)
        
        queue_header_layout.addStretch()

        # Remaining playtime display for overlay queue
        self.total_duration_label = QLabel("Remaining 0:00")
        self.total_duration_label.setStyleSheet("color: rgba(255, 255, 255, 0.75); font-size: 13px;")
        queue_header_layout.addWidget(self.total_duration_label)
        
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
        # Connection is made by parent (AmberolPlayer)
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
        # Connection is made by parent (AmberolPlayer)
        queue_header_layout.addWidget(clear_btn)
        
        overlay_layout.addWidget(queue_header)
        
        # Queue list in scroll area (no widget attached by default)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
        overlay_layout.addWidget(self.scroll_area)
        
        # Store button references for parent to connect signals
        self.reset_btn = reset_btn
        self.clear_btn = clear_btn
    
    def attach_queue_widget(self, widget):
        try:
            existing = self.scroll_area.takeWidget()
        except Exception:
            existing = None
        if widget is not None:
            self.scroll_area.setWidget(widget)
    
    def detach_queue_widget(self):
        try:
            return self.scroll_area.takeWidget()
        except Exception:
            return None
    
    def update_geometry_to_parent(self):
        try:
            parent = self.parentWidget()
            if parent is not None:
                self.setGeometry(0, 0, parent.width(), parent.height())
        except Exception:
            pass

    def animate_slide_in(self):
        """Slide in overlay from left side at 90% width"""
        from src.config.gui_config import get_config
        parent = self.parentWidget()
        if parent is None:
            return
        
        # Stop any existing animation
        if self.overlay_animation and self.overlay_animation.state() == QPropertyAnimation.Running:
            self.overlay_animation.stop()
        
        # Calculate full width
        target_width = parent.width()
        parent_height = parent.height()
        
        # Position off-screen to the left initially
        self.setGeometry(-target_width, 0, target_width, parent_height)
        super().show()
        self.raise_()
        
        # Animate slide in from left
        config = get_config()
        self.overlay_animation = QPropertyAnimation(self, b"geometry")
        self.overlay_animation.setDuration(config.overlay_animation_duration)
        self.overlay_animation.setStartValue(self.geometry())
        self.overlay_animation.setEndValue(self.geometry().adjusted(target_width, 0, target_width, 0))  # Slide to x=0
        self.overlay_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.overlay_animation.start()
    
    def animate_slide_out(self):
        """Slide out overlay to the left"""
        from src.config.gui_config import get_config
        # Stop any existing animation
        if self.overlay_animation and self.overlay_animation.state() == QPropertyAnimation.Running:
            self.overlay_animation.stop()
        
        current_geom = self.geometry()
        target_x = -current_geom.width()
        
        config = get_config()
        self.overlay_animation = QPropertyAnimation(self, b"geometry")
        self.overlay_animation.setDuration(config.overlay_animation_duration)
        self.overlay_animation.setStartValue(current_geom)
        self.overlay_animation.setEndValue(current_geom.adjusted(target_x, 0, target_x, 0))  # Slide to off-screen left
        self.overlay_animation.setEasingCurve(QEasingCurve.InCubic)
        
        def on_finished():
            super(OverlayPanel, self).hide()
        
        self.overlay_animation.finished.connect(on_finished)
        self.overlay_animation.start()
    
    def show(self):
        """Show overlay panel with slide animation"""
        self.animate_slide_in()
    
    def hide(self):
        """Hide overlay panel with slide animation"""
        if self.isVisible():
            self.animate_slide_out()
    
    def hideEvent(self, event):
        try:
            self.overlayClosed.emit()
        except Exception:
            pass
        super().hideEvent(event)


class SettingsDialog(QDialog):
    """Settings dialog for configuring audio playback options"""
    crossfadeChanged = pyqtSignal(int)
    textFadeChanged = pyqtSignal(bool)

    def __init__(self, parent=None, initial_value=0, text_fade_enabled=True):
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setModal(False)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(360, 310)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        header_row.addWidget(title)
        header_row.addStretch()

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 14px;
                color: white;
                font-size: 14px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
            }
        """)
        close_btn.clicked.connect(self.close)
        header_row.addWidget(close_btn)

        layout.addLayout(header_row)

        subtitle = QLabel("Crossfade between songs")
        subtitle.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 0.75);")
        layout.addWidget(subtitle)

        slider_row = QVBoxLayout()
        slider_row.setSpacing(6)

        self.crossfade_slider = QSlider(Qt.Horizontal)
        self.crossfade_slider.setRange(0, 12)
        self.crossfade_slider.setValue(initial_value)
        self.crossfade_slider.setTickInterval(1)
        self.crossfade_slider.setStyleSheet("""
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
        self.crossfade_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.crossfade_slider)

        self.value_label = QLabel(f"{initial_value} s")
        self.value_label.setStyleSheet("color: white; font-size: 14px;")
        slider_row.addWidget(self.value_label)

        layout.addLayout(slider_row)

        # Text fade animation toggle
        text_fade_label = QLabel("Song title & artist fade transition")
        text_fade_label.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 0.75);")
        layout.addWidget(text_fade_label)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)

        from PyQt5.QtWidgets import QCheckBox
        self.text_fade_checkbox = QCheckBox("Enable smooth fade animation")
        self.text_fade_checkbox.setChecked(text_fade_enabled)
        self.text_fade_checkbox.setStyleSheet("""
            QCheckBox {
                color: white;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid rgba(255, 255, 255, 0.3);
                background-color: transparent;
            }
            QCheckBox::indicator:checked {
                background-color: rgba(82, 148, 226, 0.8);
                border: 2px solid rgba(82, 148, 226, 1);
            }
            QCheckBox::indicator:hover {
                border: 2px solid rgba(82, 148, 226, 0.6);
            }
        """)
        self.text_fade_checkbox.toggled.connect(self._on_text_fade_changed)
        toggle_row.addWidget(self.text_fade_checkbox)
        toggle_row.addStretch()

        layout.addLayout(toggle_row)

        layout.addStretch()

        self.setStyleSheet("""
            QDialog#settingsDialog {
                background-color: rgba(20, 20, 20, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)

    def _on_slider_changed(self, value):
        self.value_label.setText(f"{value} s")
        self.crossfadeChanged.emit(value)

    def _on_text_fade_changed(self, checked):
        self.textFadeChanged.emit(checked)

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent()
        if parent:
            parent_rect = parent.geometry()
            self_rect = self.frameGeometry()
            x = parent_rect.x() + (parent_rect.width() - self_rect.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - self_rect.height()) // 2
            self.move(x, y)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class SettingsTab(QWidget):
    """Settings tab that takes up most of the window (leaving 100px for control bar)"""
    crossfadeChanged = pyqtSignal(int)
    textFadeChanged = pyqtSignal(bool)
    closeRequested = pyqtSignal()

    def __init__(self, parent=None, initial_value=0, text_fade_enabled=True):
        super().__init__(parent)
        self.setObjectName("settingsTabRoot")
        self.setStyleSheet("""
            #settingsTabRoot {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0c1220, stop:0.55 #0a0d15, stop:1 #04060a);
            }
            QLabel {
                background-color: transparent;
                color: rgba(255, 255, 255, 0.92);
            }
            QCheckBox {
                color: rgba(255, 255, 255, 0.92);
            }
            QCheckBox::indicator {
                background-color: rgba(255, 255, 255, 0.08);
                border: 2px solid rgba(255, 255, 255, 0.28);
            }
            #settingsCard {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 18px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Header with title and close button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")
        header_row.addWidget(title)
        header_row.addStretch()
        
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(40, 40)
        close_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 20px;
                color: white;
                font-size: 18px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
            }
        """)
        close_btn.clicked.connect(self.closeRequested.emit)
        header_row.addWidget(close_btn)
        
        layout.addLayout(header_row)
        
        # Divider
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
        layout.addWidget(divider)

        content_card = QWidget()
        content_card.setObjectName("settingsCard")
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)
        layout.addWidget(content_card)
        
        # Crossfade section
        crossfade_title = QLabel("Crossfade between songs")
        crossfade_title.setStyleSheet("font-size: 18px; font-weight: bold; color: white; margin-top: 20px;")
        content_layout.addWidget(crossfade_title)
        
        crossfade_desc = QLabel("Smoothly transition between tracks with configurable overlap")
        crossfade_desc.setStyleSheet("font-size: 13px; color: rgba(255, 255, 255, 0.78);")
        content_layout.addWidget(crossfade_desc)
        
        slider_row = QVBoxLayout()
        slider_row.setSpacing(12)
        
        self.crossfade_slider = QSlider(Qt.Horizontal)
        self.crossfade_slider.setRange(0, 12)
        self.crossfade_slider.setValue(initial_value)
        self.crossfade_slider.setTickInterval(1)
        self.crossfade_slider.setFixedHeight(8)
        self.crossfade_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 20px;
                height: 20px;
                margin: -7px 0;
                border-radius: 10px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(126, 180, 255, 0.92);
                border-radius: 3px;
            }
        """)
        self.crossfade_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.crossfade_slider)
        
        slider_info_row = QHBoxLayout()
        slider_info_row.setContentsMargins(0, 0, 0, 0)
        
        slider_info_row.addStretch()
        
        self.value_label = QLabel(f"{initial_value} s")
        self.value_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        slider_info_row.addWidget(self.value_label)
        
        slider_row.addLayout(slider_info_row)
        content_layout.addLayout(slider_row)
        
        # Divider
        divider2 = QWidget()
        divider2.setFixedHeight(1)
        divider2.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
        content_layout.addWidget(divider2)
        
        # Text fade section
        text_fade_title = QLabel("Animations")
        text_fade_title.setStyleSheet("font-size: 18px; font-weight: bold; color: white; margin-top: 20px;")
        content_layout.addWidget(text_fade_title)
        
        text_fade_desc = QLabel("Enable smooth fade animations when switching songs")
        text_fade_desc.setStyleSheet("font-size: 13px; color: rgba(255, 255, 255, 0.78);")
        content_layout.addWidget(text_fade_desc)
        
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        
        self.text_fade_checkbox = QCheckBox("Enable smooth fade animation")
        self.text_fade_checkbox.setChecked(text_fade_enabled)
        self.text_fade_checkbox.setStyleSheet("""
            QCheckBox {
                color: rgba(255, 255, 255, 0.92);
                font-size: 14px;
                spacing: 10px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 2px solid rgba(255, 255, 255, 0.35);
                background-color: rgba(255, 255, 255, 0.04);
            }
            QCheckBox::indicator:checked {
                background-color: rgba(126, 180, 255, 0.95);
                border: 2px solid rgba(126, 180, 255, 1);
            }
            QCheckBox::indicator:hover {
                border: 2px solid rgba(126, 180, 255, 0.7);
            }
        """)
        self.text_fade_checkbox.toggled.connect(self._on_text_fade_changed)
        toggle_row.addWidget(self.text_fade_checkbox)
        toggle_row.addStretch()
        
        content_layout.addLayout(toggle_row)
        
        # Add stretch to push everything to top
        content_layout.addStretch()
        layout.addStretch()

    def _on_slider_changed(self, value):
        self.value_label.setText(f"{value} s")
        self.crossfadeChanged.emit(value)

    def _on_text_fade_changed(self, checked):
        self.textFadeChanged.emit(checked)


class MiniControlBar(QWidget):
    """Compact control bar for the bottom 50px when settings tab is open"""
    
    playPauseRequested = pyqtSignal()
    nextTrackRequested = pyqtSignal()
    previousTrackRequested = pyqtSignal()
    shuffleToggleRequested = pyqtSignal()
    repeatToggleRequested = pyqtSignal()
    volumeChanged = pyqtSignal(int)
    
    def __init__(self, parent=None, icons=None):
        super().__init__(parent)
        self.setObjectName("miniControlBar")
        self.setFixedHeight(100)
        self.setStyleSheet("""
            #miniControlBar {
                background-color: rgba(20, 20, 20, 0.98);
                border-top: 1px solid rgba(255, 255, 255, 0.1);
            }
            QSlider {
                background-color: transparent;
                border: none;
            }
            QLabel {
                background-color: transparent;
                border: none;
            }
        """)
        
        # Store icon references
        self.icons = icons or {}
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 8, 15, 8)
        layout.setSpacing(15)
        
        # Album art thumbnail - larger now
        self.album_art = ScalableAlbumArtLabel()
        self.album_art.setFixedSize(80, 80)
        self.album_art.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }
        """)
        self.album_art.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.album_art)
        
        # Song info (title and artist)
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)
        
        self.song_title = QLabel("No song playing")
        self.song_title.setStyleSheet("font-size: 14px; font-weight: bold; color: white; background-color: transparent; margin: 0px; padding: 0px; line-height: 1;")
        self.song_title.setMaximumWidth(250)
        self.song_title.setAlignment(Qt.AlignBottom)
        info_layout.addWidget(self.song_title)
        
        self.song_artist = QLabel("")
        self.song_artist.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.7); background-color: transparent; margin: 0px; padding: 0px; line-height: 1;")
        self.song_artist.setMaximumWidth(250)
        self.song_artist.setAlignment(Qt.AlignTop)
        info_layout.addWidget(self.song_artist)
        
        layout.addLayout(info_layout)
        layout.addStretch()
        
        # Compact controls
        btn_style = """
            QToolButton {
                background-color: transparent;
                border: none;
                color: white;
                padding: 6px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }
            QToolButton:checked {
                background-color: rgba(82, 148, 226, 0.5);
                border-radius: 6px;
            }
        """
        
        self.shuffle_btn = QToolButton()
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setFixedSize(44, 44)
        self.shuffle_btn.setToolTip("Shuffle")
        self.shuffle_btn.setStyleSheet(btn_style)
        self.shuffle_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        if 'shuffle' in self.icons:
            self.shuffle_btn.setIcon(self.icons['shuffle'])
            self.shuffle_btn.setIconSize(QSize(22, 22))
        else:
            self.shuffle_btn.setText("🔀")
        self.shuffle_btn.clicked.connect(self.shuffleToggleRequested.emit)
        layout.addWidget(self.shuffle_btn)
        
        self.prev_btn = QToolButton()
        self.prev_btn.setFixedSize(44, 44)
        self.prev_btn.setToolTip("Previous")
        self.prev_btn.setStyleSheet(btn_style)
        self.prev_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        if 'skip_back' in self.icons:
            self.prev_btn.setIcon(self.icons['skip_back'])
            self.prev_btn.setIconSize(QSize(22, 22))
        else:
            self.prev_btn.setText("⏮")
        self.prev_btn.clicked.connect(self.previousTrackRequested.emit)
        layout.addWidget(self.prev_btn)
        
        self.play_btn = QToolButton()
        self.play_btn.setFixedSize(56, 56)
        self.play_btn.setToolTip("Play/Pause")
        self.play_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        if 'play' in self.icons:
            self.play_btn.setIcon(self.icons['play'])
            self.play_btn.setIconSize(QSize(28, 28))
        else:
            self.play_btn.setText("▶")
        self.play_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(82, 148, 226, 0.3);
                border: none;
                color: white;
                border-radius: 28px;
            }
            QToolButton:hover {
                background-color: rgba(82, 148, 226, 0.5);
            }
        """)
        self.play_btn.clicked.connect(self.playPauseRequested.emit)
        layout.addWidget(self.play_btn)
        
        self.next_btn = QToolButton()
        self.next_btn.setFixedSize(44, 44)
        self.next_btn.setToolTip("Next")
        self.next_btn.setStyleSheet(btn_style)
        self.next_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        if 'skip_fwd' in self.icons:
            self.next_btn.setIcon(self.icons['skip_fwd'])
            self.next_btn.setIconSize(QSize(22, 22))
        else:
            self.next_btn.setText("⏭")
        self.next_btn.clicked.connect(self.nextTrackRequested.emit)
        layout.addWidget(self.next_btn)
        
        self.repeat_btn = QToolButton()
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.setFixedSize(44, 44)
        self.repeat_btn.setToolTip("Repeat")
        self.repeat_btn.setStyleSheet(btn_style)
        self.repeat_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        if 'repeat_all' in self.icons:
            self.repeat_btn.setIcon(self.icons['repeat_all'])
            self.repeat_btn.setIconSize(QSize(22, 22))
        else:
            self.repeat_btn.setText("🔁")
        self.repeat_btn.clicked.connect(self.repeatToggleRequested.emit)
        layout.addWidget(self.repeat_btn)
        
        # Volume control
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)  # Default to 50%, will be updated when settings tab opens
        self.volume_slider.setFixedWidth(100)
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
        self.volume_slider.valueChanged.connect(self.volumeChanged.emit)
        self.volume_slider.valueChanged.connect(self.update_volume_icon)
        layout.addWidget(self.volume_slider)
        
        self.volume_icon = QLabel()
        self.volume_icon.setFixedSize(20, 20)
        self.volume_icon.setScaledContents(True)
        # Set default volume icon (will be updated by parent)
        if 'volume_low' in self.icons:
            self.volume_icon.setPixmap(self.icons['volume_low'].pixmap(20, 20))
        layout.addWidget(self.volume_icon)
    
    def set_album_art(self, pixmap):
        """Set the album art thumbnail"""
        if pixmap and not pixmap.isNull():
            # ScalableAlbumArtLabel handles automatic scaling on resize
            self.album_art.setPixmap(pixmap)
        else:
            self.album_art.setPixmap(QPixmap())
    
    def set_song_info(self, title, artist):
        """Update song title and artist"""
        self.song_title.setText(title if title else "No song")
        self.song_artist.setText(artist if artist else "")
    
    def set_play_state(self, is_playing):
        """Update play button state"""
        if 'pause' in self.icons and 'play' in self.icons:
            self.play_btn.setIcon(self.icons['pause'] if is_playing else self.icons['play'])
        else:
            self.play_btn.setText("⏸" if is_playing else "▶")
        self.play_btn.setToolTip("Pause" if is_playing else "Play")
    
    def update_shuffle_state(self, enabled):
        """Update shuffle button state"""
        self.shuffle_btn.setChecked(enabled)
    
    def update_repeat_state(self, repeat_mode):
        """Update repeat button state (0=off, 1=all, 2=one)"""
        if repeat_mode == 0:
            self.repeat_btn.setChecked(False)
            if 'repeat_all' in self.icons:
                self.repeat_btn.setIcon(self.icons['repeat_all'])
            else:
                self.repeat_btn.setText("🔁")
        elif repeat_mode == 1:
            self.repeat_btn.setChecked(True)
            if 'repeat_all' in self.icons:
                self.repeat_btn.setIcon(self.icons['repeat_all'])
            else:
                self.repeat_btn.setText("🔁")
        else:  # repeat_mode == 2
            self.repeat_btn.setChecked(True)
            if 'repeat_one' in self.icons:
                self.repeat_btn.setIcon(self.icons['repeat_one'])
            else:
                self.repeat_btn.setText("🔂")
    
    def update_volume_icon(self, value):
        """Update volume icon based on slider value"""
        if value == 0:
            if 'volume_none' in self.icons:
                self.volume_icon.setPixmap(self.icons['volume_none'].pixmap(20, 20))
        elif value <= 50:
            if 'volume_low' in self.icons:
                self.volume_icon.setPixmap(self.icons['volume_low'].pixmap(20, 20))
        else:
            if 'volume_high' in self.icons:
                self.volume_icon.setPixmap(self.icons['volume_high'].pixmap(20, 20))


class DownloaderTab(QWidget):
    """YouTube Music downloader tab integrated into the main player"""
    closeRequested = pyqtSignal()
    # Thread-safe UI signals
    resultsReady = pyqtSignal(object, str, object)  # (items_list, filter_type, source_label or None)
    clearResultsRequested = pyqtSignal()
    statusRequested = pyqtSignal(str, int)  # (text, percent)
    currentItemRequested = pyqtSignal(str)
    errorRequested = pyqtSignal(str, str)  # (title, text)
    infoRequested = pyqtSignal(str, str)   # (title, text)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("downloaderTabRoot")
        self.download_dir = ""
        self.ytmusic = None
        self.seen_tracks = set()
        self.results_cache = []
        self.result_widgets = []
        self.result_vars = []
        self.downloaded_keys = set()
        self.cookies_from_browser = None
        self.cookies_file = None
        
        try:
            self.ytmusic = YTMusic()
        except Exception:
            self.ytmusic = None
        
        self.setStyleSheet("""
            #downloaderTabRoot {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0c1220, stop:0.55 #0a0d15, stop:1 #04060a);
            }
            QLabel {
                background-color: transparent;
                color: rgba(255, 255, 255, 0.92);
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                color: white;
                padding: 8px;
            }
            QLineEdit:focus {
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(126, 180, 255, 0.5);
            }
            QComboBox {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                color: white;
                padding: 8px;
            }
            QComboBox:focus {
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(126, 180, 255, 0.5);
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 8px;
                color: white;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
            }
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                color: white;
            }
            QProgressBar::chunk {
                background-color: rgba(82, 148, 226, 0.7);
                border-radius: 5px;
            }
            QCheckBox {
                color: rgba(255, 255, 255, 0.92);
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                background-color: rgba(255, 255, 255, 0.08);
                border: 2px solid rgba(255, 255, 255, 0.28);
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background-color: rgba(82, 148, 226, 0.6);
                border: 2px solid rgba(126, 180, 255, 0.8);
                border-radius: 4px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 70)  # tighter margins, smaller bottom reserve
        layout.setSpacing(12)  # Increased spacing for better separation
        
        # Header
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        
        title = QLabel("YouTube Music Downloader")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")
        header_row.addWidget(title)
        header_row.addStretch()
        
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(40, 40)
        close_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 20px;
                color: white;
                font-size: 18px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
            }
        """)
        close_btn.clicked.connect(self.closeRequested.emit)
        header_row.addWidget(close_btn)
        
        layout.addLayout(header_row)
        
        # Divider
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
        layout.addWidget(divider)
        
        # Folder selection
        folder_section = QWidget()
        folder_layout = QHBoxLayout(folder_section)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(10)
        
        folder_label_title = QLabel("Download Folder:")
        folder_label_title.setStyleSheet("font-size: 13px; color: rgba(255, 255, 255, 0.8);")
        folder_layout.addWidget(folder_label_title)
        
        self.folder_label = QLabel("Not selected")
        self.folder_label.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.6);")
        self.folder_label.setWordWrap(True)
        folder_layout.addWidget(self.folder_label, 1)
        
        choose_folder_btn = QPushButton("Browse")
        choose_folder_btn.setMaximumWidth(100)
        choose_folder_btn.clicked.connect(self.choose_folder)
        folder_layout.addWidget(choose_folder_btn)
        
        layout.addWidget(folder_section)
        
        # Search section
        search_title = QLabel("Search YouTube Music")
        search_title.setStyleSheet("font-size: 14px; font-weight: bold; color: white; margin-top: 20px;")
        layout.addWidget(search_title)
        
        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_label = QLabel("Filter:")
        filter_label.setFixedWidth(60)
        filter_row.addWidget(filter_label)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["songs", "albums", "playlists"])
        self.filter_combo.setMaximumWidth(150)
        filter_row.addWidget(self.filter_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)
        
        # Search input
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("e.g. artist, song, album")
        layout.addWidget(self.search_entry)
        
        # Search button
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.search_music)
        layout.addWidget(search_btn)
        
        # Results panel with scroll area (will sit on the right of splitter)
        results_label = QLabel("Results")
        results_label.setStyleSheet("font-size: 14px; font-weight: bold; color: white; margin-top: 20px;")
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: transparent;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: transparent;
            }
        """)
        
        self.results_widget = QWidget()
        self.results_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(6)  # Reduced spacing
        self.results_layout.addStretch()  # Add stretch at bottom to prevent squishing
        scroll.setWidget(self.results_widget)

        self.results_panel = QWidget()
        results_panel_layout = QVBoxLayout(self.results_panel)
        results_panel_layout.setContentsMargins(0, 0, 0, 0)
        results_panel_layout.setSpacing(6)
        results_panel_layout.addWidget(results_label)
        results_panel_layout.addWidget(scroll)
        
        # Download buttons row
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)
        
        download_btn = QPushButton("⬇ Download Selected")
        download_btn.setMinimumHeight(32)
        download_btn.clicked.connect(self.download_selected)
        buttons_row.addWidget(download_btn)
        
        load_btn = QPushButton("Load Album/Playlist Tracks")
        load_btn.setMinimumHeight(32)
        load_btn.clicked.connect(self.load_selection_contents)
        buttons_row.addWidget(load_btn)
        
        # Compact "More Options" to toggle advanced section (URL + progress)
        more_btn = QToolButton()
        more_btn.setText("More Options")
        more_btn.setCheckable(True)
        more_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        more_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 8px;
                color: white;
                padding: 6px 10px;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
            }
        """)
        # Update label on toggle
        def _update_more_btn_text(checked):
            more_btn.setText("Less Options" if checked else "More Options")
        more_btn.toggled.connect(_update_more_btn_text)
        buttons_row.addStretch()
        buttons_row.addWidget(more_btn)
        layout.addLayout(buttons_row)

        # Advanced section (collapsible)
        self.advanced_section = QWidget()
        self.advanced_section.setMinimumHeight(350)  # Ensure enough height for all elements
        adv_layout = QVBoxLayout(self.advanced_section)
        adv_layout.setContentsMargins(0, 8, 0, 8)
        adv_layout.setSpacing(12)
        self.advanced_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        url_label = QLabel("Direct URL / Playlist")
        url_label.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.8);")
        adv_layout.addWidget(url_label)

        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText("https://...")
        self.url_entry.setMinimumHeight(32)
        adv_layout.addWidget(self.url_entry)
        
        url_btn = QPushButton("Download URL / Fetch Playlist")
        url_btn.setMinimumHeight(32)
        url_btn.clicked.connect(self.download_url)
        adv_layout.addWidget(url_btn)

        cookies_label = QLabel("Cookies / Anti-bot")
        cookies_label.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.8);")
        adv_layout.addWidget(cookies_label)

        cookies_col = QVBoxLayout()
        cookies_col.setSpacing(8)

        browser_cookies_btn = QPushButton("Use Browser Cookies")
        browser_cookies_btn.setToolTip("Uses --cookies-from-browser (e.g., chrome, brave, firefox)")
        browser_cookies_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        browser_cookies_btn.setMinimumHeight(32)
        browser_cookies_btn.clicked.connect(self.choose_browser_cookies)
        cookies_col.addWidget(browser_cookies_btn)

        file_cookies_btn = QPushButton("Load Cookies File")
        file_cookies_btn.setToolTip("Uses --cookies /path/to/cookies.txt")
        file_cookies_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        file_cookies_btn.setMinimumHeight(32)
        file_cookies_btn.clicked.connect(self.choose_cookies_file)
        cookies_col.addWidget(file_cookies_btn)

        adv_layout.addLayout(cookies_col)

        self.cookies_status_label = QLabel("Cookies: none")
        self.cookies_status_label.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.65);")
        self.cookies_status_label.setWordWrap(True)
        adv_layout.addWidget(self.cookies_status_label)
        
        progress_label = QLabel("Progress")
        progress_label.setStyleSheet("font-size: 12px; font-weight: bold; color: white;")
        adv_layout.addWidget(progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setMinimumHeight(24)
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        adv_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Idle")
        self.status_label.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.8);")
        adv_layout.addWidget(self.status_label)
        
        self.current_item_label = QLabel("")
        self.current_item_label.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.6);")
        self.current_item_label.setWordWrap(True)
        adv_layout.addWidget(self.current_item_label)
        
        self.advanced_section.setVisible(False)
        
        # Split view: left advanced options, right results
        self.content_splitter = QSplitter(Qt.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.addWidget(self.advanced_section)
        self.content_splitter.addWidget(self.results_panel)
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 2)
        # Start with advanced collapsed
        self.content_splitter.setSizes([0, 1])

        # Connect visibility toggle with layout update and splitter sizes
        def _toggle_advanced(checked):
            self.advanced_section.setVisible(checked)
            if checked:
                left = max(320, self.width() // 3)
                right = max(400, self.width() - left)
                self.content_splitter.setSizes([left, right])
            else:
                self.content_splitter.setSizes([0, max(1, self.width())])
        
        more_btn.toggled.connect(_toggle_advanced)
        layout.addWidget(self.content_splitter, 1)

        # Connect thread-safe signals to UI slots
        self.resultsReady.connect(self._on_results_ready)
        self.clearResultsRequested.connect(self._on_clear_results)
        self.statusRequested.connect(self._on_status_requested)
        self.currentItemRequested.connect(self._on_current_item_requested)
        self.errorRequested.connect(self._on_error_requested)
        self.infoRequested.connect(self._on_info_requested)
    
    def choose_folder(self):
        """Open folder browser dialog"""
        try:
            # Prefer native dialog (better theming on Linux/GTK)
            dlg = QFileDialog(self, "Choose Download Folder")
            dlg.setFileMode(QFileDialog.Directory)
            dlg.setOption(QFileDialog.ShowDirsOnly, True)
            # Force Qt dialog so we can fully style dropdowns (native can inherit unreadable theme)
            dlg.setOption(QFileDialog.DontUseNativeDialog, True)
            # Ensure readability across widgets, including the path combo/dropdown
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
                    background-color: rgba(82, 148, 226, 0.3);
                    border: none; border-radius: 6px; color: white; padding: 6px 12px;
                }
                QPushButton:hover { background-color: rgba(82, 148, 226, 0.5); }
                """
            )
            if dlg.exec_() == QDialog.Accepted:
                files = dlg.selectedFiles()
                folder = files[0] if files else ""
                if folder:
                    self.download_dir = folder
                    self.folder_label.setText(folder)
        except Exception:
            # Fallback to convenience API
            folder = QFileDialog.getExistingDirectory(self, "Choose Download Folder")
            if folder:
                self.download_dir = folder
                self.folder_label.setText(folder)

    def choose_browser_cookies(self):
        """Prompt for browser name to use --cookies-from-browser."""
        browser, ok = QInputDialog.getText(
            self,
            "Use Browser Cookies",
            "Browser name (e.g., chrome, brave, firefox, edge):",
            text="chrome",
        )
        if ok and browser.strip():
            self.cookies_from_browser = browser.strip()
            self.cookies_status_label.setText(f"Cookies: browser ({self.cookies_from_browser})")

    def choose_cookies_file(self):
        """Select cookies.txt to use --cookies /path/to/file."""
        try:
            # Force Qt dialog so we can fully style dropdowns (native can inherit unreadable theme)
            dlg = QFileDialog(self, "Select Cookies File")
            dlg.setFileMode(QFileDialog.ExistingFile)
            dlg.setNameFilter("Cookies (*.txt);;All Files (*)")
            dlg.setOption(QFileDialog.DontUseNativeDialog, True)
            # Ensure readability across widgets, including the path combo/dropdown
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
                path = files[0] if files else ""
                if path:
                    self.cookies_file = path
                    self.cookies_status_label.setText(f"Cookies file: {path}")
        except Exception:
            # Fallback to convenience API
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select cookies file",
                "",
                "Cookies (*.txt);;All Files (*)",
            )
            if path:
                self.cookies_file = path
                self.cookies_status_label.setText(f"Cookies file: {path}")
    
    def search_music(self):
        """Search YouTube Music"""
        if not self.ytmusic:
            self.show_error("Error", "YouTube Music API not available")
            return
        
        query = self.search_entry.text().strip()
        if not query:
            return
        
        filter_type = self.filter_combo.currentText()
        # Clear UI and update status via signals (thread-safe)
        self.clearResultsRequested.emit()
        self.statusRequested.emit("Searching...", 0)
        
        def _search():
            try:
                results = self.ytmusic.search(query, filter=filter_type)
                # Emit results to be processed on the UI thread
                self.resultsReady.emit(results, filter_type, None)
                self.statusRequested.emit(f"Found {len(results)} results", 0)
            except Exception as e:
                self.errorRequested.emit("Search Error", str(e))
                self.statusRequested.emit("Search failed", 0)
        
        thread = threading.Thread(target=_search, daemon=True)
        thread.start()
    
    def add_track_to_results(self, track, source_label=""):
        """Add a track to results"""
        title = track.get("title", "")
        artist = track.get("artists", [{}])[0].get("name", "") if track.get("artists") else ""
        video_id = track.get("videoId")
        key = video_id or (artist.strip(), title.strip())
        
        if key in self.seen_tracks:
            return
        
        self.seen_tracks.add(key)
        display = f"🎵 {artist} - {title}"
        if source_label:
            display = f"{display}  [{source_label}]"
        
        track_copy = dict(track)
        track_copy["resultType"] = "song"
        self.results_cache.append(track_copy)
        self.add_result_row(display)
    
    def add_album_to_results(self, album, source_label=""):
        """Add an album to results"""
        title = album.get("title", "")
        artist = album.get("artists", [{}])[0].get("name", "") if album.get("artists") else ""
        browse_id = album.get("browseId")
        key = browse_id or title
        
        if key in self.seen_tracks:
            return
        
        self.seen_tracks.add(key)
        display = f"💿 {artist} - {title}"
        if source_label:
            display = f"{display}  [{source_label}]"
        
        album_copy = dict(album)
        album_copy["resultType"] = "album"
        self.results_cache.append(album_copy)
        self.add_result_row(display)
    
    def add_playlist_to_results(self, playlist, source_label=""):
        """Add a playlist to results"""
        title = playlist.get("title", "")
        browse_id = playlist.get("browseId")
        key = browse_id or title
        
        if key in self.seen_tracks:
            return
        
        self.seen_tracks.add(key)
        display = f"📋 {title}"
        if source_label:
            display = f"{display}  [{source_label}]"
        
        playlist_copy = dict(playlist)
        playlist_copy["resultType"] = "playlist"
        self.results_cache.append(playlist_copy)
        self.add_result_row(display)
    
    def add_result_row(self, text):
        """Add a result row with checkbox"""
        checkbox = QCheckBox(text)
        checkbox.setChecked(False)
        checkbox.setMinimumHeight(32)  # Ensure checkbox is visible
        # Insert before the stretch item (stretch is always the last item)
        self.results_layout.insertWidget(self.results_layout.count() - 1, checkbox)
        self.result_vars.append(checkbox)
        self.result_widgets.append(checkbox)
    
    def clear_results(self):
        """Clear all results"""
        self.results_cache.clear()
        self.seen_tracks.clear()
        for widget in self.result_widgets:
            widget.deleteLater()
        self.result_widgets.clear()
        self.result_vars.clear()
    
    def selected_indices(self):
        """Get indices of selected results"""
        return [idx for idx, var in enumerate(self.result_vars) if var.isChecked()]

    def update_status(self, text, percent=0):
        """Thread-safe status helper routing through signal."""
        try:
            self.statusRequested.emit(text, int(percent))
        except Exception:
            # Fallback update on UI thread if signal connection failed
            self._on_status_requested(text, percent)
    
    def download_selected(self):
        """Download selected results"""
        indices = self.selected_indices()
        if not indices:
            self.show_info("No selection", "Please select items to download")
            return
        
        if not self.download_dir:
            self.show_error("Error", "Please choose a download folder first")
            return
        
        to_download = [self.results_cache[i] for i in indices]
        self.update_status("Preparing downloads...", 0)
        
        def _download():
            try:
                queued = []
                for item in to_download:
                    result_type = item.get("resultType", "song")
                    if result_type == "song":
                        video_id = item.get("videoId")
                        if video_id:
                            url = f"https://music.youtube.com/watch?v={video_id}"
                            queued.append((url, self.meta_from_track_dict(item)))
                    elif result_type == "album":
                        browse_id = item.get("browseId")
                        if browse_id:
                            try:
                                album = self.ytmusic.get_album(browse_id)
                                tracks = album.get("tracks", [])
                                for t in tracks:
                                    vid = t.get("videoId")
                                    if vid:
                                        url = f"https://music.youtube.com/watch?v={vid}"
                                        queued.append((url, self.meta_from_track_dict(t)))
                            except Exception as e:
                                self.show_error("Album error", str(e))
                    elif result_type == "playlist":
                        browse_id = item.get("browseId")
                        if browse_id:
                            try:
                                playlist = self.ytmusic.get_playlist(browse_id)
                                tracks = playlist.get("tracks", [])
                                for t in tracks:
                                    vid = t.get("videoId")
                                    if vid:
                                        url = f"https://music.youtube.com/watch?v={vid}"
                                        queued.append((url, self.meta_from_track_dict(t)))
                            except Exception as e:
                                self.show_error("Playlist error", str(e))
                
                if queued:
                    self.download_audio(queued)
            except Exception as e:
                self.show_error("Error", str(e))
                self.update_status("Error", 0)
        
        thread = threading.Thread(target=_download, daemon=True)
        thread.start()
    
    def load_selection_contents(self):
        """Load tracks from selected album or playlist"""
        indices = self.selected_indices()
        if not indices:
            self.show_info("No selection", "Please select an album or playlist")
            return
        
        if len(indices) != 1:
            self.show_error("Select one", "Please select only one album or playlist")
            return
        
        item = self.results_cache[indices[0]]
        self.clearResultsRequested.emit()
        self.statusRequested.emit("Loading...", 0)
        
        def _load():
            try:
                result_type = item.get("resultType", "song")
                if result_type == "album":
                    browse_id = item.get("browseId")
                    if browse_id:
                        album = self.ytmusic.get_album(browse_id)
                        tracks = album.get("tracks", [])
                        # Send tracks to UI with source label
                        self.resultsReady.emit(tracks, "songs", "Album")
                elif result_type == "playlist":
                    browse_id = item.get("browseId")
                    if browse_id:
                        playlist = self.ytmusic.get_playlist(browse_id)
                        tracks = playlist.get("tracks", [])
                        self.resultsReady.emit(tracks, "songs", "Playlist")
                
                self.statusRequested.emit("Tracks loaded", 0)
            except Exception as e:
                self.errorRequested.emit("Error", str(e))
                self.statusRequested.emit("Error loading", 0)
        
        thread = threading.Thread(target=_load, daemon=True)
        thread.start()
    
    def download_url(self):
        """Download from URL or fetch playlist"""
        url = self.url_entry.text().strip()
        if not url:
            return
        
        if not self.download_dir:
            self.show_error("Error", "Please choose a download folder first")
            return
        
        playlist_id = self.extract_playlist_id(url)
        if playlist_id:
            self.statusRequested.emit("Loading playlist tracks...", 0)
            self.clearResultsRequested.emit()
            
            def _load_playlist():
                try:
                    playlist = self.ytmusic.get_playlist(playlist_id)
                    tracks = playlist.get("tracks", [])
                    self.resultsReady.emit(tracks, "songs", "Playlist")
                    self.statusRequested.emit("Playlist loaded", 0)
                except Exception as e:
                    self.errorRequested.emit("Playlist error", str(e))
                    self.statusRequested.emit("Error", 0)
            
            thread = threading.Thread(target=_load_playlist, daemon=True)
            thread.start()
        else:
            self.statusRequested.emit("Starting download...", 0)
            self.currentItemRequested.emit(url)
            self.download_audio([(url, None)])
    
    def download_audio(self, urls_or_meta):
        """Download audio files"""
        if not self.download_dir:
            self.show_error("Error", "Please choose a download folder first")
            return
        
        # Normalize input
        normalized = []
        for item in urls_or_meta:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                normalized.append((item[0], item[1]))
            else:
                normalized.append((item, None))
        
        filtered_targets = []
        batch_seen = set()
        meta_lookup = {}
        
        for target, meta in normalized:
            vid = self.url_video_id(target)
            key = vid or target
            if key in batch_seen:
                continue
            batch_seen.add(key)
            filtered_targets.append((target, key))
            if meta:
                meta_lookup[key] = meta
        
        if not filtered_targets:
            self.show_info("Already downloaded", "All selected items were already downloaded")
            return
        
        ffmpeg_exe = get_ffmpeg_path()
        if not ffmpeg_exe:
            self.show_error("Error", "FFmpeg not found")
            return
        
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)

        # Detect Node.js runtime for signature solving
        node_path = None
        try:
            result = subprocess.run(["which", "node"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                node_path = result.stdout.strip()
        except Exception:
            pass

        cookie_opts = {}
        if self.cookies_from_browser:
            # yt-dlp expects tuple: (browser, profile, keyring)
            cookie_opts["cookiesfrombrowser"] = (self.cookies_from_browser, None, None)
        if self.cookies_file:
            cookie_opts["cookiefile"] = self.cookies_file
        
        def progress_hook(status):
            state = status.get("status")
            info = status.get("info_dict", {})
            title = info.get("title") or ""
            artist = info.get("artist") or ""
            filename = info.get("_filename") or status.get("filename", "")
            
            if state == "downloading":
                total = status.get("total_bytes") or status.get("total_bytes_estimate")
                downloaded = status.get("downloaded_bytes", 0)
                percent = (downloaded / total * 100) if total else 0
                self.statusRequested.emit("Downloading...", int(percent))
                if artist or title:
                    self.currentItemRequested.emit(f"{artist} - {title}")
                else:
                    self.currentItemRequested.emit(os.path.basename(filename))
            elif state == "finished":
                self.statusRequested.emit("Converting to MP3...", 100)
        
        ydl_opts = {
            **cookie_opts,
            "format": "bestaudio/best",
            "ffmpeg_location": ffmpeg_dir,
            "ignoreerrors": True,
            "outtmpl": os.path.join(self.download_dir, "%(artist)s - %(title)s.%(ext)s"),
            "progress_hooks": [progress_hook],
            "noplaylist": False,
            "addmetadata": True,  # Add metadata from source
            "embedthumbnail": True,  # Embed thumbnail in output
            "writethumbnail": True,  # Write thumbnail to disk so EmbedThumbnail can use it
            "convert_thumbnails": "jpg",  # Convert thumbnails to JPG for better compatibility
            "writethumbnail_minthumb_width": 300,  # Minimum thumbnail width (maintains aspect ratio)
            "writethumbnail_maxheight": 300,  # Maximum thumbnail height to prevent squishing
            "remote_components": ["ejs:npm"],  # Enable challenge solver via remote components (as list)
            "allow_unplayable_formats": True,  # Allow all available formats even if signature fails
            "js_runtimes": {"node": {}},  # Enable Node.js runtime for signature solving
            "postprocessor_args": [
                "-ar", "44100",
                "-b:a", "320k",
                "-minrate", "320k",
                "-maxrate", "320k",
                "-bufsize", "640k",
                "-codec:a", "libmp3lame",
            ],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                },
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                },
            ],
        }
        
        def _download():
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    to_download = []
                    skipped_existing = 0
                    failed_items = []
                    
                    for target, key in filtered_targets:
                        try:
                            info = ydl.extract_info(target, download=False)
                        except Exception:
                            info = None
                        
                        mp3_path = None
                        if info:
                            raw_name = ydl.prepare_filename(info)
                            base, _ = os.path.splitext(raw_name)
                            mp3_path = base + ".mp3"
                        
                        if mp3_path and os.path.exists(mp3_path):
                            skipped_existing += 1
                            continue
                        
                        to_download.append((target, key))
                    
                    if not to_download:
                        msg = "All selected items already exist."
                        if skipped_existing:
                            msg += f" Skipped {skipped_existing}."
                        self.infoRequested.emit("Already downloaded", msg)
                        return
                    
                    for idx, (target, key) in enumerate(to_download, start=1):
                        self.currentItemRequested.emit(f"Item {idx}/{len(to_download)}")
                        self.statusRequested.emit("Starting download...", 0)
                        try:
                            info = ydl.extract_info(target, download=True, process=True)
                            if not info:
                                raise RuntimeError("No info returned for download.")
                            
                            base_name = os.path.splitext(ydl.prepare_filename(info))[0]
                            mp3_path = base_name + ".mp3"
                            
                            meta = self.preferred_metadata(info)
                            override = meta_lookup.get(key)
                            if override:
                                meta.update({k: v for k, v in override.items() if v})
                            
                            self.update_status("Cleaning metadata...", 100)
                            
                            # Write metadata to MP3 file using ffmpeg
                            if os.path.exists(mp3_path):
                                self._write_mp3_metadata(mp3_path, meta)
                        except Exception as e:
                            failed_items.append((target, str(e)))
                            continue
                
                if failed_items:
                    details = "\n".join([f"- {t}: {err}" for t, err in failed_items])
                    error_text = f"Some downloads failed.\n\n{details}"
                    self._handle_download_error(RuntimeError(error_text))
                    return

                self.statusRequested.emit("All downloads finished", 100)
                self.infoRequested.emit("Done", "All downloads finished successfully")
            except Exception as e:
                self._handle_download_error(e)
        
        thread = threading.Thread(target=_download, daemon=True)
        thread.start()

    def _handle_download_error(self, err):
        """Centralized download error handler with cookie guidance."""
        text = str(err)
        normalized = text.lower().replace("’", "'")
        needs_cookies = (
            "confirm you're not a bot" in normalized
            or "no info returned for download" in normalized
            or "http error 403" in normalized
            or "403" in normalized
            or "forbidden" in normalized
        )
        secretstorage = "secretstorage" in normalized or "decrypt cookie" in normalized

        if secretstorage:
            message = (
                "Browser cookie decryption failed (secretstorage missing or locked).\n\n"
                "Options:\n"
                " • Install secretstorage: pip install secretstorage\n"
                " • Or export cookies to a file and use 'Load Cookies File'.\n\n"
                "FAQ: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
            )
            self.errorRequested.emit("Cookie decryption failed", message)
        elif needs_cookies:
            message = (
                "YouTube thinks you're a robot. Pass your cookies to yt-dlp to continue.\n\n"
                "Use the buttons under More Options → Cookies / Anti-bot to either:\n"
                " • Use Browser Cookies (--cookies-from-browser)\n"
                " • Load Cookies File (--cookies /path/to/cookies.txt)\n\n"
                "See instructions: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
            )
            self.errorRequested.emit("YouTube wants cookies", message)
        else:
            self.errorRequested.emit("Download failed", text)
        self.statusRequested.emit("Download failed", 0)
    
    # ===== UI slots for thread-safe updates =====
    def _on_results_ready(self, items, filter_type, source_label):
        """Process results on UI thread and populate list."""
        try:
            if not isinstance(items, list):
                return
            for item in items:
                # Normalize type across sources
                rt = item.get("resultType") or filter_type
                if rt == "song" or filter_type == "songs":
                    self.add_track_to_results(item, source_label or "")
                elif rt == "album":
                    self.add_album_to_results(item, source_label or "")
                elif rt == "playlist":
                    self.add_playlist_to_results(item, source_label or "")
        except Exception as e:
            # Best-effort: show error on UI
            self._on_error_requested("Render error", str(e))

    def _on_clear_results(self):
        self.clear_results()

    def _on_status_requested(self, text, percent):
        self.status_label.setText(text)
        try:
            self.progress_bar.setValue(int(percent))
        except Exception:
            self.progress_bar.setValue(0)

    def _on_current_item_requested(self, text):
        self.current_item_label.setText(text)

    def _on_error_requested(self, title, text):
        QMessageBox.critical(self, title, text)

    def _on_info_requested(self, title, text):
        QMessageBox.information(self, title, text)
    
    def show_error(self, title, text):
        """Show error message"""
        QMessageBox.critical(self, title, text)
    
    def show_info(self, title, text):
        """Show info message"""
        QMessageBox.information(self, title, text)
    
    def url_video_id(self, url: str):
        """Extract video ID from URL"""
        match = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", url)
        return match.group(1) if match else None
    
    def extract_playlist_id(self, url: str):
        """Extract playlist ID from URL"""
        match = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url)
        return match.group(1) if match else None
    
    def preferred_metadata(self, info_dict):
        """Extract metadata from info dict"""
        title = info_dict.get("track") or info_dict.get("title") or ""
        artist = info_dict.get("artist") or ""
        if not artist:
            artists = info_dict.get("artists") or []
            if artists and isinstance(artists, list):
                artist = artists[0].get("name") or artists[0].get("artist", "")
        
        album = info_dict.get("album") or ""
        year = info_dict.get("release_year") or info_dict.get("upload_year") or ""
        if not year:
            release_date = info_dict.get("release_date") or ""
            if isinstance(release_date, str) and len(release_date) >= 4:
                year = release_date[:4]
        
        return {
            "title": title.strip(),
            "artist": artist.strip(),
            "album": album.strip(),
            "year": str(year).strip(),
        }
    
    def meta_from_track_dict(self, track):
        """Build metadata dict from track"""
        title = track.get("title") or track.get("track") or ""
        artist = track.get("artist") or ""
        if not artist:
            artists = track.get("artists") or []
            if artists and isinstance(artists, list):
                artist = artists[0].get("name") or artists[0].get("artist", "")
        
        album = ""
        album_obj = track.get("album")
        if isinstance(album_obj, dict):
            album = album_obj.get("name") or album_obj.get("title") or ""
        elif isinstance(album_obj, str):
            album = album_obj
        
        year = track.get("year") or track.get("releaseYear") or track.get("release_year") or ""
        if not year:
            date_str = track.get("releaseDate") or track.get("published") or ""
            if isinstance(date_str, str) and len(date_str) >= 4:
                year = date_str[:4]
        
        return {
            "title": str(title).strip(),
            "artist": str(artist).strip(),
            "album": str(album).strip(),
            "year": str(year).strip(),
        }

    def _write_mp3_metadata(self, mp3_path, meta):
        """Write metadata to MP3 file using mutagen ID3 tags."""
        try:
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC
            
            # Try to load existing ID3 tags, or create new ones
            try:
                tags = ID3(mp3_path)
            except Exception:
                tags = ID3()
            
            # Write metadata using ID3v2 tags (universally compatible)
            title = meta.get("title", "").strip() or "Unknown"
            artist = meta.get("artist", "").strip() or "Unknown"
            album = meta.get("album", "").strip() or "Unknown"
            year = meta.get("year", "").strip()
            
            if title:
                tags.add(TIT2(encoding=3, text=[title]))
            if artist:
                tags.add(TPE1(encoding=3, text=[artist]))
            if album:
                tags.add(TALB(encoding=3, text=[album]))
            if year:
                tags.add(TDRC(encoding=3, text=[year]))
            
            # Save tags to file
            tags.save(mp3_path, v2_version=4)
        except ImportError:
            # Fallback to ffmpeg if mutagen not available
            self._write_mp3_metadata_ffmpeg(mp3_path, meta)
        except Exception:
            pass  # Silently skip if metadata writing fails

    def _write_mp3_metadata_ffmpeg(self, mp3_path, meta):
        """Fallback: Write metadata to MP3 file using ffmpeg."""
        try:
            ffmpeg_exe = get_ffmpeg_path()
            if not ffmpeg_exe:
                return
            
            temp_mp3 = mp3_path + ".tmp"
            
            title = meta.get("title", "").strip() or "Unknown"
            artist = meta.get("artist", "").strip() or "Unknown"
            album = meta.get("album", "").strip() or "Unknown"
            year = meta.get("year", "").strip()
            
            cmd = [
                ffmpeg_exe,
                "-i", mp3_path,
                "-c", "copy",
                "-metadata", f"title={title}",
                "-metadata", f"artist={artist}",
                "-metadata", f"album={album}",
            ]
            
            if year:
                cmd.extend(["-metadata", f"date={year}"])
            
            cmd.extend(["-y", temp_mp3])
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and os.path.exists(temp_mp3):
                os.replace(temp_mp3, mp3_path)
            elif os.path.exists(temp_mp3):
                os.remove(temp_mp3)
        except Exception:
            pass


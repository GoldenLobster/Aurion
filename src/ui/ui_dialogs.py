"""Dialog components for the Aurion music player"""

from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QSlider, QLabel, QLineEdit, QToolButton,
                             QScrollArea)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor


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

    def __init__(self, parent=None, initial_value=0):
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setModal(False)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(360, 210)

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

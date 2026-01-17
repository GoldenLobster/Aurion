"""
Custom PyQt5 widgets for the Aurion music player UI.
Includes waveform display, queue items, and background rendering.
"""

import random
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QListWidget, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, pyqtSignal, pyqtProperty, QSize
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap, QLinearGradient


class WaveformWidget(QWidget):
    """Interactive waveform display with hover preview and click-to-seek"""
    
    seekRequested = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.waveform_data = []
        self.current_position = 0
        self.duration = 1
        self.setMinimumHeight(80)
        from PyQt5.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.hover_x = None
        self.preview_visible = False
        
    def set_waveform_data(self, data):
        """Set waveform amplitude data for visualization"""
        self.waveform_data = data
        self.update()
    
    def set_position(self, position, duration):
        """Update current playback position and total duration"""
        self.current_position = position
        self.duration = max(duration, 1)
        self.update()
    
    def paintEvent(self, event):
        """Render waveform with progress indicator"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        width = self.width()
        height = self.height()
        center_y = height // 2
        
        # Define bar dimensions
        bar_width = 3
        spacing = 2
        available_width_per_bar = bar_width + spacing
        
        bar_count = max(1, width // available_width_per_bar)
        
        # Generate amplitudes based on waveform data or placeholder
        if not self.waveform_data:
            amplitudes = [random.randint(10, height - 20) for _ in range(bar_count)]
        else:
            samples_per_bar = max(1, len(self.waveform_data) // bar_count)
            amplitudes = []
            for i in range(bar_count):
                sample_start = i * samples_per_bar
                sample_end = min(sample_start + samples_per_bar, len(self.waveform_data))
                if sample_end > sample_start:
                    avg_amplitude = sum(self.waveform_data[sample_start:sample_end]) / (sample_end - sample_start)
                else:
                    avg_amplitude = 0
                amplitudes.append(int(avg_amplitude * (height - 20)))

        # Calculate progress
        progress = self.current_position / self.duration if self.duration > 0 else 0
        progress_x = progress * width

        # Draw bars
        for i in range(bar_count):
            bar_height = amplitudes[i] if i < len(amplitudes) else 0
            x = int(i * available_width_per_bar)

            if x < progress_x:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(82, 148, 226, 180))
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255, 100))

            y = center_y - bar_height // 2
            painter.drawRoundedRect(x, y, max(1, bar_width - spacing), bar_height, 2, 2)

        # Draw hover preview
        if self.preview_visible and self.hover_x is not None:
            try:
                hx = max(0, min(self.hover_x, width))
                pen = QPen(QColor(255, 255, 255, 180))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(hx, 0, hx, height)

                preview_ratio = hx / max(1, width)
                preview_ratio = max(0.0, min(1.0, preview_ratio))
                preview_ms = int(preview_ratio * self.duration)
                time_text = self._format_time(preview_ms)

                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(time_text) + 10
                th = fm.height() + 6
                tx = max(6, min(hx - tw // 2, width - tw - 6))
                ty = 6

                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 200))
                painter.drawRoundedRect(tx, ty, tw, th, 6, 6)

                painter.setPen(QColor(255, 255, 255))
                painter.drawText(tx + 5, ty + fm.ascent() + 3, time_text)
            except Exception:
                pass
    
    def mousePressEvent(self, event):
        """Handle click to seek"""
        if self.duration > 0:
            hx = max(0, min(event.pos().x(), self.width()))
            click_ratio = hx / max(1, self.width())
            click_ratio = max(0.0, min(1.0, click_ratio))
            seek_position = int(click_ratio * self.duration)
            self.seekRequested.emit(seek_position)

    def mouseMoveEvent(self, event):
        """Update hover preview position"""
        self.hover_x = event.pos().x()
        self.preview_visible = True
        self.update()

    def leaveEvent(self, event):
        """Hide hover preview when mouse leaves"""
        self.preview_visible = False
        self.hover_x = None
        self.update()

    def enterEvent(self, event):
        """Show preview when mouse enters"""
        self.preview_visible = True
        self.update()

    def _format_time(self, ms):
        """Format milliseconds as MM:SS"""
        try:
            seconds = int(ms // 1000)
            m = seconds // 60
            s = seconds % 60
            return f"{m}:{s:02d}"
        except Exception:
            return "0:00"


class QueueItemWidget(QWidget):
    """Custom widget for queue item with album art, song name, and artist"""
    
    def __init__(self, file_path, is_playing=False):
        super().__init__()
        self.file_path = file_path
        self.is_playing = is_playing
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Album art
        self.art_label = QLabel()
        self.art_label.setFixedSize(60, 60)
        self.art_label.setScaledContents(True)
        self.art_label.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            font-size: 24px;
        """)
        self.art_label.setAlignment(Qt.AlignCenter)
        self.art_label.setText("🎵")
        layout.addWidget(self.art_label)
        
        # Text info
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        text_layout.setContentsMargins(0, 0, 0, 0)
        
        self.song_label = QLabel()
        self.song_label.setStyleSheet("""
            font-size: 15px;
            font-weight: bold;
            color: white;
        """)
        self.song_label.setWordWrap(False)
        text_layout.addWidget(self.song_label)
        
        self.artist_label = QLabel()
        self.artist_label.setStyleSheet("""
            font-size: 13px;
            color: rgba(255, 255, 255, 0.7);
        """)
        self.artist_label.setWordWrap(False)
        text_layout.addWidget(self.artist_label)
        
        text_layout.addStretch()
        layout.addLayout(text_layout, 1)
        
        # Playing indicator
        self.playing_icon = QLabel()
        self.playing_icon.setFixedSize(20, 20)
        self.playing_icon.setScaledContents(True)
        self.playing_icon.setVisible(is_playing)
        layout.addWidget(self.playing_icon)
        
        self.setLayout(layout)
        self._update_background()
    
    def set_metadata(self, title, artist):
        """Set song title and artist"""
        self.song_label.setText(title if title else "Unknown Track")
        self.artist_label.setText(artist if artist else "Unknown Artist")
    
    def set_album_art(self, pixmap):
        """Set album art pixmap"""
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.art_label.setPixmap(scaled)
            self.art_label.setText("")
        else:
            self.art_label.setText("🎵")
            self.art_label.setPixmap(QPixmap())
    
    def set_playing(self, playing):
        """Update playing state - only show/hide the icon, don't highlight background"""
        self.is_playing = playing
        self.playing_icon.setVisible(playing)
    
    def _update_background(self):
        """Update widget background based on playing state"""
        if self.is_playing:
            self.setStyleSheet("""
                background-color: rgba(82, 148, 226, 0.3);
                border-radius: 8px;
            """)
        else:
            self.setStyleSheet("background-color: transparent;")


class QueueWidget(QListWidget):
    """Stylized list widget for displaying playlist queue"""
    
    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                color: #ffffff;
                font-size: 14px;
                padding: 10px;
                outline: none;
            }
            QListWidget::item {
                padding: 0px;
                margin: 4px 0px;
                border: none;
                border-radius: 8px;
                background-color: transparent;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: transparent;
                outline: none;
            }
            QListWidget::item:hover {
                background-color: transparent;
                outline: none;
            }
            QListWidget::item:focus {
                outline: none;
                background-color: transparent;
            }
        """)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)


class BlurredBackground(QLabel):
    """Animated background with gradient color transitions"""
    
    def __init__(self):
        super().__init__()
        self.setScaledContents(True)
        self.base_color = QColor(30, 30, 30, 200)
        self.last_use_gradient = True
    
    def get_animated_color(self):
        """Get current background color"""
        return self.base_color
    
    def set_animated_color(self, color):
        """Set background color (used for animations)"""
        self.base_color = color
        self.set_from_color(color)
    
    animatedColor = pyqtProperty(QColor, get_animated_color, set_animated_color)
        
    def set_from_color(self, color, use_gradient=True):
        """
        Generate background pixmap from color.
        
        Args:
            color: Base color for background
            use_gradient: Whether to create gradient or solid color
        """
        self.base_color = color
        self.last_use_gradient = use_gradient
        
        width = max(self.width(), 1000)
        height = max(self.height(), 1130)
        
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if use_gradient:
            # Create vibrant gradient background
            r = min(255, int(color.red() * 1.2))
            g = min(255, int(color.green() * 1.2))
            b = min(255, int(color.blue() * 1.2))
            
            r_dark = int(r * 0.3)
            g_dark = int(g * 0.3)
            b_dark = int(b * 0.3)
            
            gradient = QLinearGradient(0, 0, 0, height)
            gradient.setColorAt(0, QColor(r, g, b, 255))
            gradient.setColorAt(0.4, QColor(int(r*0.7), int(g*0.7), int(b*0.7), 255))
            gradient.setColorAt(0.7, QColor(int(r*0.4), int(g*0.4), int(b*0.4), 255))
            gradient.setColorAt(1, QColor(r_dark, g_dark, b_dark, 255))
            
            painter.fillRect(pixmap.rect(), gradient)
        else:
            # Solid color
            painter.fillRect(pixmap.rect(), color)
        
        painter.end()
        self.setPixmap(pixmap)

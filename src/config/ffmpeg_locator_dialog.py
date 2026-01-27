"""
Dialog for locating ffmpeg when system-installed version is not found.
"""

from pathlib import Path
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFileDialog, QTextEdit)


class FFmpegLocatorDialog(QDialog):
    """Dialog to help user locate ffmpeg/ffprobe binaries"""
    
    def __init__(self, parent=None, search_suggestions=None):
        super().__init__(parent)
        self.selected_path = None
        self.search_suggestions = search_suggestions or []
        self.init_ui()
    
    def init_ui(self):
        """Initialize dialog UI"""
        self.setWindowTitle("Locate FFmpeg")
        self.setModal(True)
        self.setFixedSize(600, 400)
        self.setStyleSheet("""
            QDialog {
                background-color: rgba(30, 30, 30, 0.95);
            }
            QLabel {
                color: white;
            }
            QTextEdit {
                background-color: rgba(50, 50, 50, 0.9);
                color: rgba(255, 255, 255, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 5px;
                padding: 8px;
            }
            QPushButton {
                background-color: rgba(82, 148, 226, 0.6);
                border: none;
                border-radius: 5px;
                color: white;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(82, 148, 226, 0.8);
            }
            QPushButton#cancelBtn {
                background-color: rgba(100, 100, 100, 0.6);
            }
            QPushButton#cancelBtn:hover {
                background-color: rgba(100, 100, 100, 0.8);
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("FFmpeg Not Found")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        layout.addWidget(title)
        
        # Explanation
        explanation = QLabel(
            "FFmpeg could not be found on your system.\n\n"
            "Please locate the directory containing 'ffmpeg' and 'ffprobe' binaries.\n\n"
            "You can either:\n"
            "• Install ffmpeg using your system's package manager\n"
            "• Download it from https://ffmpeg.org/download.html\n"
            "• Browse to an existing installation\n"
        )
        explanation.setStyleSheet("font-size: 13px; color: rgba(255, 255, 255, 0.8); line-height: 1.6;")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        
        # Common paths info
        if self.search_suggestions:
            paths_label = QLabel("Common paths to check:")
            paths_label.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.7); font-weight: bold;")
            layout.addWidget(paths_label)
            
            paths_text = QTextEdit()
            paths_text.setReadOnly(True)
            paths_text.setFixedHeight(100)
            paths_text.setText("\n".join(self.search_suggestions))
            layout.addWidget(paths_text)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        browse_btn = QPushButton("Browse for FFmpeg")
        browse_btn.clicked.connect(self.browse_for_ffmpeg)
        button_layout.addWidget(browse_btn)
        
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addStretch()
        layout.addLayout(button_layout)
    
    def browse_for_ffmpeg(self):
        """Open file browser to locate ffmpeg directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select FFmpeg Directory",
            "",
            options=QFileDialog.ShowDirsOnly
        )
        
        if directory:
            self.selected_path = Path(directory)
            self.accept()
    
    def get_selected_path(self) -> Path:
        """Get the selected ffmpeg directory"""
        return self.selected_path

"""Event handling for frameless window functionality"""

from PyQt5.QtWidgets import QWidget, QToolButton, QPushButton
from PyQt5.QtCore import Qt, QRect, QEvent, QCursor
from PyQt5.QtGui import QCursor as QCursorGUI


class FramelessWindowEventHandler:
    """Mixin class for handling frameless window events (drag, resize, etc)"""
    
    def _is_in_header_area(self, global_pos):
        """Check if position is in the draggable header area"""
        local_pos = self.mapFromGlobal(global_pos)
        header_height = 230
        window_width = self.width()
        right_side_width = 200
        return local_pos.y() < header_height and local_pos.x() < (window_width - right_side_width - 20)

    def _get_resize_region(self, global_pos):
        """Determine which edge/corner the cursor is in for resizing"""
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
        """Update cursor appearance based on position"""
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
        """Start a window resize operation"""
        self.resizing = True
        self.resize_direction = direction
        self.resize_start_geom = self.geometry()
        self.resize_start_pos = global_pos
        self.grabMouse()
        self._update_cursor_shape(global_pos)

    def _perform_resize(self, global_pos):
        """Handle actual resize movement"""
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
        """Handle window dragging from header"""
        if not self.isMaximized():
            self.move(global_pos - self.drag_position)

    def _handle_mouse_press_common(self, event):
        """Common mouse press handling for frameless window"""
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
            self.drag_position = global_pos - self.frameGeometry().topLeft()
            self.is_dragging_header = True
            return True

        return False

    def _handle_mouse_move_common(self, event):
        """Common mouse move handling for frameless window"""
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
        """Common mouse release handling for frameless window"""
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
        """Filter events for frameless window functionality"""
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

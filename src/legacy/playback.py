"""Playback control and crossfade logic for the Aurion player"""

import time
import random
from PyQt5.QtCore import QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl


class PlaybackController:
    """Mixin class for playback control methods (play, pause, next, previous, shuffle, repeat, etc)"""
    
    def toggle_play(self):
        """Toggle between play and pause states"""
        if self.active_player.state() == QMediaPlayer.PlayingState:
            self.active_player.pause()
        else:
            if self.current_index == -1 and self.playlist:
                self.play_track(0)
            else:
                self.active_player.play()
        self._update_play_icon()

    def show_settings_window(self):
        """Show or hide the settings dialog"""
        from ui_dialogs import SettingsDialog
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self, initial_value=self.crossfade_duration_secs)
            self.settings_dialog.crossfadeChanged.connect(self.set_crossfade_duration)
        if self.settings_dialog.isVisible():
            self.settings_dialog.close()
            return
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _update_play_icon(self):
        """Update play button icon based on current playback state"""
        try:
            if self.active_player.state() == QMediaPlayer.PlayingState:
                self.play_btn.setIcon(self.icon_pause)
            else:
                self.play_btn.setIcon(self.icon_play)
        except Exception:
            pass
    
    def next_track(self):
        """Skip to the next track"""
        self._cancel_crossfade()
        if not self.playlist:
            return
        
        if self.repeat_mode == 2:  # Repeat one
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
        """Go to the previous track"""
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
        """Toggle shuffle mode on/off"""
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

    def _update_shuffle_icon(self):
        """Update shuffle button appearance based on mode"""
        try:
            self.shuffle_btn.setChecked(self.shuffle_mode)
        except Exception:
            pass
    
    def toggle_repeat(self):
        """Cycle through repeat modes (off -> all -> one -> off)"""
        self.repeat_mode = (self.repeat_mode + 1) % 3
        self._update_repeat_icon()

    def _update_repeat_icon(self):
        """Update repeat button appearance based on mode"""
        try:
            if self.repeat_mode == 0:  # No repeat
                self.repeat_btn.setChecked(False)
                self.repeat_btn.setIcon(self.icon_repeat_all)
            elif self.repeat_mode == 1:  # Repeat all
                self.repeat_btn.setChecked(True)
                self.repeat_btn.setIcon(self.icon_repeat_all)
            else:  # Repeat one
                self.repeat_btn.setChecked(True)
                self.repeat_btn.setIcon(self.icon_repeat_one)
        except Exception:
            pass
    
    def seek_to_position(self, position):
        """Seek to a specific position in the current track"""
        self.active_player.setPosition(position)
    
    def change_volume(self, value):
        """Change playback volume"""
        self.active_player.setVolume(value)
        self.preload_player.setVolume(value)

    def set_crossfade_duration(self, seconds):
        """Set the crossfade duration in seconds"""
        seconds = max(0, min(12, int(seconds)))
        self.crossfade_duration_secs = seconds
        if self.settings_dialog:
            try:
                self.settings_dialog.crossfade_slider.setValue(seconds)
            except Exception:
                pass
            try:
                self.settings_dialog.value_label.setText(f"{seconds} s")
            except Exception:
                pass
        # Cancel any in-flight crossfade if duration is set to zero mid-transition
        if seconds == 0 and self.crossfade_in_progress:
            self._cancel_crossfade()

    def _cancel_crossfade(self):
        """Cancel an in-progress crossfade"""
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
        """Check if it's time to start crossfading to the next track"""
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
        """Begin crossfading to the specified next track"""
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
        """Handle each step of the crossfade animation"""
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
        """Complete the crossfade by swapping active and preload players"""
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

    # Shuffle helper methods

    def _reseed_shuffle_pool(self, preserve_current=True, reset_history=False):
        """Rebuild shuffle order so every track plays once before repeating"""
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
        """Keep shuffle helpers in sync with the playlist"""
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

        if self.repeat_mode == 2:  # Repeat one
            return self.current_index
        
        if self.shuffle_mode:
            self._prepare_shuffle_pool(allow_reseed=(not self.shuffle_seeded) or self.repeat_mode == 1)
            if not self.shuffle_pool:
                return -1
            return self.shuffle_pool[-1]

        next_idx = self.current_index + 1
        if next_idx >= len(self.playlist):
            if self.repeat_mode == 1:  # Repeat all
                return 0
            return -1
        return next_idx

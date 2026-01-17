"""
Audio processing utilities for waveform computation and dominant color extraction.
Handles audio decoding and image analysis for visual feedback.
"""

import wave
import struct
import io
from PIL import Image
from PyQt5.QtGui import QColor


def compute_waveform(file_path, target_samples=1000):
    """
    Compute waveform amplitude data from audio file.
    
    Args:
        file_path: Path to audio file
        target_samples: Number of amplitude samples to generate
        
    Returns:
        List of normalized amplitudes (0.0-1.0), or empty list on error
    """
    try:
        with wave.open(file_path, 'rb') as wav_file:
            n_frames = wav_file.getnframes()
            sample_width = wav_file.getsampwidth()
            n_channels = wav_file.getnchannels()
            
            # Calculate how many frames to read at a time
            frames_per_sample = max(1, n_frames // target_samples)
            amplitudes = []
            
            for i in range(target_samples):
                start_frame = i * frames_per_sample
                wav_file.setpos(start_frame)
                
                frames = wav_file.readframes(frames_per_sample)
                if not frames:
                    break
                
                # Unpack audio samples
                sample_count = len(frames) // (sample_width * n_channels)
                samples = struct.unpack(
                    f'<{sample_count * n_channels}h',
                    frames[:sample_count * sample_width * n_channels]
                )
                
                # Calculate RMS (root mean square) for this chunk
                if samples:
                    rms = (sum(s**2 for s in samples) / len(samples)) ** 0.5
                    normalized = min(1.0, rms / 32768.0)
                    amplitudes.append(normalized)
            
            return amplitudes
            
    except Exception:
        return []


def get_dominant_color(image_data):
    """
    Calculate dominant color from image data.
    
    Args:
        image_data: Image bytes
        
    Returns:
        QColor representing dominant color, or None on error
    """
    try:
        # Load image
        img = Image.open(io.BytesIO(image_data))
        
        # Resize for faster processing
        img = img.resize((150, 150))
        
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Get pixel data
        try:
            pixels = list(img.get_flattened_data())
        except AttributeError:
            pixels = list(img.getdata())
        
        # Filter out very dark and very light pixels
        filtered_pixels = [p for p in pixels if sum(p) > 50 and sum(p) < 700]
        if not filtered_pixels:
            filtered_pixels = pixels
        
        # Calculate average color
        if filtered_pixels:
            r_avg = sum(p[0] for p in filtered_pixels) // len(filtered_pixels)
            g_avg = sum(p[1] for p in filtered_pixels) // len(filtered_pixels)
            b_avg = sum(p[2] for p in filtered_pixels) // len(filtered_pixels)
            
            # Enhance saturation for more vibrant colors
            max_val = max(r_avg, g_avg, b_avg)
            min_val = min(r_avg, g_avg, b_avg)
            
            if max_val > 0:
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
            
    except Exception:
        pass
    
    return None

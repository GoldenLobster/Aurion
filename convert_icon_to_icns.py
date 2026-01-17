#!/usr/bin/env python3
"""
Convert logo.ico to logo.icns for macOS compatibility.
This script uses PIL (Pillow) to convert the ICO file to ICNS format.
"""

import os
from pathlib import Path
from PIL import Image

def convert_ico_to_icns():
    """Convert logo.ico to logo.icns"""
    icons_dir = Path(__file__).parent / "src" / "Icons"
    ico_path = icons_dir / "logo.ico"
    icns_path = icons_dir / "logo.icns"
    
    if not ico_path.exists():
        print(f"Error: {ico_path} not found")
        return False
    
    try:
        # Open the ICO file
        img = Image.open(ico_path)
        
        # Ensure the image is RGBA
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        
        # Resize to common macOS icon size (512x512)
        # macOS uses 512x512 as the standard size for app icons
        icon_size = (512, 512)
        if img.size != icon_size:
            img = img.resize(icon_size, Image.Resampling.LANCZOS)
        
        # Save as ICNS (macOS icon format)
        img.save(icns_path, "ICNS")
        print(f"✓ Successfully converted {ico_path} to {icns_path}")
        return True
    except Exception as e:
        print(f"Error converting icon: {e}")
        return False

if __name__ == "__main__":
    success = convert_ico_to_icns()
    exit(0 if success else 1)

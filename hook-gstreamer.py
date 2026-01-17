"""
PyInstaller hook for GStreamer

This hook ensures that GStreamer libraries and plugins are properly bundled
into PyInstaller executables for Linux builds.
"""

from PyInstaller.utils.hooks import collect_submodules, get_module_file_attribute
import os
import subprocess

# Collect the GStreamer Python module if available
hiddenimports = []

def get_gstreamer_libs():
    """Get list of GStreamer libraries from pkg-config"""
    libs = []
    try:
        result = subprocess.run(
            ['pkg-config', '--list-all'],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'gstreamer' in line.lower():
                # Extract library name from pkg-config output
                lib_name = line.split()[0]
                libs.append(lib_name)
    except Exception:
        pass
    return libs

def get_gstreamer_plugin_dirs():
    """Get GStreamer plugin directories"""
    plugin_dirs = []
    try:
        result = subprocess.run(
            ['pkg-config', '--variable=plugindir', 'gstreamer-1.0'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout.strip():
            plugin_dirs.append(result.stdout.strip())
    except Exception:
        pass
    
    # Add common fallback directories
    common_dirs = [
        '/usr/lib/gstreamer-1.0',
        '/usr/lib/x86_64-linux-gnu/gstreamer-1.0',
        '/usr/lib64/gstreamer-1.0',
        '/usr/local/lib/gstreamer-1.0',
    ]
    
    for dir_path in common_dirs:
        if os.path.exists(dir_path):
            plugin_dirs.append(dir_path)
    
    return plugin_dirs

# Collect binaries (GStreamer libraries)
binaries = []

# Get GStreamer libraries via pkg-config
gst_libs = get_gstreamer_libs()
for lib in gst_libs:
    try:
        result = subprocess.run(
            ['pkg-config', '--variable=libdir', lib],
            capture_output=True,
            text=True,
            timeout=5
        )
        lib_dir = result.stdout.strip()
        if os.path.exists(lib_dir):
            # Add all .so files from the library directory
            for so_file in os.listdir(lib_dir):
                if 'gstreamer' in so_file and so_file.endswith('.so'):
                    binaries.append((
                        os.path.join(lib_dir, so_file),
                        'lib'
                    ))
    except Exception:
        pass

# Collect GStreamer plugins
datas = []
plugin_dirs = get_gstreamer_plugin_dirs()
for plugin_dir in plugin_dirs:
    if os.path.exists(plugin_dir):
        datas.append((
            plugin_dir,
            'gstreamer-1.0'
        ))

# Collect other GStreamer supporting libraries
common_gst_libs = [
    'libgstreamer-1.0',
    'libgstbase-1.0',
    'libgstapp-1.0',
    'libgstaudio-1.0',
    'libgstvideo-1.0',
    'libgstgl-1.0',
]

for lib_name in common_gst_libs:
    try:
        # Try to find lib in standard locations
        for lib_dir in ['/usr/lib', '/usr/lib/x86_64-linux-gnu', '/usr/lib64', '/usr/local/lib']:
            lib_paths = [
                os.path.join(lib_dir, f'{lib_name}.so'),
                os.path.join(lib_dir, f'{lib_name}.so.0'),
            ]
            for lib_path in lib_paths:
                if os.path.exists(lib_path):
                    binaries.append((lib_path, 'lib'))
                    break
    except Exception:
        pass

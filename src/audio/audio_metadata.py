"""
Audio metadata extraction from music files.
Supports ID3 tags, MP4, FLAC, OGG Vorbis, and other formats via Mutagen.
"""

from mutagen import File as MutagenFile
import base64


def extract_metadata(file_path):
    """
    Extract title and artist metadata from audio file.
    
    Args:
        file_path: Path to audio file
        
    Returns:
        Tuple of (title, artist) strings
    """
    try:
        audio = MutagenFile(file_path)
        if audio is None:
            return ("Unknown Track", "Unknown Artist")
        
        title = None
        artist = None
        
        # Try different tag formats
        # MP3 (ID3)
        if hasattr(audio, 'tags') and audio.tags:
            if 'TIT2' in audio.tags:
                title = str(audio.tags['TIT2'])
            if 'TPE1' in audio.tags:
                artist = str(audio.tags['TPE1'])
        
        # MP4/M4A
        if not title and '\xa9nam' in audio:
            title = audio['\xa9nam'][0]
        if not artist and '\xa9ART' in audio:
            artist = audio['\xa9ART'][0]
        
        # FLAC
        if not title and 'title' in audio:
            title = audio['title'][0]
        if not artist and 'artist' in audio:
            artist = audio['artist'][0]
        
        # OGG Vorbis
        if not title and 'TITLE' in audio:
            title = audio['TITLE'][0]
        if not artist and 'ARTIST' in audio:
            artist = audio['ARTIST'][0]
        
        title = title or "Unknown Track"
        artist = artist or "Unknown Artist"
        
        return (str(title), str(artist))
        
    except Exception:
        return ("Unknown Track", "Unknown Artist")


def extract_album_art(file_path):
    """
    Extract album art from audio file metadata.
    
    Args:
        file_path: Path to audio file
        
    Returns:
        Album art as bytes, or None if not found
    """
    try:
        audio = MutagenFile(file_path)
        if audio is None:
            return None
        
        # MP3 (ID3)
        if hasattr(audio, 'tags') and audio.tags:
            for key in audio.tags.keys():
                if 'APIC' in key:
                    return audio.tags[key].data
        
        # MP4/M4A
        if 'covr' in audio:
            return bytes(audio['covr'][0])
        
        # FLAC
        if hasattr(audio, 'pictures') and audio.pictures:
            return audio.pictures[0].data
        
        # OGG Vorbis
        if 'metadata_block_picture' in audio:
            data = base64.b64decode(audio['metadata_block_picture'][0])
            return data[32:]  # Skip FLAC picture block header
            
    except Exception:
        pass
    
    return None

import customtkinter as ctk
from tkinter import filedialog, messagebox
from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
import os
import threading
import re
import subprocess
import ctypes
import threading

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(1.0)

CHILD_LAUNCH = os.environ.get("AURION_CHILD") == "1"
PARENT_PID = os.environ.get("AURION_PARENT_PID")

if CHILD_LAUNCH:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.andrewdore.aurion")
    except Exception:
        pass

# -----------------------------
# Globals initialised after root is created
# -----------------------------
root = None
progress_bar = None
status_var = None
current_item_var = None
search_filter = None
results_frame = None
search_entry = None
url_entry = None
folder_label = None

results_cache = []
result_vars = []
result_widgets = []
seen_tracks = set()
downloaded_keys = set()
download_dir = ""
tooltips = {}

ytmusic = YTMusic()


# -----------------------------
# FFmpeg path resolution
# -----------------------------
def get_ffmpeg_dir():
    """Always returns ./ffmpeg next to app.py"""
    base_path = os.path.dirname(os.path.abspath(__file__))
    ffmpeg_dir = os.path.join(base_path, "ffmpeg")

    if not os.path.exists(os.path.join(ffmpeg_dir, "ffmpeg.exe")):
        show_error(
            "FFmpeg missing",
            "ffmpeg/ffmpeg.exe was not found.\n"
            "Make sure ffmpeg.exe and ffprobe.exe exist in the ffmpeg folder."
        )

    return ffmpeg_dir


def show_error(title, text):
    if root is not None:
        root.after(0, lambda: messagebox.showerror(title, text))
    else:
        messagebox.showerror(title, text)


def show_info(title, text):
    if root is not None:
        root.after(0, lambda: messagebox.showinfo(title, text))
    else:
        messagebox.showinfo(title, text)


# -----------------------------
# Progress + selection helpers
# -----------------------------
def update_progress(percent, text=""):
    """Thread-safe progress updates for the bar and label."""
    if progress_bar is None or status_var is None:
        return

    def _apply():
        progress_bar.set(max(0, min(1, percent / 100)))
        if text:
            status_var.set(text)
    root.after(0, _apply)


def set_current_item(text):
    if current_item_var is None:
        return

    def _apply():
        current_item_var.set(text)
    root.after(0, _apply)


def reset_progress():
    update_progress(0, "Idle")
    set_current_item("")


def clear_results():
    results_cache.clear()
    seen_tracks.clear()
    for widget in result_widgets:
        widget.destroy()
    result_widgets.clear()
    result_vars.clear()


def add_result_row(text):
    if results_frame is None:
        return
    var = ctk.BooleanVar(value=False)
    checkbox = ctk.CTkCheckBox(results_frame, text=text, variable=var)
    checkbox.pack(anchor="w", pady=2, fill="x")
    result_vars.append(var)
    result_widgets.append(checkbox)


def selected_indices():
    return [idx for idx, var in enumerate(result_vars) if var.get()]


def attach_tooltip(widget, text):
    """Lightweight tooltip shown on hover using a CTkToplevel."""
    state = tooltips.setdefault(widget, {"tw": None, "after": None})

    def show_now():
        tw = state["tw"]
        if tw is None:
            tw = ctk.CTkToplevel(widget)
            tw.withdraw()
            tw.overrideredirect(True)
            tw.attributes("-topmost", True)
            label = ctk.CTkLabel(
                tw,
                text=text,
                corner_radius=6,
                fg_color="#333333",
                text_color="white",
                padx=8,
                pady=4,
            )
            label.pack()
            state["tw"] = tw

        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 6
        tw.geometry(f"+{x}+{y}")
        tw.deiconify()
        state["after"] = None

    def schedule_show(_event=None):
        if state["after"]:
            widget.after_cancel(state["after"])
        state["after"] = widget.after(2000, show_now)

    def hide(_event=None):
        if state["after"]:
            widget.after_cancel(state["after"])
            state["after"] = None
        tw = state.get("tw")
        if tw:
            tw.withdraw()

    widget.bind("<Enter>", schedule_show)
    widget.bind("<Leave>", hide)
    widget.bind("<Motion>", schedule_show)




# -----------------------------
# yt-dlp download logic
# -----------------------------
def download_audio(urls_or_meta):
    if not download_dir:
        show_error("Error", "Please choose a download folder first.")
        return

    # Normalize input into list of (url, meta_override_dict|None)
    raw_list = [urls_or_meta] if isinstance(urls_or_meta, str) else list(urls_or_meta)
    normalized = []
    for item in raw_list:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            normalized.append((item[0], item[1]))
        else:
            normalized.append((item, None))

    filtered_targets = []
    batch_seen = set()
    meta_lookup = {}
    for target, meta in normalized:
        vid = url_video_id(target)
        key = vid or target
        # Only dedupe within the current batch; allow re-downloads if files were deleted
        if key in batch_seen:
            continue
        batch_seen.add(key)
        filtered_targets.append((target, key))
        if meta:
            meta_lookup[key] = meta

    if not filtered_targets:
        show_info("Already downloaded", "All selected items were already downloaded.")
        return

    ffmpeg_dir = get_ffmpeg_dir()

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
            update_progress(percent, "Downloading...")
            if artist or title:
                set_current_item(f"{artist} - {title}")
            else:
                set_current_item(os.path.basename(filename))
        elif state == "finished":
            update_progress(100, "Converting to mp3...")

    ydl_opts = {
        "format": "bestaudio/best",
        "ffmpeg_location": ffmpeg_dir,
        "ignoreerrors": True,
        "outtmpl": os.path.join(download_dir, "%(artist)s - %(title)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "noplaylist": False,
        "addmetadata": False,
        "embedthumbnail": False,
        "postprocessor_args": [
            "-ar",
            "44100",
            "-b:a",
            "320k",
            "-minrate",
            "320k",
            "-maxrate",
            "320k",
            "-bufsize",
            "640k",
            "-codec:a",
            "libmp3lame",
        ],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            },
            {"key": "EmbedThumbnail"},
        ],
        "writethumbnail": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            to_download = []
            skipped_existing = 0

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
                show_info("Already downloaded", msg)
                return

            for idx, (target, key) in enumerate(to_download, start=1):
                set_current_item(f"Item {idx}/{len(to_download)}")
                update_progress(0, "Starting download...")
                try:
                    info = ydl.extract_info(target, download=True, process=True)
                    if not info:
                        raise RuntimeError("No info returned for download.")

                    base_name = os.path.splitext(ydl.prepare_filename(info))[0]
                    mp3_path = base_name + ".mp3"
                    thumb_path = find_thumbnail(base_name)

                    update_progress(100, "Cleaning metadata...")
                    meta = preferred_metadata(info)
                    override = meta_lookup.get(key)
                    if override:
                        meta.update({k: v for k, v in override.items() if v})
                    clean_metadata(mp3_path, meta, thumb_path, ffmpeg_dir)
                except Exception:
                    raise
            update_progress(100, "All downloads finished.")
            msg = "All downloads finished."
            if skipped_existing:
                msg += f" Skipped {skipped_existing} existing file(s)."
            show_info("Done", msg)
    except Exception as e:
        show_error("Download failed", str(e))


def threaded_download(urls):
    threading.Thread(target=download_audio, args=(urls,), daemon=True).start()


# -----------------------------
# YouTube Music search
# -----------------------------
def add_track_to_results(track, source_label=""):
    """Insert a track dict into results list with optional source context, skipping duplicates."""
    title = track.get("title", "")
    artist = track.get("artists", [{}])[0].get("name", "")
    video_id = track.get("videoId")
    key = video_id or (artist.strip(), title.strip())
    if key in seen_tracks:
        return
    seen_tracks.add(key)

    display = f"Song | {artist} - {title}"
    if source_label:
        display = f"{display}  [{source_label}]"
    track_copy = dict(track)
    track_copy["resultType"] = "song"
    results_cache.append(track_copy)
    add_result_row(display)


def url_video_id(url: str):
    match = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", url)
    return match.group(1) if match else None


def clean_metadata(mp3_path, meta, thumb_path, ffmpeg_dir):
    """Rewrites tags to keep only the whitelisted fields and re-embeds cover art."""
    if not os.path.exists(mp3_path):
        return

    ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe")
    tmp_path = mp3_path + ".tmp"

    created_temp_cover = False
    prepared_cover = None

    if not thumb_path or not os.path.exists(thumb_path):
        extracted = extract_cover_to_jpeg(mp3_path, ffmpeg_dir)
        if extracted:
            thumb_path = extracted
            created_temp_cover = True

    if thumb_path and os.path.exists(thumb_path):
        prepared_cover = ensure_cover_jpeg(thumb_path, ffmpeg_dir)
        if prepared_cover:
            created_temp_cover = True

    cmd = [
        ffmpeg_exe,
        "-y",
        "-hide_banner",
        "-i",
        mp3_path,
    ]

    if prepared_cover and os.path.exists(prepared_cover):
        cmd += [
            "-i",
            prepared_cover,
            "-map",
            "0:a:0",
            "-map",
            "1:v:0",
            "-disposition:v",
            "attached_pic",
            "-c:v",
            "copy",
            "-metadata:s:v:0",
            "title=Album cover",
            "-metadata:s:v:0",
            "comment=Cover (front)",
        ]
    else:
        cmd += ["-map", "0:a:0"]

    cmd += [
        "-c:a",
        "libmp3lame",
        "-b:a",
        "320k",
        "-minrate",
        "320k",
        "-maxrate",
        "320k",
        "-bufsize",
        "640k",
        "-ar",
        "44100",
        "-map_metadata",
        "-1",
        "-id3v2_version",
        "3",
        "-f",
        "mp3",
    ]

    if meta.get("title"):
        cmd += ["-metadata", f"title={meta['title']}"]
    if meta.get("artist"):
        cmd += ["-metadata", f"artist={meta['artist']}"]
    if meta.get("album"):
        cmd += ["-metadata", f"album={meta['album']}"]
    if meta.get("year"):
        cmd += ["-metadata", f"date={meta['year']}"]

    cmd.append(tmp_path)

    try:
        proc = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        os.replace(tmp_path, mp3_path)
    except subprocess.CalledProcessError as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        stdout_txt = e.stdout or ""
        stderr_txt = e.stderr or ""
        msg = "ffmpeg failed"\
            + (f"\nstdout:\n{stdout_txt}" if stdout_txt else "")\
            + (f"\nstderr:\n{stderr_txt}" if stderr_txt else "")
        raise RuntimeError(msg) from e
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    finally:
        # Clean up any temp cover we created.
        if created_temp_cover:
            for path in [prepared_cover, thumb_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass
            try:
                os.remove(thumb_path)
            except Exception:
                pass


def preferred_metadata(info_dict):
    """Extracts the allowed metadata fields from yt-dlp's info dict."""
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


def meta_from_track_dict(track):
    """Build a metadata dict from a YTMusic track/album/playlist item."""
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
        # Some entries store date like "2020-01-01"
        date_str = track.get("releaseDate") or track.get("published") or ""
        if isinstance(date_str, str) and len(date_str) >= 4:
            year = date_str[:4]

    return {
        "title": str(title).strip(),
        "artist": str(artist).strip(),
        "album": str(album).strip(),
        "year": str(year).strip(),
    }


def find_thumbnail(base_path):
    """Tries to locate the downloaded thumbnail matching the media base name."""
    candidates = [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
    for ext in candidates:
        cand = base_path + ext
        if os.path.exists(cand):
            return cand

    directory = os.path.dirname(base_path)
    prefix = os.path.basename(base_path)
    if os.path.isdir(directory):
        for name in os.listdir(directory):
            if not name.lower().endswith(tuple(candidates)):
                continue
            if name.startswith(prefix):
                return os.path.join(directory, name)
    return None


def extract_cover_to_jpeg(mp3_path, ffmpeg_dir):
    """If the mp3 already has an attached picture, extract it to a mjpeg file."""
    ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe")
    base, _ = os.path.splitext(mp3_path)
    out_path = base + ".apic.jpg"

    cmd = [
        ffmpeg_exe,
        "-y",
        "-hide_banner",
        "-i",
        mp3_path,
        "-map",
        "0:v:0",
        "-c:v",
        "mjpeg",
        out_path,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out_path if os.path.exists(out_path) else None
    except Exception:
        if os.path.exists(out_path):
            os.remove(out_path)
        return None


def ensure_cover_jpeg(src_path, ffmpeg_dir):
    """Converts any image to a JPEG suitable for APIC embedding."""
    if not src_path or not os.path.exists(src_path):
        return None

    ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe")
    base, _ = os.path.splitext(src_path)
    out_path = base + "_cover.jpg"

    cmd = [
        ffmpeg_exe,
        "-y",
        "-hide_banner",
        "-i",
        src_path,
        "-map",
        "0:v:0",
        "-vf",
        # Normalize cover: scale up to fill then center-crop to 600x600 for a full-frame look.
        "scale=600:600:force_original_aspect_ratio=increase,crop=600:600",
        "-frames:v",
        "1",
        "-pix_fmt",
        "yuvj420p",
        "-q:v",
        "2",
        out_path,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out_path if os.path.exists(out_path) else None
    except Exception:
        if os.path.exists(out_path):
            os.remove(out_path)
        return None


def extract_playlist_id(url: str):
    match = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


def populate_playlist_tracks(playlist_id, source_label="Playlist"):
    """Fetch playlist tracks in a worker and populate the list for selection."""

    def worker():
        try:
            playlist = ytmusic.get_playlist(playlist_id, limit=1000)
            tracks = playlist.get("tracks", [])
            title = playlist.get("title", source_label)
        except Exception as e:
            show_error("Playlist error", str(e))
            return

        def apply():
            clear_results()
            for t in tracks:
                add_track_to_results(t, source_label=title)
            status_var.set(f"Loaded {len(tracks)} tracks from {title}")

        root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()


def search_music():
    query = search_entry.get().strip()
    clear_results()

    if not query:
        return

    try:
        results = ytmusic.search(query, filter=search_filter.get(), limit=20)
    except Exception as e:
        messagebox.showerror("Search error", str(e))
        return

    for r in results:
        result_type = r.get("resultType") or search_filter.get()
        if result_type == "song":
            title = r.get("title", "")
            artist = r.get("artists", [{}])[0].get("name", "")
            display = f"Song | {artist} - {title}"
        elif result_type == "album":
            title = r.get("title", "")
            artist = r.get("artists", [{}])[0].get("name", "")
            display = f"Album | {artist} - {title}"
        elif result_type == "playlist":
            title = r.get("title", "")
            count = r.get("count", "")
            display = f"Playlist | {title} ({count})"
        else:
            display = r.get("title", "Unknown")

        results_cache.append(r)
        add_result_row(display)


def load_selection_contents():
    selection = selected_indices()
    if not selection:
        return

    selected_items = [results_cache[i] for i in selection]
    clear_results()

    for data in selected_items:
        result_type = data.get("resultType") or search_filter.get()

        if result_type == "album":
            browse_id = data.get("browseId")
            if not browse_id:
                continue
            try:
                album = ytmusic.get_album(browse_id)
                title = album.get("title", "Album")
                for t in album.get("tracks", []):
                    add_track_to_results(t, source_label=title)
            except Exception as e:
                show_error("Album error", str(e))
        elif result_type == "playlist":
            playlist_id = data.get("playlistId")
            if not playlist_id:
                continue
            try:
                playlist = ytmusic.get_playlist(playlist_id)
                title = playlist.get("title", "Playlist")
                for t in playlist.get("tracks", []):
                    add_track_to_results(t, source_label=title)
            except Exception as e:
                show_error("Playlist error", str(e))
        else:
            add_track_to_results(data, source_label="")


def download_selected():
    selection = selected_indices()
    if not selection:
        return

    queued = []  # list of (url, meta_override)

    for idx in selection:
        data = results_cache[idx]
        result_type = data.get("resultType") or search_filter.get()

        if result_type == "song":
            video_id = data.get("videoId")
            if video_id:
                queued.append((f"https://music.youtube.com/watch?v={video_id}", meta_from_track_dict(data)))
        elif result_type == "playlist":
            playlist_id = data.get("playlistId")
            if playlist_id:
                queued.append((f"https://music.youtube.com/playlist?list={playlist_id}", None))
        elif result_type == "album":
            browse_id = data.get("browseId")
            if not browse_id:
                continue
            try:
                album = ytmusic.get_album(browse_id)
                tracks = album.get("tracks", [])
                for t in tracks:
                    vid = t.get("videoId")
                    if vid:
                        queued.append((f"https://music.youtube.com/watch?v={vid}", meta_from_track_dict(t)))
            except Exception as e:
                show_error("Album error", str(e))

    if queued:
        update_progress(0, "Starting download...")
        set_current_item("")
        threaded_download(queued)


# -----------------------------
# Folder picker
# -----------------------------
def choose_folder():
    global download_dir
    folder = filedialog.askdirectory()
    if folder:
        download_dir = folder
        folder_label.configure(text=folder)


# -----------------------------
# Direct URL download
# -----------------------------
def download_url():
    url = url_entry.get().strip()
    if not url:
        return

    playlist_id = extract_playlist_id(url)
    if playlist_id:
        status_var.set("Loading playlist tracks...")
        populate_playlist_tracks(playlist_id)
    else:
        update_progress(0, "Starting download...")
        set_current_item(url)
        threaded_download(url)


# -----------------------------
# GUI
# -----------------------------
def build_gui():
    global root, status_var, current_item_var, search_filter
    global results_frame, search_entry, url_entry, folder_label, progress_bar

    root = ctk.CTk()
    root.title("YouTube Music Downloader")
    root.geometry("720x600")
    root.minsize(800, 700)
    root.configure(padx=8, pady=8)

    if CHILD_LAUNCH:
        try:
            # Keep same AppUserModelID but allow normal window so it shows as second window in the group
            pass
        except Exception:
            pass

    status_var = ctk.StringVar(root, value="Idle")
    current_item_var = ctk.StringVar(root, value="")
    search_filter = ctk.StringVar(root, value="songs")

    ctk.CTkLabel(root, text="Download Folder").pack(pady=(10, 0))
    ctk.CTkButton(root, text="Choose Folder", command=choose_folder).pack()
    folder_label = ctk.CTkLabel(root, text="Not selected")
    folder_label.pack(pady=(0, 10))

    ctk.CTkLabel(root, text="Search YouTube Music").pack()
    filter_frame = ctk.CTkFrame(root)
    filter_frame.pack(pady=(2, 6), fill="x", padx=20)
    ctk.CTkLabel(filter_frame, text="Filter:").pack(side="left", padx=(0, 6))
    ctk.CTkComboBox(
        filter_frame,
        variable=search_filter,
        values=["songs", "albums", "playlists"],
        width=140,
        state="readonly",
    ).pack(side="left")
    search_entry = ctk.CTkEntry(root, placeholder_text="e.g. artist, song, album")
    search_entry.pack(fill="x", padx=20)
    ctk.CTkButton(root, text="Search", command=search_music).pack(pady=3)

    results_frame = ctk.CTkScrollableFrame(root)
    results_frame.pack(fill="both", expand=True, pady=3, padx=20)

    download_btn = ctk.CTkButton(root, text="➕ Download Selected", command=download_selected)
    download_btn.pack(pady=3)
    attach_tooltip(download_btn, "Downloads the selected tracks")
    load_btn = ctk.CTkButton(root, text="Load Tracks from Selection", command=load_selection_contents)
    load_btn.pack(pady=(0, 10))
    attach_tooltip(
        load_btn,
        "Load tracks from selected album or playlist - useful if you only want to download specific tracks from an album or playlist",
    )

    ctk.CTkLabel(root, text="Or paste a direct YouTube / YouTube Music URL").pack(pady=(5, 0))
    url_entry = ctk.CTkEntry(root, placeholder_text="https://...")
    url_entry.pack(fill="x", padx=20)
    url_btn = ctk.CTkButton(root, text="Download URL / Fetch playlist", command=download_url)
    url_btn.pack(pady=3)
    attach_tooltip(
        url_btn,
        "Directly download a song or fetch albums and playlist for download",
    )

    progress_frame = ctk.CTkFrame(root)
    progress_frame.pack(fill="x", pady=5, padx=20)
    ctk.CTkLabel(progress_frame, text="Progress").pack(anchor="w")
    progress_bar = ctk.CTkProgressBar(progress_frame)
    progress_bar.pack(fill="x", pady=(4, 2))
    progress_bar.set(0)
    ctk.CTkLabel(progress_frame, textvariable=status_var).pack(anchor="w")
    ctk.CTkLabel(progress_frame, textvariable=current_item_var, justify="left").pack(anchor="w", fill="x")


if __name__ == "__main__":
    if CHILD_LAUNCH and PARENT_PID:
        # Watch parent; exit if parent dies so windows close together
        def _watch_parent(pid):
            try:
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
                if handle:
                    kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
                os._exit(0)
            except Exception:
                pass

        t = threading.Thread(target=_watch_parent, args=(PARENT_PID,), daemon=True)
        t.start()

    build_gui()
    root.mainloop()


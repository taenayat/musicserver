"""
artwork.py — cover-art detection and embedding (mutagen).

Shared by the download cover-art backfill and the interactive album-art sync
tool. Pure file/tag operations: detect whether a file already has art, whether
its folder has a cover image, and embed image bytes into common audio formats.
Network fetching and Deezer resolution live in the callers (main.py), which hold
the http/deezer clients.
"""

import logging
import os

log = logging.getLogger("artwork")

_FOLDER_COVER_NAMES = ("cover", "folder", "front", "albumart", "album")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
_EMBEDDABLE_EXTS = (".mp3", ".flac", ".m4a", ".mp4", ".aac")


def has_embedded_art(abs_path: str) -> bool:
    """True if the audio file already carries embedded cover art."""
    from mutagen import File as MutagenFile

    try:
        mf = MutagenFile(abs_path)
    except Exception as exc:
        log.debug("art probe failed for %s: %s", abs_path, exc)
        return False
    if mf is None:
        return False

    # FLAC / OGG expose .pictures
    if getattr(mf, "pictures", None):
        return True

    tags = getattr(mf, "tags", None)
    if not tags:
        return False
    try:
        keys = list(tags.keys())
    except Exception:
        return False
    # MP3 ID3 APIC frames
    if any(str(k).startswith("APIC") for k in keys):
        return True
    # MP4 / M4A cover atom
    if "covr" in keys:
        return True
    return False


def folder_has_cover(abs_path: str) -> bool:
    """True if the track's directory has a cover image Navidrome would read."""
    folder = os.path.dirname(abs_path)
    try:
        entries = os.listdir(folder)
    except OSError:
        return False
    for name in entries:
        base, ext = os.path.splitext(name.lower())
        if ext in _IMAGE_EXTS and base in _FOLDER_COVER_NAMES:
            return True
    return False


def is_missing_art(abs_path: str) -> bool:
    """A track is missing art if it has neither embedded nor folder cover."""
    return not has_embedded_art(abs_path) and not folder_has_cover(abs_path)


def can_embed(abs_path: str) -> bool:
    return os.path.splitext(abs_path)[1].lower() in _EMBEDDABLE_EXTS


def embed_cover(abs_path: str, image_bytes: bytes, mime: str = "image/jpeg") -> bool:
    """Embed image bytes as cover art. Returns True on success.

    Supports mp3 (ID3 APIC), flac (Picture), and mp4/m4a (covr). Other formats
    (ogg/opus) are skipped for now and return False.
    """
    ext = os.path.splitext(abs_path)[1].lower()
    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, APIC, error as id3error
            try:
                audio = ID3(abs_path)
            except id3error:
                audio = ID3()
            audio.delall("APIC")
            audio.add(APIC(encoding=3, mime=mime, type=3, desc="Cover",
                           data=image_bytes))
            audio.save(abs_path)
            return True
        if ext == ".flac":
            from mutagen.flac import FLAC, Picture
            audio = FLAC(abs_path)
            pic = Picture()
            pic.type = 3
            pic.mime = mime
            pic.data = image_bytes
            audio.clear_pictures()
            audio.add_picture(pic)
            audio.save()
            return True
        if ext in (".m4a", ".mp4", ".aac"):
            from mutagen.mp4 import MP4, MP4Cover
            audio = MP4(abs_path)
            fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            audio["covr"] = [MP4Cover(image_bytes, imageformat=fmt)]
            audio.save()
            return True
    except Exception as exc:
        log.warning("embed cover failed for %s: %s", abs_path, exc)
        return False
    log.debug("embed cover unsupported format: %s", abs_path)
    return False

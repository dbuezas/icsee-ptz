"""Video encoding limits (resolutions, FPS and the encode power budget).

The resolution names and sizes are the XM SDK "CaptureSize" list; the bit index in
EncodeCapability masks is the position in this list. Sizes are from the official
FunSDK demo (EncodeDataSourse.m). The budget rule is what the official apps do:
pixels(main) * fps(main) + pixels(sub) * fps(sub) <= MaxEncodePowerPerChannel.
"""

from __future__ import annotations

from typing import Any

RESOLUTIONS: tuple[tuple[str, tuple[int, int], tuple[int, int]], ...] = (
    # name, PAL size, NTSC size
    ("D1", (704, 576), (704, 480)),
    ("HD1", (704, 288), (704, 240)),
    ("BCIF", (352, 576), (352, 480)),
    ("CIF", (352, 288), (352, 240)),
    ("QCIF", (176, 144), (176, 120)),
    ("VGA", (640, 480), (640, 480)),
    ("QVGA", (320, 240), (320, 240)),
    ("SVCD", (480, 480), (480, 480)),
    ("QQVGA", (160, 128), (160, 128)),
    ("ND1", (240, 192), (240, 192)),
    ("650TVL", (928, 576), (928, 576)),
    ("720P", (1280, 720), (1280, 720)),
    ("1_3M", (1280, 960), (1280, 960)),
    ("UXGA", (1600, 1200), (1600, 1200)),
    ("1080P", (1920, 1080), (1920, 1080)),
    ("WUXGA", (1920, 1200), (1920, 1200)),
    ("2_5M", (1872, 1408), (1872, 1408)),
    ("3M", (2048, 1536), (2048, 1536)),
    ("5M", (3744, 1408), (3744, 1408)),
    ("1080N", (960, 1080), (960, 1080)),
    ("4M", (2592, 1520), (2592, 1520)),
    ("6M", (3072, 2048), (3072, 2048)),
    ("8M", (3264, 2448), (3264, 2448)),
    ("12M", (4000, 3000), (4000, 3000)),
    ("4K", (4096, 2160), (4096, 2160)),
    ("720N", (640, 720), (640, 720)),
    ("WSVGA", (1024, 576), (1024, 576)),
    ("NHD", (640, 360), (640, 360)),
    ("3M_N", (1024, 1536), (1024, 1536)),
    ("4M_N", (1280, 1440), (1280, 1440)),
    ("5M_N", (1872, 1408), (1872, 1408)),
    ("4K_N", (2048, 2106), (2048, 2106)),
)
RESOLUTION_INDEX = {name: i for i, (name, _, _) in enumerate(RESOLUTIONS)}

COMPRESSIONS = {7: "H.264", 8: "H.265"}  # bit index in CompressionMask

MAIN, SUB = "MainFormat", "ExtraFormat"


def _int(value: Any) -> int:
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") else int(value)
    return int(value or 0)


def _at(values: Any, channel: int) -> Any:
    if isinstance(values, list) and channel < len(values):
        return values[channel]
    return None


def is_ntsc(location: dict[str, Any] | None) -> bool:
    return bool(location) and location.get("VideoFormat") == "NTSC"


def max_fps(location: dict[str, Any] | None) -> int:
    return 30 if is_ntsc(location) else 25


def pixels(resolution: str | None, ntsc: bool) -> int:
    if resolution not in RESOLUTION_INDEX:
        return 0
    _, pal, ntsc_size = RESOLUTIONS[RESOLUTION_INDEX[resolution]]
    width, height = ntsc_size if ntsc else pal
    return width * height


def _mask_names(mask: Any) -> list[str]:
    bits = _int(mask)
    return [name for i, (name, _, _) in enumerate(RESOLUTIONS) if bits >> i & 1]


def resolution_options(
    capability: dict[str, Any], encode: dict[str, Any], stream: str, channel: int
) -> list[str]:
    """Resolutions the camera offers for a stream (before the budget check)."""
    if stream == MAIN:
        mask = _at(capability.get("ImageSizePerChannel"), channel)
    else:
        mask = 0
        main_res = encode.get(MAIN, {}).get("Video", {}).get("Resolution")
        per_main = _at(capability.get("ExImageSizePerChannelEx"), channel)
        if main_res in RESOLUTION_INDEX and isinstance(per_main, list):
            mask = _int(_at(per_main, RESOLUTION_INDEX[main_res]))
        if not mask:
            mask = _at(capability.get("ExImageSizePerChannel"), channel)
    options = _mask_names(mask)
    current = encode.get(stream, {}).get("Video", {}).get("Resolution")
    if current and current not in options:
        options.append(current)
    return options


def compression_options(
    capability: dict[str, Any], encode: dict[str, Any], stream: str
) -> list[str]:
    infos = capability.get("EncodeInfo") or []
    wanted = "MainStream" if stream == MAIN else "ExtraStream2"
    mask = next(
        (i.get("CompressionMask") for i in infos if i.get("StreamType") == wanted), 0
    )
    options = [name for bit, name in COMPRESSIONS.items() if _int(mask) >> bit & 1]
    current = encode.get(stream, {}).get("Video", {}).get("Compression")
    if current and current not in options:
        options.append(current)
    return options


def budget(capability: dict[str, Any], channel: int) -> int | None:
    value = _at(capability.get("MaxEncodePowerPerChannel"), channel)
    if value is None:
        value = capability.get("MaxEncodePower")
    return _int(value) or None


def load(encode: dict[str, Any], ntsc: bool) -> int:
    """Encode power used by an Simplify.Encode channel entry."""
    total = 0
    for stream in (MAIN, SUB):
        fmt = encode.get(stream) or {}
        if stream == SUB and not fmt.get("VideoEnable", True):
            continue
        video = fmt.get("Video") or {}
        total += pixels(video.get("Resolution"), ntsc) * _int(video.get("FPS"))
    return total


def fits(
    capability: dict[str, Any], encode: dict[str, Any], channel: int, ntsc: bool
) -> bool:
    limit = budget(capability, channel)
    return limit is None or load(encode, ntsc) <= limit


def stream_max_fps(
    capability: dict[str, Any],
    encode: dict[str, Any],
    stream: str,
    channel: int,
    ntsc: bool,
) -> int:
    """Highest FPS for a stream: the encode budget left by the other stream,
    but never more than the video standard allows (25 PAL / 30 NTSC)."""
    standard = 30 if ntsc else 25
    limit = budget(capability, channel)
    video = (encode.get(stream) or {}).get("Video") or {}
    own = pixels(video.get("Resolution"), ntsc)
    if limit is None or not own:
        return standard
    other = load({**encode, stream: {"VideoEnable": False}}, ntsc)
    return max(1, min(standard, (limit - other) // own))

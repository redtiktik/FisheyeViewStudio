from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Sequence
import json
import os
import re
import shutil
import subprocess
import sys

from .models import MediaInfo, RenderSettings, TimestampSettings, ViewDefinition


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".m4v",
    ".ts",
    ".mts",
    ".m2ts",
}


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str | Path) -> Path:
    relative_path = Path(relative)
    bundle_root = Path(getattr(sys, "_MEIPASS", app_base_dir()))
    candidate = bundle_root / relative_path
    if candidate.exists():
        return candidate
    return app_base_dir() / relative_path


def locate_ffmpeg(preferred: str | None = None) -> tuple[Path | None, Path | None]:
    candidates: list[Path] = []

    if preferred:
        candidates.append(Path(preferred))

    base = app_base_dir()
    candidates.extend(
        [
            resource_path("tools/ffmpeg.exe"),
            base / "tools" / "ffmpeg.exe",
            base / "ffmpeg.exe",
            Path(r"C:\FFmpeg\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe"),
            Path(r"C:\FFmpeg\bin\ffmpeg.exe"),
        ]
    )

    path_match = shutil.which("ffmpeg.exe") or shutil.which("ffmpeg")
    if path_match:
        candidates.append(Path(path_match))

    ffmpeg_path: Path | None = None
    for candidate in candidates:
        try:
            candidate = candidate.expanduser().resolve()
        except OSError:
            continue
        if candidate.is_file():
            ffmpeg_path = candidate
            break

    if ffmpeg_path is None:
        return None, None

    ffprobe_candidates = [
        ffmpeg_path.with_name("ffprobe.exe"),
        ffmpeg_path.with_name("ffprobe"),
    ]
    probe_match = shutil.which("ffprobe.exe") or shutil.which("ffprobe")
    if probe_match:
        ffprobe_candidates.append(Path(probe_match))

    ffprobe_path = next((p.resolve() for p in ffprobe_candidates if p.is_file()), None)
    return ffmpeg_path, ffprobe_path


def probe_media(
    ffmpeg_path: Path,
    input_path: Path,
    ffprobe_path: Path | None = None,
) -> MediaInfo:
    """Read media details with ffprobe when available, otherwise use ffmpeg.

    The compact portable package intentionally ships only ffmpeg.exe.  FFmpeg's
    normal input summary contains the dimensions, duration, frame rate, codec,
    and audio-stream presence needed by this application.  When ffprobe.exe is
    available beside a user-selected FFmpeg installation, its JSON output is
    still preferred because it is more structured.
    """
    if ffprobe_path is not None and ffprobe_path.is_file():
        try:
            return _probe_media_with_ffprobe(ffprobe_path, input_path)
        except RuntimeError:
            # A damaged or incompatible ffprobe should not prevent the app from
            # using a working ffmpeg.exe.
            pass

    return _probe_media_with_ffmpeg(ffmpeg_path, input_path)


def _probe_media_with_ffprobe(ffprobe_path: Path, input_path: Path) -> MediaInfo:
    command = [
        str(ffprobe_path),
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,duration:format=duration",
        "-of",
        "json",
        str(input_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=_creation_flags(),
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ffprobe could not read the selected video.")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ffprobe returned invalid media information.") from exc

    streams = payload.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video_stream:
        raise RuntimeError("No video stream was found in the selected file.")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError("The video dimensions could not be determined.")

    duration_text = video_stream.get("duration") or (payload.get("format") or {}).get("duration") or 0
    try:
        duration = float(duration_text)
    except (TypeError, ValueError):
        duration = 0.0

    frame_rate = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0/1"
    fps = _parse_fraction(frame_rate)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    return MediaInfo(
        path=input_path,
        width=width,
        height=height,
        duration_seconds=max(0.0, duration),
        fps=max(0.0, fps),
        has_audio=has_audio,
        codec_name=str(video_stream.get("codec_name") or ""),
    )


def _probe_media_with_ffmpeg(ffmpeg_path: Path, input_path: Path) -> MediaInfo:
    # FFmpeg returns a non-zero exit status when no output file is specified;
    # the media summary in stderr is still the intended result here.
    command = [str(ffmpeg_path), "-hide_banner", "-i", str(input_path)]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=_creation_flags(),
    )
    summary = f"{completed.stdout}\n{completed.stderr}"

    video_lines = [
        line.strip()
        for line in summary.splitlines()
        if "Stream #" in line and "Video:" in line
    ]
    if not video_lines:
        detail = completed.stderr.strip()
        if detail:
            detail = detail.splitlines()[-1]
        raise RuntimeError(detail or "FFmpeg could not find a video stream in the selected file.")

    video_line = video_lines[0]
    dimensions = _parse_dimensions_from_ffmpeg_line(video_line)
    if dimensions is None:
        raise RuntimeError("FFmpeg found a video stream, but its dimensions could not be determined.")
    width, height = dimensions

    duration = _parse_duration_from_ffmpeg_summary(summary)
    fps = _parse_fps_from_ffmpeg_line(video_line)
    has_audio = any("Stream #" in line and "Audio:" in line for line in summary.splitlines())

    codec_match = re.search(r"Video:\s*([^,\s(]+)", video_line, flags=re.IGNORECASE)
    codec_name = codec_match.group(1) if codec_match else ""

    return MediaInfo(
        path=input_path,
        width=width,
        height=height,
        duration_seconds=max(0.0, duration),
        fps=max(0.0, fps),
        has_audio=has_audio,
        codec_name=codec_name,
    )


def _parse_dimensions_from_ffmpeg_line(line: str) -> tuple[int, int] | None:
    # Stream descriptions can contain hexadecimal codec tags, SAR/DAR values,
    # and other numbers.  Restrict candidates to plausible video dimensions.
    candidates = re.findall(r"(?<![0-9A-Fa-f])(\d{2,5})x(\d{2,5})(?![0-9A-Fa-f])", line)
    for width_text, height_text in candidates:
        width = int(width_text)
        height = int(height_text)
        if 16 <= width <= 32768 and 16 <= height <= 32768:
            return width, height
    return None


def _parse_duration_from_ffmpeg_summary(summary: str) -> float:
    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        summary,
        flags=re.IGNORECASE,
    )
    if not match:
        return 0.0
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def _parse_fps_from_ffmpeg_line(line: str) -> float:
    for pattern in (r"(\d+(?:\.\d+)?)\s*fps\b", r"(\d+(?:\.\d+)?)\s*tbr\b"):
        match = re.search(pattern, line, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return 0.0
    return 0.0

def detect_nvenc(ffmpeg_path: Path) -> bool:
    command = [str(ffmpeg_path), "-hide_banner", "-encoders"]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=_creation_flags(),
    )
    text = f"{completed.stdout}\n{completed.stderr}".lower()
    return completed.returncode == 0 and "h264_nvenc" in text


def build_extract_frame_args(input_path: Path, output_path: Path, timestamp_seconds: float) -> list[str]:
    return [
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        format_seconds(timestamp_seconds),
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        "-an",
        str(output_path),
    ]


def build_preview_args(
    input_path: Path,
    output_path: Path,
    view: ViewDefinition,
    timestamp: TimestampSettings,
    render: RenderSettings,
    timestamp_seconds: float,
    preview_width: int = 640,
    preview_height: int = 360,
) -> list[str]:
    view.clamp()
    filter_complex, output_label = build_single_view_filter(
        view=view,
        timestamp=timestamp,
        render=render,
        output_width=preview_width,
        output_height=preview_height,
        preview=True,
    )

    return [
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        format_seconds(timestamp_seconds),
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        "-filter_complex",
        filter_complex,
        "-map",
        output_label,
        "-an",
        str(output_path),
    ]


def build_render_command(
    input_path: Path,
    output_dir: Path,
    views: Sequence[ViewDefinition],
    timestamp: TimestampSettings,
    render: RenderSettings,
    use_nvenc: bool,
) -> tuple[list[str], list[Path]]:
    active_views = [view for view in views if view.enabled]
    if not active_views:
        raise ValueError("At least one view must be enabled before rendering.")

    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = sanitize_filename(input_path.stem)
    filter_complex, labels = build_multi_view_filter(active_views, timestamp, render)

    args: list[str] = [
        "-hide_banner",
        "-y",
        "-progress",
        "pipe:1",
        "-nostats",
    ]

    if render.test_seconds > 0:
        args.extend(["-t", str(render.test_seconds)])

    args.extend(["-i", str(input_path), "-filter_complex", filter_complex])

    outputs: list[Path] = []
    for index, (view, label) in enumerate(zip(active_views, labels), start=1):
        safe_view_name = sanitize_filename(view.name) or f"View_{index:02d}"
        output_path = output_dir / f"{base_name}_View_{index:02d}_{safe_view_name}.mp4"
        outputs.append(output_path)

        args.extend(["-map", label, "-map", "0:a:0?"])
        args.extend(encoder_args(render, use_nvenc))
        args.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                f"{render.audio_bitrate_kbps}k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

    return args, outputs


def build_single_view_filter(
    view: ViewDefinition,
    timestamp: TimestampSettings,
    render: RenderSettings,
    output_width: int,
    output_height: int,
    preview: bool,
) -> tuple[str, str]:
    square_crop = r"crop=min(iw\,ih):min(iw\,ih):(iw-min(iw\,ih))/2:(ih-min(iw\,ih))/2"
    v360 = _v360_filter(view, render, output_width, output_height)

    if not timestamp.enabled:
        graph = f"[0:v]{square_crop},{v360},setsar=1[outv]"
        return graph, "[outv]"

    stamp_width = timestamp.overlay_width
    overlay_x = timestamp.overlay_x
    overlay_y = timestamp.overlay_y
    if preview:
        scale = output_width / max(1, render.output_width)
        stamp_width = max(120, int(round(timestamp.overlay_width * scale)))
        overlay_x = max(0, int(round(timestamp.overlay_x * scale)))
        overlay_y = max(0, int(round(timestamp.overlay_y * scale)))

    graph = (
        "[0:v]split=2[stamp_src][fish_src];"
        f"[stamp_src]crop={timestamp.crop_width}:{timestamp.crop_height}:"
        f"{timestamp.crop_x}:{timestamp.crop_y},"
        f"scale={stamp_width}:-2:flags=bilinear[stamp];"
        f"[fish_src]{square_crop},{v360},setsar=1[p];"
        f"[p][stamp]overlay={overlay_x}:{overlay_y}:format=auto,setsar=1[outv]"
    )
    return graph, "[outv]"


def build_multi_view_filter(
    views: Sequence[ViewDefinition],
    timestamp: TimestampSettings,
    render: RenderSettings,
) -> tuple[str, list[str]]:
    count = len(views)
    square_crop = r"crop=min(iw\,ih):min(iw\,ih):(iw-min(iw\,ih))/2:(ih-min(iw\,ih))/2"
    pieces: list[str] = []
    labels: list[str] = []

    if timestamp.enabled:
        pieces.append("[0:v]split=2[stamp_src][fish_src]")
        pieces.append(
            f"[stamp_src]crop={timestamp.crop_width}:{timestamp.crop_height}:"
            f"{timestamp.crop_x}:{timestamp.crop_y},"
            f"scale={timestamp.overlay_width}:-2:flags=bilinear[stamp]"
        )
        stamp_outputs = "".join(f"[t{i}]" for i in range(1, count + 1))
        pieces.append(f"[stamp]split={count}{stamp_outputs}")
        fish_source = "[fish_src]"
    else:
        fish_source = "[0:v]"

    split_outputs = "".join(f"[s{i}]" for i in range(1, count + 1))
    pieces.append(f"{fish_source}{square_crop},split={count}{split_outputs}")

    for index, view in enumerate(views, start=1):
        view.clamp()
        pieces.append(
            f"[s{index}]"
            f"{_v360_filter(view, render, render.output_width, render.output_height)},"
            f"setsar=1[p{index}]"
        )
        if timestamp.enabled:
            pieces.append(
                f"[p{index}][t{index}]"
                f"overlay={timestamp.overlay_x}:{timestamp.overlay_y}:format=auto,"
                f"setsar=1[v{index}]"
            )
            labels.append(f"[v{index}]")
        else:
            labels.append(f"[p{index}]")

    return ";".join(pieces), labels


def encoder_args(render: RenderSettings, use_nvenc: bool) -> list[str]:
    if use_nvenc:
        # Temporal AQ is a strong fit for security footage with static detailed backgrounds.
        # NVIDIA recommends using either spatial AQ or temporal AQ, not both.
        return [
            "-c:v",
            "h264_nvenc",
            "-gpu",
            "0",
            "-preset",
            "p5",
            "-tune",
            "hq",
            "-multipass",
            "qres",
            "-rc",
            "vbr",
            "-b:v",
            f"{render.bitrate_kbps}k",
            "-maxrate:v",
            f"{render.maxrate_kbps}k",
            "-bufsize:v",
            f"{render.buffer_kbps}k",
            "-rc-lookahead",
            "16",
            "-temporal-aq",
            "1",
            "-bf",
            "3",
            "-b_ref_mode",
            "middle",
            "-g",
            "60",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-fps_mode",
            "passthrough",
        ]

    return [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-b:v",
        f"{render.bitrate_kbps}k",
        "-maxrate:v",
        f"{render.maxrate_kbps}k",
        "-bufsize:v",
        f"{render.buffer_kbps}k",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-fps_mode",
        "passthrough",
    ]


def estimate_output_bytes(
    duration_seconds: float,
    view_count: int,
    render: RenderSettings,
    has_audio: bool,
) -> tuple[int, int]:
    duration = render.test_seconds if render.test_seconds > 0 else max(0.0, duration_seconds)
    audio = render.audio_bitrate_kbps if has_audio else 0
    bits_per_second = (render.bitrate_kbps + audio) * 1000
    per_view = int(duration * bits_per_second / 8)
    return per_view, per_view * max(0, view_count)


def human_size(byte_count: int) -> str:
    size = float(max(0, byte_count))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit in {"B", "KB"}:
                return f"{size:.0f} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def sanitize_filename(value: str) -> str:
    value = re.sub(r"[<>:\\|?*\x00-\x1F]", "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:180] or "output"


def format_seconds(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remainder = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remainder:06.3f}"


def _v360_filter(
    view: ViewDefinition,
    render: RenderSettings,
    output_width: int,
    output_height: int,
) -> str:
    interpolation = render.interpolation if render.interpolation in {"linear", "cubic", "lanczos"} else "cubic"
    return (
        "v360="
        "input=fisheye:output=flat:"
        "ih_fov=180:iv_fov=180:"
        f"pitch={view.pitch:.3f}:roll={view.roll:.3f}:"
        "rorder=rpy:"
        f"h_fov={view.h_fov:.3f}:v_fov={view.v_fov:.3f}:"
        f"w={int(output_width)}:h={int(output_height)}:"
        f"interp={interpolation}"
    )


def _parse_fraction(value: str) -> float:
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            denominator_value = float(denominator)
            if denominator_value == 0:
                return 0.0
            return float(numerator) / denominator_value
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0

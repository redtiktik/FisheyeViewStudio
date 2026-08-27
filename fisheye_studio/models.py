from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import math
import uuid


VIEW_COLORS = [
    "#38BDF8",  # sky
    "#22C55E",  # green
    "#F59E0B",  # amber
    "#F43F5E",  # rose
    "#A78BFA",  # violet
    "#14B8A6",  # teal
    "#FB7185",  # pink
    "#84CC16",  # lime
]


@dataclass
class ViewDefinition:
    name: str
    roll: float
    pitch: float
    h_fov: float = 100.0
    v_fov: float = 70.0
    enabled: bool = True
    color: str = "#38BDF8"
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)

    def clamp(self) -> None:
        self.roll = normalize_roll(self.roll)
        self.pitch = max(0.0, min(88.0, float(self.pitch)))
        self.h_fov = max(40.0, min(140.0, float(self.h_fov)))
        self.v_fov = max(30.0, min(110.0, float(self.v_fov)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ViewDefinition":
        view = cls(
            name=str(data.get("name", "View")),
            roll=float(data.get("roll", 0.0)),
            pitch=float(data.get("pitch", 55.0)),
            h_fov=float(data.get("h_fov", 100.0)),
            v_fov=float(data.get("v_fov", 70.0)),
            enabled=bool(data.get("enabled", True)),
            color=str(data.get("color", "#38BDF8")),
            uid=str(data.get("uid") or uuid.uuid4().hex),
        )
        view.clamp()
        return view


@dataclass
class MediaInfo:
    path: Path
    width: int
    height: int
    duration_seconds: float
    fps: float
    has_audio: bool
    codec_name: str = ""

    @property
    def duration_text(self) -> str:
        total = max(0, int(round(self.duration_seconds)))
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @property
    def resolution_text(self) -> str:
        return f"{self.width} × {self.height}"


@dataclass
class TimestampSettings:
    enabled: bool = True
    crop_x: int = 0
    crop_y: int = 0
    crop_width: int = 700
    crop_height: int = 55
    overlay_width: int = 700
    overlay_x: int = 0
    overlay_y: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimestampSettings":
        return cls(
            enabled=bool(data.get("enabled", True)),
            crop_x=max(0, int(data.get("crop_x", 0))),
            crop_y=max(0, int(data.get("crop_y", 0))),
            crop_width=max(1, int(data.get("crop_width", 700))),
            crop_height=max(1, int(data.get("crop_height", 55))),
            overlay_width=max(50, int(data.get("overlay_width", 700))),
            overlay_x=max(0, int(data.get("overlay_x", 0))),
            overlay_y=max(0, int(data.get("overlay_y", 0))),
        )


@dataclass
class RenderSettings:
    output_width: int = 1920
    output_height: int = 1080
    bitrate_kbps: int = 3000
    audio_bitrate_kbps: int = 128
    maxrate_kbps: int = 5000
    buffer_kbps: int = 12000
    interpolation: str = "cubic"
    encoder_mode: str = "auto"  # auto, nvenc, cpu
    test_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RenderSettings":
        settings = cls(
            output_width=int(data.get("output_width", 1920)),
            output_height=int(data.get("output_height", 1080)),
            bitrate_kbps=int(data.get("bitrate_kbps", 3000)),
            audio_bitrate_kbps=int(data.get("audio_bitrate_kbps", 128)),
            maxrate_kbps=int(data.get("maxrate_kbps", 5000)),
            buffer_kbps=int(data.get("buffer_kbps", 12000)),
            interpolation=str(data.get("interpolation", "cubic")),
            encoder_mode=str(data.get("encoder_mode", "auto")),
            test_seconds=int(data.get("test_seconds", 0)),
        )
        settings.output_width = max(320, settings.output_width)
        settings.output_height = max(240, settings.output_height)
        settings.bitrate_kbps = max(500, settings.bitrate_kbps)
        settings.audio_bitrate_kbps = max(32, settings.audio_bitrate_kbps)
        settings.maxrate_kbps = max(settings.bitrate_kbps, settings.maxrate_kbps)
        settings.buffer_kbps = max(settings.maxrate_kbps, settings.buffer_kbps)
        if settings.interpolation not in {"linear", "cubic", "lanczos"}:
            settings.interpolation = "cubic"
        if settings.encoder_mode not in {"auto", "nvenc", "cpu"}:
            settings.encoder_mode = "auto"
        settings.test_seconds = max(0, settings.test_seconds)
        return settings


def normalize_roll(value: float) -> float:
    value = float(value)
    while value > 180.0:
        value -= 360.0
    while value <= -180.0:
        value += 360.0
    if abs(value) < 0.0001:
        return 0.0
    return value


def roll_pitch_to_normalized(roll: float, pitch: float) -> tuple[float, float]:
    """Return a point inside the centered square crop as normalized x/y."""
    radius = max(0.0, min(1.0, pitch / 90.0)) * 0.5
    radians = math.radians(roll)
    x = 0.5 + math.sin(radians) * radius
    y = 0.5 - math.cos(radians) * radius
    return x, y


def normalized_to_roll_pitch(x: float, y: float) -> tuple[float, float]:
    dx = float(x) - 0.5
    dy = float(y) - 0.5
    radial = math.sqrt(dx * dx + dy * dy)
    if radial < 1e-8:
        return 0.0, 0.0

    max_radial = 0.5
    if radial > max_radial:
        scale = max_radial / radial
        dx *= scale
        dy *= scale
        radial = max_radial

    roll = math.degrees(math.atan2(dx, -dy))
    pitch = min(88.0, radial / max_radial * 90.0)
    return normalize_roll(roll), pitch


def default_views() -> list[ViewDefinition]:
    defaults = [
        ("Top", 0.0, 55.0, 100.0, 70.0),
        ("Right", 90.0, 55.0, 100.0, 70.0),
        ("Bottom", 180.0, 55.0, 100.0, 70.0),
        ("Left", -90.0, 55.0, 100.0, 70.0),
        ("Center", 0.0, 0.0, 110.0, 80.0),
    ]
    return [
        ViewDefinition(
            name=name,
            roll=roll,
            pitch=pitch,
            h_fov=h_fov,
            v_fov=v_fov,
            color=VIEW_COLORS[index % len(VIEW_COLORS)],
        )
        for index, (name, roll, pitch, h_fov, v_fov) in enumerate(defaults)
    ]

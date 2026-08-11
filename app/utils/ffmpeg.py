"""
Thin wrappers around FFmpeg/FFprobe used by the render service.

All calls are synchronous subprocess calls - callers running inside async
code should wrap them with asyncio.to_thread (see render_service.py).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.utils.errors import RenderError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()

_ASPECT_TO_SIZE = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "1:1": (960, 960),
}


def probe_duration(path: str) -> float:
    cmd = [
        settings.FFPROBE_BINARY,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        path,
    ]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, timeout=20)
        data = json.loads(out.stdout.decode())
        return float(data["format"]["duration"])
    except Exception as e:  # noqa: BLE001
        raise RenderError(f"ffprobe failed for {path}: {e}") from e


def normalize_clip(src_path: str, dst_path: str, aspect_ratio: str, target_duration: Optional[float] = None) -> str:
    """Re-encode a clip to the standard pipeline format: H.264/yuv420p,
    fixed size for the requested aspect ratio, optional duration trim/pad.
    """
    width, height = _ASPECT_TO_SIZE.get(aspect_ratio, (1280, 720))
    Path(dst_path).parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    cmd = [settings.FFMPEG_BINARY, "-y", "-i", src_path, "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an"]
    if target_duration:
        cmd += ["-t", str(target_duration)]
    cmd.append(dst_path)
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        stderr = getattr(e, "stderr", b"")
        stderr_text = stderr.decode(errors="ignore") if isinstance(stderr, bytes) else str(stderr)
        raise RenderError(f"Failed to normalize clip {src_path}: {stderr_text[:300]}") from e
    return dst_path


def concat_clips(clip_paths: list[str], dst_path: str) -> str:
    """Concatenate pre-normalized (same codec/size) clips via the
    concat demuxer, which is fast and lossless for matching streams."""
    if not clip_paths:
        raise RenderError("No clips to concatenate")
    Path(dst_path).parent.mkdir(parents=True, exist_ok=True)
    list_file = str(Path(dst_path).with_suffix(".txt"))
    with open(list_file, "w") as f:
        for p in clip_paths:
            # The concat demuxer resolves relative paths in this file
            # relative to the LIST FILE's own directory, not the
            # process's cwd - always write absolute paths here to avoid
            # doubled/broken paths regardless of how LOCAL_STORAGE_PATH
            # or the caller's cwd is configured.
            f.write(f"file '{Path(p).resolve()}'\n")
    cmd = [settings.FFMPEG_BINARY, "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", dst_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        stderr = getattr(e, "stderr", b"")
        stderr_text = stderr.decode(errors="ignore") if isinstance(stderr, bytes) else str(stderr)
        raise RenderError(f"Failed to concatenate clips: {stderr_text[:300]}") from e
    return dst_path


def mix_audio_tracks(
    *,
    voice_paths: list[str],
    music_path: Optional[str],
    sfx_paths: list[str],
    duration: float,
    dst_path: str,
) -> Optional[str]:
    """Mix voice (foreground) + ducked music (background) + sfx into one
    AAC-ready audio track. Returns None if there is nothing to mix."""
    inputs: list[str] = []
    filter_inputs: list[str] = []
    cmd = [settings.FFMPEG_BINARY, "-y"]

    idx = 0
    voice_labels = []
    for vp in voice_paths:
        cmd += ["-i", vp]
        voice_labels.append(f"[{idx}:a]")
        idx += 1

    music_label = None
    if music_path:
        cmd += ["-i", music_path]
        music_label = f"[{idx}:a]"
        idx += 1

    sfx_labels = []
    for sp in sfx_paths:
        cmd += ["-i", sp]
        sfx_labels.append(f"[{idx}:a]")
        idx += 1

    if idx == 0:
        return None

    Path(dst_path).parent.mkdir(parents=True, exist_ok=True)

    filter_parts = []
    mix_inputs = []

    if voice_labels:
        joined = "".join(voice_labels)
        if len(voice_labels) > 1:
            filter_parts.append(f"{joined}amix=inputs={len(voice_labels)}:duration=longest[voice_raw]")
        else:
            # amix with a single input still works, but skip it for
            # clarity/robustness - just relabel the sole voice stream.
            filter_parts.append(f"{voice_labels[0]}anull[voice_raw]")

        if music_label:
            # The voice bus feeds BOTH the sidechain key input below AND
            # the final mix - ffmpeg filtergraph labels are single-use, so
            # an already-consumed label can't be referenced twice without
            # an explicit split. Fan it out here.
            filter_parts.append("[voice_raw]asplit=2[voice_key][voice]")
        else:
            filter_parts.append("[voice_raw]anull[voice]")
        mix_inputs.append("[voice]")

    if music_label:
        # Duck music under dialogue: lower volume, and if voice exists,
        # apply sidechaincompress so music dips when voice is present.
        if voice_labels:
            filter_parts.append(f"{music_label}volume=0.35[musicq]")
            filter_parts.append("[musicq][voice_key]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[music_ducked]")
            mix_inputs.append("[music_ducked]")
        else:
            filter_parts.append(f"{music_label}volume=0.5[music_only]")
            mix_inputs.append("[music_only]")

    for i, sl in enumerate(sfx_labels):
        filter_parts.append(f"{sl}volume=0.6[sfx{i}]")
        mix_inputs.append(f"[sfx{i}]")

    if len(mix_inputs) == 1:
        # A single source needs no amix - just carry it through to [aout].
        single = mix_inputs[0]
        filter_parts.append(f"{single}anull[aout]")
    else:
        joined_mix = "".join(mix_inputs)
        filter_parts.append(f"{joined_mix}amix=inputs={len(mix_inputs)}:duration=longest:normalize=0[aout]")

    filter_complex = ";".join(filter_parts)
    cmd += ["-filter_complex", filter_complex, "-map", "[aout]", "-t", str(duration), "-c:a", "aac", dst_path]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        stderr = getattr(e, "stderr", b"")
        stderr_text = stderr.decode(errors="ignore") if isinstance(stderr, bytes) else str(stderr)
        log_event(logger, "error", "ffmpeg.mix_audio.error", error=stderr_text[:500])
        raise RenderError(f"Failed to mix audio: {stderr_text[:300]}") from e
    return dst_path


def mux_video_audio(video_path: str, audio_path: Optional[str], dst_path: str) -> str:
    Path(dst_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [settings.FFMPEG_BINARY, "-y", "-i", video_path]
    if audio_path:
        cmd += ["-i", audio_path, "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", dst_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        stderr = getattr(e, "stderr", b"")
        stderr_text = stderr.decode(errors="ignore") if isinstance(stderr, bytes) else str(stderr)
        raise RenderError(f"Failed to mux final video: {stderr_text[:300]}") from e
    return dst_path

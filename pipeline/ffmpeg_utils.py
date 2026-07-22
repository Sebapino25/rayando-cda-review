"""Helpers de ffmpeg/ffprobe compartidos entre cortar_clip.py y portadas.py."""

import subprocess
from pathlib import Path


def format_hhmmss(seconds: float) -> str:
    ms = round(seconds * 1000)
    hh, ms = divmod(ms, 3_600_000)
    mm, ms = divmod(ms, 60_000)
    ss, ms = divmod(ms, 1000)
    if ms:
        return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def run_ffmpeg(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló (código {result.returncode}):\n"
            f"cmd: {' '.join(cmd)}\n{result.stderr[-3000:]}"
        )
    return result


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe falló para {path}: {result.stderr}")
    return float(result.stdout.strip())


def extract_frame(video_path: Path, timestamp: float, out_png: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-ss", format_hhmmss(timestamp),
        "-i", str(video_path),
        "-frames:v", "1", "-q:v", "2",
        str(out_png),
    ]
    run_ffmpeg(cmd)

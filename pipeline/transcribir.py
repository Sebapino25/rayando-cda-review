import argparse
import importlib.util
import itertools
import json
import os
import sys
from pathlib import Path

import config
import corregir_nombres

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _register_nvidia_dll_dirs() -> None:
    if os.name != "nt":
        return
    bin_dirs = []
    for module_name in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        spec = importlib.util.find_spec(module_name)
        if not spec or not spec.submodule_search_locations:
            continue
        bin_dir = Path(list(spec.submodule_search_locations)[0]) / "bin"
        if bin_dir.is_dir():
            bin_dirs.append(str(bin_dir))
            os.add_dll_directory(str(bin_dir))
    if bin_dirs:
        os.environ["PATH"] = os.pathsep.join(bin_dirs) + os.pathsep + os.environ["PATH"]


_register_nvidia_dll_dirs()

from faster_whisper import WhisperModel


def find_latest_recording() -> Path:
    candidates = [
        p for p in config.RECORDINGS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in config.RECORDING_EXTENSIONS
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No hay grabaciones en {config.RECORDINGS_DIR}"
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


def resolve_video(video_arg: str | None) -> Path:
    if video_arg is None:
        video = find_latest_recording()
        print(f"No se indicó video, usando la grabación más reciente: {video.name}")
        return video
    p = Path(video_arg)
    if p.is_absolute():
        if not p.exists():
            raise FileNotFoundError(f"No existe el archivo: {p}")
        return p
    candidate = config.RECORDINGS_DIR / video_arg
    if candidate.exists():
        return candidate
    if p.exists():
        return p
    raise FileNotFoundError(
        f"No se encontró '{video_arg}' ni en {config.RECORDINGS_DIR} ni como ruta relativa"
    )


def _start_transcription(model: WhisperModel, video_path: Path):
    segments_gen, info = model.transcribe(
        str(video_path),
        language=config.WHISPER_LANGUAGE,
        vad_filter=config.WHISPER_VAD_FILTER,
        beam_size=config.WHISPER_BEAM_SIZE,
        initial_prompt=corregir_nombres.construir_initial_prompt(),
    )
    iterator = iter(segments_gen)
    first = next(iterator, None)
    return first, iterator, info


def load_model_and_start(video_path: Path, model_size: str):
    try:
        model = WhisperModel(
            model_size, device="cuda", compute_type=config.WHISPER_COMPUTE_TYPE_GPU
        )
        first, iterator, info = _start_transcription(model, video_path)
        print(f"Modelo '{model_size}' corriendo en GPU (CUDA, {config.WHISPER_COMPUTE_TYPE_GPU}).")
        return first, iterator, info
    except Exception as e:
        print(f"No se pudo usar GPU ({e}).")
        print(f"Cargando modelo '{model_size}' en CPU ({config.WHISPER_COMPUTE_TYPE_CPU})...")
        model = WhisperModel(
            model_size, device="cpu", compute_type=config.WHISPER_COMPUTE_TYPE_CPU
        )
        first, iterator, info = _start_transcription(model, video_path)
        print("Modelo corriendo en CPU.")
        return first, iterator, info


def format_srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    hh, ms = divmod(ms, 3_600_000)
    mm, ms = divmod(ms, 60_000)
    ss, ms = divmod(ms, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def format_hhmmss(seconds: float) -> str:
    seconds = int(seconds)
    hh, rem = divmod(seconds, 3600)
    mm, ss = divmod(rem, 60)
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def transcribe(video_path: Path, model_size: str) -> None:
    out_dir = config.TRANSCRIPTS_DIR / video_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    srt_final = out_dir / f"{video_path.stem}.srt"
    json_final = out_dir / f"{video_path.stem}.json"
    srt_tmp = out_dir / f"{video_path.stem}.srt.tmp"
    json_tmp = out_dir / f"{video_path.stem}.json.tmp"

    print(f"Transcribiendo: {video_path}")
    first, iterator, info = load_model_and_start(video_path, model_size)
    if first is not None:
        segments_gen = itertools.chain([first], iterator)
    else:
        segments_gen = iterator

    duration = info.duration
    print(f"Duración detectada: {format_hhmmss(duration)} ({duration:.1f}s)")
    print("Iniciando transcripción, esto puede tardar varios minutos...\n")

    segments_list = []
    idx = 1
    interrupted = False

    srt_file = open(srt_tmp, "w", encoding="utf-8")
    try:
        for seg in segments_gen:
            text = seg.text.strip()
            segments_list.append(
                {"id": idx, "start": seg.start, "end": seg.end, "text": text}
            )
            srt_file.write(
                f"{idx}\n{format_srt_timestamp(seg.start)} --> "
                f"{format_srt_timestamp(seg.end)}\n{text}\n\n"
            )
            srt_file.flush()

            pct = min(seg.end / duration * 100, 100) if duration else 0
            print(
                f"[{pct:5.1f}%] {format_hhmmss(seg.start)} -> "
                f"{format_hhmmss(seg.end)} | {text}"
            )
            idx += 1
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrumpido por el usuario. Guardando el progreso transcrito hasta ahora...")
    finally:
        srt_file.close()

    json_tmp.write_text(
        json.dumps(
            {
                "source_video": str(video_path),
                "language": info.language,
                "duration_seconds": duration,
                "model": model_size,
                "partial": interrupted,
                "segments": segments_list,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.replace(srt_tmp, srt_final)
    os.replace(json_tmp, json_final)

    print("Aplicando corrección de nombres propios (diccionario.json)...")
    diccionario = corregir_nombres.cargar_diccionario()
    n_srt = corregir_nombres.corregir_srt(srt_final, diccionario)
    n_json = corregir_nombres.corregir_json(json_final, diccionario)
    print(f"  {n_json} segmentos corregidos en el .json ({n_srt} bloques en el .srt).")

    if interrupted:
        last_end = segments_list[-1]["end"] if segments_list else 0
        print(
            f"Progreso PARCIAL guardado (hasta {format_hhmmss(last_end)}):\n"
            f"  {srt_final}\n  {json_final}"
        )
        sys.exit(1)

    print(f"\nTranscripción completa.\n  {srt_final}\n  {json_final}")


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe una grabación de Rayando el CDA con faster-whisper."
    )
    parser.add_argument(
        "video",
        nargs="?",
        default=None,
        help="Ruta o nombre de archivo en la carpeta de grabaciones. "
        "Si se omite, se usa la grabación más reciente.",
    )
    parser.add_argument(
        "--modelo",
        default=config.WHISPER_MODEL_SIZE,
        help=f"Modelo de Whisper a usar (default: {config.WHISPER_MODEL_SIZE})",
    )
    args = parser.parse_args()

    video_path = resolve_video(args.video)
    transcribe(video_path, args.modelo)


if __name__ == "__main__":
    main()

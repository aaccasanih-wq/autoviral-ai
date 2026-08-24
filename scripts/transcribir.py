"""Paso 3 del pipeline: transcribir el audio narrado a un ``.srt`` con timestamps.

Esto produce los subtítulos que se queman sobre el video y la duración real por frase.
``faster-whisper`` usa un modelo local; la primera ejecución descarga el modelo elegido.

Salida:
    - ``<outdir>/narracion.srt`  (subtítulos con timestamps precisos).
    - ``<outdir>/narracion.json` (array con {start, end, text} por frase).

Uso:
    python scripts/transcribir.py --audio workspace/audio/narracion.mp3 --outdir workspace/transcripcion
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from guion import ms_timestamp, guardar_json
from envutil import cargar_env, whisper_por_defecto

cargar_env()

# Mantén el cache del modelo de whisper DENTRO del proyecto (workspace/.cache_hf),
# salvo que el usuario defina HF_HOME. Así el pipeline no necesita escribir en ~/.cache
# y queda contenido en el workspace (que además suele estar gitignored).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(_PROJECT_ROOT / "workspace" / ".cache_hf"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def transcribir(audio: Path, outdir: Path, model_size: str, device: str,
                compute_type: str, language: str | None) -> int:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        print("[transcribir] Falta 'faster-whisper'. Instala con: pip install faster-whisper",
              file=sys.stderr)
        return 1

    if not audio.is_file():
        print(f"[transcribir] No se encuentra el audio: {audio}", file=sys.stderr)
        return 1

    print(f"[transcribir] Cargando modelo '{model_size}' (device={device}, compute={compute_type}) ...")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    print(f"[transcribir] Transcribiendo {audio.name} ...")
    segments, info = model.transcribe(
        str(audio),
        language=language,
        vad_filter=True,
        beam_size=5,
    )

    lineas: list[str] = []
    frases: list[dict] = []
    idx = 1
    for seg in segments:
        start, end, text = float(seg.start), float(seg.end), seg.text.strip()
        if not text:
            continue
        frases.append({"start": round(start, 3), "end": round(end, 3), "text": text})
        lineas.append(
            f"{idx}\n{ms_timestamp(start)} --> {ms_timestamp(end)}\n{text}\n"
        )
        idx += 1

    srt = outdir / "narracion.srt"
    srt.write_text("\n".join(lineas), encoding="utf-8")
    guardar_json(frases, outdir / "narracion.json")

    print(f"[transcribir] OK: {len(frases)} frases | idioma={info.language} "
          f"(prob {info.language_probability:.2f})")
    print(f"[transcribir] -> {srt}")
    print(f"[transcribir] -> {outdir / 'narracion.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Transcribir narración a .srt (faster-whisper).")
    ap.add_argument("--audio", default="workspace/audio/narracion.mp3", help="Ruta al audio.")
    ap.add_argument("--outdir", default="workspace/transcripcion", help="Carpeta de salida.")
    ap.add_argument("--model", default=None,
                    help="Modelo whisper: tiny/base/small/medium/large-v3. Por defecto el de .env (small).")
    ap.add_argument("--device", default="cpu", help="cpu/cuda/auto.")
    ap.add_argument("--compute-type", default="int8", help="int8/float16/float32.")
    ap.add_argument("--language", default=None, help="Código ISO (p. ej. es). Por defecto auto.")
    args = ap.parse_args(argv)
    model_size = args.model or whisper_por_defecto()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return transcribir(Path(args.audio), outdir, model_size, args.device,
                       args.compute_type, args.language)


if __name__ == "__main__":
    raise SystemExit(main())

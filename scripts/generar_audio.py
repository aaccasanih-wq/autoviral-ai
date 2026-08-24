"""Paso 2 del pipeline: generar audio narrado por escena con ``edge-tts``.

Salida:
    - Un ``.mp3`` por escena en ``<outdir>/escena-XX.mp3``.
    - ``<outdir>/narracion.mp3``: el track completo (concatenado en orden de escenas).
    - ``<outdir>/timings.json``: duración real de cada escena (clave = id de escena).

Uso:
    python scripts/generar_audio.py --guion workspace/guion.json --outdir workspace/audio
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

from guion import cargar_guion, escenas, guardar_json
from envutil import cargar_env, voz_por_defecto

cargar_env()

# Voz por defecto (edge-tts, voz en español). Ajustable por env EDGE_TTS_VOZ o por CLI --voz.
VOZ_DEF = voz_por_defecto()


def _leer_duracion(path: Path) -> float:
    """Devuelve la duración (segundos) de un MP3 usando mutagen; fallback por ffprobe."""
    try:
        import mutagen
        from mutagen.mp3 import MP3

        info = MP3(str(path)).info
        return float(info.length)
    except Exception:
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True)
            try:
                return float(out.stdout.strip())
            except ValueError:
                pass
    return 0.0


async def _sintetizar(texto: str, voz: str, rate: str, out: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(texto, voz, rate=rate, volume="+0%")
    await communicate.save(str(out))


async def _todo(escenas_habladas: list[tuple[str, str, Path]], voz: str, rate: str) -> None:
    await asyncio.gather(*(_sintetizar(t, voz, rate, out) for _, t, out in escenas_habladas))


def _concatenar_audio(entradas: list[Path], salida: Path) -> bool:
    """Concatena mp3 en orden. Devuelve False si no se pudo (sin ffmpeg)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    tmp = salida.with_suffix(".txt")
    tmp.write_text("".join(f"file '{p.as_posix()}'\n" for p in entradas), encoding="utf-8")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(tmp),
             "-c", "copy", str(salida)],
            check=True, capture_output=True)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generar audio narrado por escena (edge-tts).")
    ap.add_argument("--guion", default="workspace/guion.json", help="Ruta al guion.json.")
    ap.add_argument("--outdir", default="workspace/audio", help="Carpeta de salida.")
    ap.add_argument("--voz", default=VOZ_DEF, help="Voz de edge-tts.")
    ap.add_argument("--rate", default="+0%", help="Velocidad de la voz (p. ej. -10%% o +5%%).")
    args = ap.parse_args(argv)

    try:
        guion = cargar_guion(args.guion)
    except Exception as e:
        print(f"[audio] Error: {e}", file=sys.stderr)
        return 1

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    escs = escenas(guion)
    trabajos: list[tuple[str, str, Path]] = []
    for esc in escs:
        salida = outdir / f"{esc['id']}.mp3"
        trabajos.append((esc["id"], str(esc["narracion"]).strip(), salida))

    print(f"[audio] Sintetizando {len(trabajos)} escenas con voz '{args.voz}' ...")
    asyncio.run(_todo(trabajos, args.voz, args.rate))

    # Duración real por escena, a partir de los mp3 generados.
    timings: dict[str, dict] = {}
    rutas: list[Path] = []
    for esc_id, _, out in trabajos:
        if not out.is_file() or out.stat().st_size == 0:
            print(f"[audio] Aviso: no se generó {out.name}", file=sys.stderr)
            continue
        dur = _leer_duracion(out)
        timings[esc_id] = {"audio": out.name, "duracion_segundos": round(dur, 3)}
        rutas.append(out)

    if not rutas:
        print("[audio] Error: no se generó ningún audio.", file=sys.stderr)
        return 1

    narracion = outdir / "narracion.mp3"
    if _concatenar_audio(rutas, narracion):
        print(f"[audio] Track completo -> {narracion}")
    else:
        # Fallback sin ffmpeg: copia los mp3 concatenados (reproducible en muchos players).
        with open(narracion, "wb") as f:
            for r in rutas:
                f.write(r.read_bytes())
        print(f"[audio] Aviso: ffmpeg no disponible; {narracion} es concatenación best-effort.")

    guardar_json({"voz": args.voz, "escenas": timings}, outdir / "timings.json")
    print(f"[audio] timings -> {outdir / 'timings.json'}")
    print(f"[audio] OK: {len(timings)} escenas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Paso 2 del pipeline: generar audio narrado por escena con motor TTS **modular**.

Motores soportados (intercambiables; el pipeline NO está atado a uno):

* ``edge`` — edge-tts (servicio online de lectura de Microsoft Edge; gratis, sin API key).
  Voz/rate/pitch configurables. Default del pipeline.
* ``gcp`` — Google Cloud Text-to-Speech (REST ``text:synthesize``). Requiere ``GCP_TTS_API_KEY``.
  Free tier mensual permanente: WaveNet 4M chars, Neural2 1M chars, Chirp 3 HD 1M chars.

Selección del motor (prioridad): flag ``--motor`` > ``parametros.tts.motor`` del guion >
``TTS_MOTOR`` del ``.env`` > automático (``gcp`` si existe ``GCP_TTS_API_KEY``, si no ``edge``).
Voz/velocidad/tono (misma prioridad): ``--voz/--rate/--pitch`` > ``parametros.tts`` del guion >
variables ``EDGE_TTS_VOZ`` / ``GCP_TTS_VOZ`` > default.

Salida (idéntica para todos los motores):
    - Un ``.mp3`` por escena en ``<outdir>/escena-XX.mp3``.
    - ``<outdir>/narracion.mp3``: el track completo (concatenado en orden de escenas).
    - ``<outdir>/timings.json``: duración real de cada escena (clave = id de escena) + motor usado.

Uso:
    python scripts/generar_audio.py --guion workspace/guion.json --outdir workspace/audio
    python scripts/generar_audio.py --guion sesion/guion.json --motor gcp --voz es-ES-Neural2-F
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from guion import cargar_guion, directorio_sesion, escenas, guardar_json
from envutil import (cargar_env, edge_tts_voz_por_defecto, gcp_tts_apikey,
                     gcp_tts_voz_por_defecto, tts_motor_por_defecto)

cargar_env()

MOTORES = ("edge", "gcp")

# Defaults por motor (se usan solo si no hay nada en guion/.env/CLI).
VOZ_POR_MOTOR = {
    "edge": edge_tts_voz_por_defecto(),      # es-ES-ElviraNeural
    "gcp": gcp_tts_voz_por_defecto(),        # es-ES-Neural2-F
}
RATE_DEF = "+0%"
PITCH_DEF = {"edge": "+0Hz", "gcp": "0"}


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


# ---------------------------------------------------------------------------
# Motor edge-tts (Microsoft Edge Read-Aloud; gratis, sin API key)
# ---------------------------------------------------------------------------

async def _sintetizar_edge(texto: str, voz: str, rate: str, pitch: str, out: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(texto, voz, rate=rate, volume="+0%", pitch=pitch)
    await communicate.save(str(out))


# ---------------------------------------------------------------------------
# Motor Google Cloud TTS (REST; requiere GCP_TTS_API_KEY)
# ---------------------------------------------------------------------------

def _a_flotante(valor: str, default: float) -> float:
    """Convierte '+10%', '-2', '+2Hz', '1.1' a float. '%' se interpreta como porcentaje de 1.0."""
    m = re.search(r"(-?\d+(?:\.\d+)?)", str(valor or ""))
    if not m:
        return default
    num = float(m.group(1))
    if "%" in str(valor):
        return 1.0 + num / 100.0
    return num


def _sintetizar_gcp(texto: str, voz: str, rate: str, pitch: str, apikey: str, out: Path) -> None:
    """Sintetiza con Cloud TTS y escribe el MP3 (respuesta base64 en ``audioContent``)."""
    language_code = "-".join(voz.split("-")[:2]) or "es-ES"
    body = {
        "input": {"text": texto},
        "voice": {"languageCode": language_code, "name": voz},
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": max(0.25, min(4.0, _a_flotante(rate, 1.0))),
            "pitch": max(-20.0, min(20.0, _a_flotante(pitch, 0.0))),
        },
    }
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={apikey}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    audio = data.get("audioContent")
    if not audio:
        raise RuntimeError(f"Respuesta sin audioContent: {json.dumps(data)[:200]}")
    out.write_bytes(base64.b64decode(audio))


# ---------------------------------------------------------------------------
# Concatenación y orquestación
# ---------------------------------------------------------------------------

def _concatenar_audio(entradas: list[Path], salida: Path) -> bool:
    """Concatena mp3 en orden. Devuelve False si no se pudo (sin ffmpeg)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    tmp = salida.with_suffix(".txt")
    # Rutas ABSOLUTAS: el demuxer concat resuelve las rutas relativas respecto a la carpeta
    # del archivo de lista, no del cwd. Usamos rutas absolutas para que sea independiente.
    tmp.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in entradas), encoding="utf-8")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(tmp),
             "-c", "copy", str(salida)],
            check=True, capture_output=True)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def _resolver_config(args, guion: dict) -> tuple[str, str, str, str]:
    """Resuelve (motor, voz, rate, pitch) con prioridad CLI > guion.parametros.tts > .env > default."""
    tts_guion = (guion.get("parametros") or {}).get("tts") or {}
    if not isinstance(tts_guion, dict):
        tts_guion = {}

    motor = (args.motor or tts_guion.get("motor") or tts_motor_por_defecto()).strip().lower()
    if motor not in MOTORES:
        print(f"[audio] Motor desconocido '{motor}'; uso 'edge'.", file=sys.stderr)
        motor = "edge"

    voz = (args.voz or tts_guion.get("voz") or VOZ_POR_MOTOR.get(motor)).strip()
    rate = str(args.rate if args.rate is not None else tts_guion.get("rate") or RATE_DEF)
    pitch = str(args.pitch if args.pitch is not None else tts_guion.get("pitch")
                or PITCH_DEF.get(motor, "+0Hz"))
    return motor, voz, rate, pitch


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generar audio narrado por escena (TTS modular: edge-tts / Google Cloud TTS).")
    ap.add_argument("--guion", default="workspace/guion.json", help="Ruta al guion.json.")
    ap.add_argument("--outdir", default=None,
                    help="Carpeta de salida. Por defecto <carpeta del guion>/audio.")
    ap.add_argument("--motor", default=None, choices=list(MOTORES),
                    help="Motor TTS. Default: parametros.tts.motor del guion, TTS_MOTOR del .env, "
                         "o automático (gcp si hay GCP_TTS_API_KEY; si no edge).")
    ap.add_argument("--voz", default=None,
                    help="Voz del motor (edge: es-ES-ElviraNeural; gcp: es-ES-Neural2-F).")
    ap.add_argument("--rate", default=None,
                    help="Velocidad de la voz (p. ej. -10%% o +5%%; en gcp se convierte a speakingRate).")
    ap.add_argument("--pitch", default=None,
                    help="Tono de la voz (p. ej. -2 más grave, +2 más agudo; edge usa Hz, gcp semitonos).")
    args = ap.parse_args(argv)

    try:
        guion = cargar_guion(args.guion)
    except Exception as e:
        print(f"[audio] Error: {e}", file=sys.stderr)
        return 1

    motor, voz, rate, pitch = _resolver_config(args, guion)
    apikey = gcp_tts_apikey() if motor == "gcp" else None
    if motor == "gcp" and not apikey:
        print("[audio] Motor 'gcp' sin GCP_TTS_API_KEY en .env. "
              "Añade la clave o usa --motor edge.", file=sys.stderr)
        return 2

    outdir = Path(args.outdir) if args.outdir else directorio_sesion(args.guion) / "audio"
    outdir.mkdir(parents=True, exist_ok=True)

    escs = escenas(guion)
    trabajos: list[tuple[str, str, Path]] = []
    for esc in escs:
        salida = outdir / f"{esc['id']}.mp3"
        trabajos.append((esc["id"], str(esc["narracion"]).strip(), salida))

    print(f"[audio] Sintetizando {len(trabajos)} escenas | motor={motor} | voz='{voz}' "
          f"| rate='{rate}' | pitch='{pitch}' ...")
    if motor == "edge":
        async def _todo_edge() -> None:
            await asyncio.gather(*(
                _sintetizar_edge(t, voz, rate, pitch, out) for _, t, out in trabajos))
        asyncio.run(_todo_edge())
    else:
        for _, texto, out in trabajos:
            _sintetizar_gcp(texto, voz, rate, pitch, apikey or "", out)

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

    guardar_json({"motor": motor, "voz": voz, "rate": rate, "pitch": pitch, "escenas": timings},
                 outdir / "timings.json")
    print(f"[audio] timings -> {outdir / 'timings.json'}")
    print(f"[audio] OK: {len(timings)} escenas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Orquestador de extremo a extremo del pipeline AutoViral AI.

Encadena las etapas de la Fase 2 en orden (audio → transcripción → imágenes → ensamblado),
reutilizando cada script como subproceso para que sean ejecutables de forma independiente.

Uso:
    python scripts/pipeline.py --guion workspace/guion.json
    python scripts/pipeline.py --guion workspace/guion.json --pasos audio,transcripcion
    python scripts/pipeline.py --pasos ensamblado   # asume audio/transcripcion/imagenes ya hechos
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

PASOS = {"audio", "transcripcion", "imagenes", "ensamblado"}
ORDEN_DEF = ["audio", "transcripcion", "imagenes", "ensamblado"]

# Script por paso.
SCRIPT = {
    "audio": "scripts/generar_audio.py",
    "transcripcion": "scripts/transcribir.py",
    "imagenes": "scripts/generar_imagenes.py",
    "ensamblado": "scripts/ensamblar_video.py",
}


def _ejecutar(paso: str, guion: Path, voz: str, modelo: str, formatos: str,
              whisper_model: str) -> int:
    script = RAIZ / SCRIPT[paso]
    cmd = [sys.executable, str(script)]
    # Rutas por defecto del workspace (consistentes con config/settings.example.json).
    if paso in ("audio", "imagenes", "ensamblado"):
        cmd += ["--guion", str(guion)]
    if paso == "audio":
        cmd += ["--outdir", "workspace/audio", "--voz", voz]
    elif paso == "transcripcion":
        cmd += ["--audio", "workspace/audio/narracion.mp3",
                "--outdir", "workspace/transcripcion", "--model", whisper_model]
    elif paso == "imagenes":
        cmd += ["--outdir", "workspace/imagenes", "--model", modelo]
    elif paso == "ensamblado":
        cmd += ["--imagedir", "workspace/imagenes",
                "--audio", "workspace/audio/narracion.mp3",
                "--srt", "workspace/transcripcion/narracion.srt",
                "--outdir", "workspace/video"]
        if formatos:
            cmd += ["--formato", formatos]
    print(f"\n[->] {paso}: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(RAIZ)).returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Orquestador del pipeline Automático de AutoViral AI.")
    ap.add_argument("--guion", default="workspace/guion.json", help="Ruta al guion.json.")
    ap.add_argument("--pasos", default="all",
                    help="Etapas a ejecutar, separadas por coma, o 'all' (cadena completa).")
    ap.add_argument("--voz", default="es-ES-ElviraNeural", help="Voz de edge-tts.")
    ap.add_argument("--model", default="gemini-3.1-flash-image-preview",
                    help="Modelo de imagen de Gemini.")
    ap.add_argument("--whisper-model", default="small",
                    help="Modelo whisper para la transcripción (tiny/base/small/...).")
    ap.add_argument("--formato", default=None, choices=["vertical", "horizontal"],
                    help="Sobrescribe el formato para el ensamblado.")
    args = ap.parse_args(argv)

    guion = Path(args.guion)
    if not guion.is_file():
        print(f"[pipeline] No existe el guion: {guion}", file=sys.stderr)
        print("[pipeline] Genera primero un guion con la skill '/ideacion-video'.", file=sys.stderr)
        return 2

    pasos = ORDEN_DEF if args.pasos == "all" else [p.strip() for p in args.pasos.split(",")]
    desconocidos = [p for p in pasos if p not in PASOS]
    if desconocidos:
        print(f"[pipeline] Pasos desconocidos: {', '.join(desconocidos)}. Válidos: "
              f"{', '.join(sorted(PASOS))}.", file=sys.stderr)
        return 2

    for paso in pasos:
        # Las imágenes necesitan la API key de Gemini; avisamos sin abortar el resto.
        if paso == "imagenes" and not (os.environ.get("GEMINI_API_KEY")):
            print(f"[pipeline] Aviso: GEMINI_API_KEY no definida; se omite el paso 'imagenes'.",
                  file=sys.stderr)
            continue
        if _ejecutar(paso, guion, args.voz, args.model, args.formato,
                     args.whisper_model) != 0:
            print(f"[pipeline] El paso '{paso}' falló. Abortando.", file=sys.stderr)
            return 1

    print("\n[pipeline] Pipeline completado. Revisa el video final en workspace/video/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

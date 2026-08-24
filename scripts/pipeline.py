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
import subprocess
import sys
from pathlib import Path

from envutil import (apikey_proveedor, cargar_env, model_imagen_por_defecto,
                     proveedor_imagen_por_defecto, voz_por_defecto, whisper_por_defecto)

cargar_env()

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
              whisper_model: str, referencia: str | None = None,
              proveedor: str | None = None, estilo: str | None = None) -> int:
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
        if proveedor:
            cmd += ["--proveedor", proveedor]
        if referencia:
            cmd += ["--referencia", referencia]
        if estilo:
            cmd += ["--estilo", estilo]
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
    ap.add_argument("--voz", default=voz_por_defecto(), help="Voz de edge-tts.")
    ap.add_argument("--model", default=model_imagen_por_defecto(),
                    help="Modelo de imagen del proveedor activo (Gemini o Qwen).")
    ap.add_argument("--proveedor", default=None, choices=["gemini", "qwen"],
                    help="Proveedor de imágenes para el paso 'imagenes'. " 
                         "Por defecto el de IMAGEN_PROVEEDOR o el detectado.")
    ap.add_argument("--estilo", default=None,
                    help="Ajuste global de estilo/feedback para las imágenes del paso "
                         "'imagenes' (se añade a todos los prompts).")
    ap.add_argument("--whisper-model", default=whisper_por_defecto(),
                    help="Modelo whisper para la transcripción (tiny/base/small/...).")
    ap.add_argument("--formato", default=None, choices=["vertical", "horizontal"],
                    help="Sobrescribe el formato para el ensamblado.")
    ap.add_argument("--referencia", default=None,
                    help="Ruta a una imagen de referencia (.png/.jpg/...) para el estilo animado "
                         "de las imágenes. Si no se pasa, se usa parametros.imagen_referencia del "
                         "guion (si existe).")
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

    proveedor = (args.proveedor or proveedor_imagen_por_defecto()).strip().lower()
    for paso in pasos:
        # Las imágenes necesitan la API key del proveedor; avisamos sin abortar el resto.
        if paso == "imagenes" and not apikey_proveedor(proveedor):
            print(f"[pipeline] Aviso: no hay API key para el proveedor '{proveedor}' "
                  f"({('QWEN_API_KEY' if proveedor == 'qwen' else 'GEMINI_API_KEY')}); "
                  f"se omite el paso 'imagenes'.", file=sys.stderr)
            continue
        if _ejecutar(paso, guion, args.voz, args.model, args.formato, args.whisper_model,
                     args.referencia, proveedor, args.estilo) != 0:
            print(f"[pipeline] El paso '{paso}' falló. Abortando.", file=sys.stderr)
            return 1

    print("\n[pipeline] Pipeline completado. Revisa el video final en workspace/video/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

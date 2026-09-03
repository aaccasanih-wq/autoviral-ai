"""Paso 1 del pipeline: verificar dependencias y herramientas del entorno.

Reporta si están presentes las herramientas locales (edge-tts, faster-whisper, google-genai),
el motor FFmpeg y las herramientas MCP (kino de Kinocut y nano-banana-2 de Gemini).

Uso:
    python scripts/verificar_entorno.py [--json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys

CHECKS_LOCAL = [
    ("edge-tts", "edge_tts", "texto-a-voz narración"),
    ("faster-whisper", "faster_whisper", "transcripción a .srt/.ass"),
    ("google-genai", "google.genai", "imágenes Gemini (vía CLI)"),
    ("imageio-ffmpeg", "imageio_ffmpeg", "ffmpeg con libass para subtítulos quemados"),
    ("mutagen", "mutagen", "leer duración de audio"),
]
BINARIOS = [
    ("ffmpeg", "motor multimedia (requerido; vale PATH o fallback imageio-ffmpeg/.venv)"),
    ("ffprobe", "inspección de metadatos (opcional; el pipeline usa mutagen + ffmpeg)"),
]
# Opcionales: no bloquean el pipeline ni cuentan como FALTA en el resumen.
BINARIOS_OPCIONALES = [
    ("kino", "CLI de Kinocut (alternativa de edición MCP, opcional)"),
]
MCP_SRVS = ["nano-banana-2", "kinocut"]


def _mod_ok(nombre_import: str) -> bool:
    return importlib.util.find_spec(nombre_import) is not None


def _ffmpeg_fallback_path() -> str | None:
    """Ruta de ffmpeg provista por imageio-ffmpeg (pip), si está instalada."""
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and __import__("pathlib").Path(p).is_file():
            return p
    except Exception:
        pass
    # symlink local .venv/bin/ffmpeg o .venv/Scripts/ffmpeg.exe (creado por setup.sh/.bat)
    for cand in (__import__("pathlib").Path(".venv/bin/ffmpeg"),
                 __import__("pathlib").Path(".venv/bin/ffmpeg.exe"),
                 __import__("pathlib").Path(".venv/Scripts/ffmpeg.exe"),
                 __import__("pathlib").Path(".venv/Scripts/ffmpeg")):
        if cand.is_file():
            return str(cand)
    return None


def _bin_ok(bin_: str) -> bool:
    if shutil.which(bin_) is not None:
        return True
    # fallback para ffmpeg/ffprobe vía imageio-ffmpeg
    if bin_ in ("ffmpeg", "ffprobe"):
        return _ffmpeg_fallback_path() is not None
    return False


def _check_mcp(servidor: str) -> bool:
    """Heurística: el servidor MCP está configurado si existe config en .mcp.json o mcp/*.json."""
    import pathlib

    for base in (pathlib.Path(".mcp.json"), pathlib.Path("mcp") / f"{servidor}.json",
                 pathlib.Path("config") / f"mcp-{servidor}.json"):
        if base.is_file() and servidor in (base.read_text(encoding="utf-8") or ""):
            return True
    return False


def _ffmpeg_bin() -> str:
    """Binario ffmpeg a usar: PATH o fallback imageio-ffmpeg."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    fb = _ffmpeg_fallback_path()
    return fb or "ffmpeg"


def _ffmpeg_tiene_libass() -> bool:
    """True si el ffmpeg en PATH (o fallback) soporta el filtro 'subtitles'/'ass' (libass)."""
    import re, subprocess
    try:
        out = subprocess.run([_ffmpeg_bin(), "-hide_banner", "-filters"], capture_output=True, text=True, timeout=10).stdout
        return bool(re.search(r"(?<![-\w])subtitles(?![-\w])", out) or re.search(r"(?<![-\w])ass(?![-\w])", out))
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verificación del entorno de AutoViral AI.")
    ap.add_argument("--json", action="store_true", help="Salida JSON.")
    args = ap.parse_args(argv)

    local = [{"name": n, "presente": _mod_ok(m), "rol": r} for n, m, r in CHECKS_LOCAL]
    bins = [{"name": n, "presente": _bin_ok(n), "rol": r} for n, r in BINARIOS]
    # Extra: ffmpeg con libass para subtítulos quemados
    tiene_libass = _ffmpeg_tiene_libass()
    bins.append({"name": "ffmpeg (libass)", "presente": tiene_libass, "rol": "quemado de subtítulos ASS (imageio-ffmpeg trae ffmpeg 7.1 con libass)"})
    opcionales = [{"name": n, "presente": _bin_ok(n), "rol": r} for n, r in BINARIOS_OPCIONALES]
    mcp = [{"name": s, "presente": _check_mcp(s), "rol": "servidor MCP de " + s} for s in MCP_SRVS]

    # Motores TTS (opcionales): edge siempre; gcp si hay API key configurada.
    try:
        from envutil import cargar_env as _cenv, gcp_tts_apikey, tts_motor_por_defecto
        _cenv()
        tts = [{"name": "edge (edge-tts)", "presente": _mod_ok("edge_tts"),
                "rol": "motor TTS gratis (Microsoft Edge Read-Aloud, online)"},
               {"name": "gcp (Google Cloud TTS)", "presente": bool(gcp_tts_apikey()),
                "rol": f"motor TTS premium; activo={tts_motor_por_defecto()}"}]
    except Exception:
        tts = []

    if args.json:
        print(json.dumps({"local": local, "binarios": bins, "mcp": mcp, "tts": tts}, indent=2))
        return 0

    print("=== AutoViral AI — verificación del entorno ===")
    for grupo, items in (("Herramientas locales (pip)", local),
                         ("Binarios del sistema", bins),
                         ("Opcionales (no bloquean)", opcionales),
                         ("Servidores MCP", mcp),
                         ("Motores TTS (default gcp, fallback edge)", tts)):
        print(f"\n{grupo}")
        for it in items:
            estado = "OK" if it["presente"] else "FALTA"
            print(f"  [{estado}] {it['name']} — {it['rol']}")

    faltan = sum(1 for i in local + bins if not i["presente"])
    print("\nResumen:", "OK" if faltan == 0 else
          f"{faltan} elementos ausentes. Revisa README.md → Prerrequisitos.")
    return 0 if faltan == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

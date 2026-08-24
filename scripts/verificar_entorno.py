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
    ("faster-whisper", "faster_whisper", "transcripción a .srt"),
    ("google-genai", "google.genai", "imágenes Gemini (vía CLI)"),
    ("mutagen", "mutagen", "leer duración de audio"),
]
BINARIOS = [
    ("ffmpeg", "motor multimedia (requerido por ensamblado y por Kinocut)"),
    ("ffprobe", "inspección de metadatos de medios"),
    ("kino", "CLI de Kinocut (alternativa de edición MCP)"),
]
MCP_SRVS = ["nano-banana-2", "kinocut"]


def _mod_ok(nombre_import: str) -> bool:
    return importlib.util.find_spec(nombre_import) is not None


def _bin_ok(bin_: str) -> bool:
    return shutil.which(bin_) is not None


def _check_mcp(servidor: str) -> bool:
    """Heurística: el servidor MCP está configurado si existe config en .mcp.json o mcp/*.json."""
    import pathlib

    for base in (pathlib.Path(".mcp.json"), pathlib.Path("mcp") / f"{servidor}.json",
                 pathlib.Path("config") / f"mcp-{servidor}.json"):
        if base.is_file() and servidor in (base.read_text(encoding="utf-8") or ""):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verificación del entorno de AutoViral AI.")
    ap.add_argument("--json", action="store_true", help="Salida JSON.")
    args = ap.parse_args(argv)

    local = [{"name": n, "presente": _mod_ok(m), "rol": r} for n, m, r in CHECKS_LOCAL]
    bins = [{"name": n, "presente": _bin_ok(n), "rol": r} for n, r in BINARIOS]
    mcp = [{"name": s, "presente": _check_mcp(s), "rol": "servidor MCP de " + s} for s in MCP_SRVS]

    if args.json:
        print(json.dumps({"local": local, "binarios": bins, "mcp": mcp}, indent=2))
        return 0

    print("=== AutoViral AI — verificación del entorno ===")
    for grupo, items in (("Herramientas locales (pip)", local),
                         ("Binarios del sistema", bins),
                         ("Servidores MCP", mcp)):
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

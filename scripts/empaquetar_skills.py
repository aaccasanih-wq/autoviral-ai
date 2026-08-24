"""Genera los zips de distribución de cada skill para Claude Desktop.

Estructura por zip (según PROJECT.md):
    <nombre>-skill.zip
    ├── skill.json        # metadatos (nombre, versión, descripción)
    ├── instructions.md    # instrucciones del sistema (contenido del skill)
    └── README.md          # documentación breve

Uso:
    python scripts/empaquetar_skills.py [--dest dist]
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = ("ideacion-video", "generacion-video")
DESCRIPCIONES = {
    "ideacion-video": ("Guía al usuario desde una idea vaga (o sin idea) hasta un guion de video "
                       "corto final, estructurado y confirmado. Fase 1: ideación y redacción. "
                       "Nunca genera audio, imágenes ni video."),
    "generacion-video": ("Ejecuta el pipeline técnico de producción de un video corto desde un "
                         "guion confirmado: audio (edge-tts), transcripción (.srt), imágenes por "
                         "escena (Gemini) y ensamblado final (FFmpeg/Kinocut). Fase 2."),
}


def _body(raw: str) -> str:
    """Devuelve el contenido del markdown sin el bloque de frontmatter YAML."""
    m = re.match(r"^---\n.*?\n---\n", raw, flags=re.DOTALL)
    return raw[m.end():].strip() + "\n" if m else raw.strip() + "\n"


def _readme(nombre: str) -> str:
    return f"""# Skill: {nombre}

Skill de AutoViral AI para cargar en Claude Desktop.

- **Nombre:** `{nombre}`
- **Versión:** 1.0.0
- **Descripción:** {DESCRIPCIONES[nombre]}

## Carga en Claude Desktop

Importa este `.zip` desde la configuración de skills de Claude Desktop. Las instrucciones del
sistema están en `instructions.md`.

## Cómo se usa

Carga la skill cuando el usuario indique que quiere crear/refinar una idea de video
(`ideacion-video`) o producir un video a partir de un guion confirmado (`generacion-video`).

---
Proyecto: AutoViral AI · Licencia MIT
"""


def generar(dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    zips: list[Path] = []
    for nombre in SKILLS:
        src = RAIZ / "skills" / nombre / "SKILL.md"
        if not src.is_file():
            raise FileNotFoundError(f"No existe {src}")
        z = dest / f"{nombre}-skill.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as fz:
            fz.writestr("skill.json", json.dumps({
                "name": nombre,
                "version": "1.0.0",
                "description": DESCRIPCIONES[nombre],
                "author": "AutoViral AI",
                "license": "MIT",
            }, ensure_ascii=False, indent=2) + "\n")
            fz.writestr("instructions.md", _body(src.read_text(encoding="utf-8")))
            fz.writestr("README.md", _readme(nombre))
        zips.append(z)
        print(f"[empaquetar] -> {z}")
    return zips


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Genera zips de skill para Claude Desktop.")
    ap.add_argument("--dest", default=str(RAIZ / "dist"), help="Carpeta de salida.")
    args = ap.parse_args(argv)
    generar(Path(args.dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

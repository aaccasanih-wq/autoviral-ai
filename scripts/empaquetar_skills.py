"""Genera los zips de distribución de cada skill para Claude Desktop.

Estructura por zip (formato de skill de Claude Desktop):
    <nombre>-skill.zip
    └── <nombre>/            # carpeta con el nombre de la skill
        └── SKILL.md         # definición completa de la skill (con frontmatter)

Claude Desktop importa la carpeta cuyo nombre es el de la skill y define el comportamiento del
agente en el SKILL.md que está dentro.

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
SKILLS = ("ideacion-video", "generacion-video", "creacion-estilo")
DESCRIPCIONES = {
    "ideacion-video": ("Guía al usuario desde una idea vaga (o sin idea) hasta un guion de video "
                       "corto final, estructurado y confirmado. Fase 1: nicho, ideación y redacción. "
                       "Nunca genera audio, imágenes ni video."),
    "generacion-video": ("Ejecuta el pipeline técnico de producción de un video corto desde un "
                         "guion confirmado: audio (TTS default gcp, fallback edge), "
                         "transcripción (.srt), imágenes por escena (Gemini o Qwen, con estilos "
                         "reutilizables y anti-drift) y ensamblado final (FFmpeg/Kinocut). Fase 2."),
    "creacion-estilo": ("Crea un estilo de animación + voz reutilizable a partir de imágenes de "
                        "referencia y muestra/descripción de voz. Guarda en estilos/<id>/ y lo "
                        "registra en estilos/catalogo.json."),
}


def _body(raw: str) -> str:
    """Devuelve el contenido del markdown sin el bloque de frontmatter YAML."""
    m = re.match(r"^---\n.*?\n---\n", raw, flags=re.DOTALL)
    return raw[m.end():].strip() + "\n" if m else raw.strip() + "\n"


def _readme(nombre: str) -> str:
    usos = {
        "ideacion-video": "crear/refinar una idea de video y obtener un guion confirmado",
        "generacion-video": "producir un video a partir de un guion confirmado",
        "creacion-estilo": "guardar/crear un estilo de animación + voz reutilizable",
    }
    return f"""# Skill: {nombre}

Skill de AutoViral AI para cargar en Claude Desktop.

- **Nombre:** `{nombre}`
- **Versión:** 1.1.0
- **Descripción:** {DESCRIPCIONES[nombre]}

## Carga en Claude Desktop

Importa este `.zip` desde la configuración de skills de Claude Desktop. Las instrucciones del
sistema están en `instructions.md`.

## Cómo se usa

Carga la skill cuando el usuario indique que quiere {usos.get(nombre, nombre)}.

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
            # Estructura de skill de Claude Desktop: carpeta con el nombre + SKILL.md dentro.
            # El SKILL.md va completo (con el frontmatter name/description/whenToUse).
            fz.writestr(f"{nombre}/SKILL.md", src.read_text(encoding="utf-8"))
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

"""Carga el archivo ``.env`` de la raíz del proyecto (si existe).

Permite que los scripts lean `GEMINI_API_KEY`, `NANO_BANANA_MODEL`, `EDGE_TTS_VOZ` y
`WHISPER_MODEL` sin depender de variables de entorno exportadas manualmente.
"""

from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def cargar_env() -> bool:
    """Intenta cargar ``.env``. Devuelve True si python-dotenv está disponible."""
    try:
        from dotenv import load_dotenv

        load_dotenv(RAIZ / ".env", override=False)
        return True
    except ImportError:
        return False


def env_o(key: str, default: str | None = None) -> str | None:
    """Valor de una variable de entorno, o el default si no está definida."""
    valor = os.environ.get(key)
    return valor if valor not in (None, "") else default


def model_imagen_por_defecto() -> str:
    return env_o("NANO_BANANA_MODEL", "gemini-3.1-flash-image-preview") or \
        "gemini-3.1-flash-image-preview"


def voz_por_defecto() -> str:
    return env_o("EDGE_TTS_VOZ", "es-ES-ElviraNeural") or "es-ES-ElviraNeural"


def whisper_por_defecto() -> str:
    return env_o("WHISPER_MODEL", "small") or "small"

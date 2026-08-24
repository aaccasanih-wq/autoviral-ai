"""Carga el archivo ``.env`` de la raíz del proyecto (si existe).

Permite que los scripts lean credenciales y configuración sin depender de variables de entorno
exportadas manualmente: `GEMINI_API_KEY`/`NANO_BANANA_MODEL` (imágenes Gemini), `QWEN_API_KEY`/
`QWEN_IMAGE_MODEL`/`QWEN_API_HOST` (imágenes Alibaba Cloud Qwen), `IMAGEN_PROVEEDOR` (proveedor
activo), `EDGE_TTS_VOZ` y `WHISPER_MODEL`.
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


PROVEEDORES_IMAGEN = ("gemini", "qwen")
DEFAULT_PROVEEDOR = "gemini"


def proveedor_imagen_por_defecto() -> str:
    """Proveedor de imágenes activo: ``gemini`` o ``qwen``.

    Se lee de ``IMAGEN_PROVEEDOR`` (o ``QWEN_API_KEY`` definida como pista de que el usuario
    quiere Qwen); por defecto ``gemini``.
    """
    val = (env_o("IMAGEN_PROVEEDOR", "") or "").strip().lower()
    if val:
        return val if val in PROVEEDORES_IMAGEN else DEFAULT_PROVEEDOR
    # Pista: si hay key de Qwen y no hay key de Gemini, elegimos Qwen.
    if env_o("QWEN_API_KEY") or env_o("DASHSCOPE_API_KEY"):
        if not env_o("GEMINI_API_KEY"):
            return "qwen"
    return DEFAULT_PROVEEDOR


def apikey_proveedor(proveedor: str) -> str | None:
    """API key del proveedor de imágenes indicado (``gemini`` o ``qwen``)."""
    if proveedor == "qwen":
        return env_o("QWEN_API_KEY") or env_o("DASHSCOPE_API_KEY")
    return env_o("GEMINI_API_KEY")


def qwen_modelo_por_defecto() -> str:
    return env_o("QWEN_IMAGE_MODEL", "qwen-image-3.0") or "qwen-image-3.0"


def qwen_api_host() -> str:
    return env_o("QWEN_API_HOST") or env_o("DASHSCOPE_API_HOST") or "dashscope.aliyuncs.com"


def qwen_rpm() -> int:
    """Máximo de peticiones por minuto al proveedor Qwen.

    Default **2** (límite del free tier de ``qwen-image-2.0``; ``qwen-image-3.0`` permite 5).
    Modificable en ``.env`` (``QWEN_RPM``) por el usuario o por el agente a pedido.
    El script espacia las peticiones para no superar este límite.
    """
    try:
        return int(env_o("QWEN_RPM", "2") or "2")
    except (TypeError, ValueError):
        return 2


def qwen_generacion_url() -> str:
    """Endpoint DashScope multimodal-generation para Qwen image models."""
    return f"https://{qwen_api_host()}/api/v1/services/aigc/multimodal-generation/generation"


def voz_por_defecto() -> str:
    return env_o("EDGE_TTS_VOZ", "es-ES-ElviraNeural") or "es-ES-ElviraNeural"


def whisper_por_defecto() -> str:
    return env_o("WHISPER_MODEL", "small") or "small"

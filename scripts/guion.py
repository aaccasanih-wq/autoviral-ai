"""Utilidades para cargar/validar el guion y manejar timestamps del pipeline AutoViral AI.

El guion de la Fase 1 se materializa en un JSON con el esquema de ``config/guion.example.json``.
Este módulo es la única fuente de verdad para interpretarlo en la Fase 2.

Convención de timestamps:
    - Internamente usamos segundos (float) para "inicio" y "fin" de escena.
    - El nombre de archivo de imagen usa ``MM_SS_descripcion.png`` (minutos y segundos enteros).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class GuionError(ValueError):
    """Error de validez de guion. El mensaje es apto para mostrar al agente/usuario."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise GuionError(msg)


def cargar_guion(path: str | Path) -> dict[str, Any]:
    """Carga y valida ``guion.json``. Lanza ``GuionError`` si el documento es inválido."""
    p = Path(path)
    if not p.is_file():
        raise GuionError(f"No se encuentra el guion en {p}. Escribelo o crealo con la Fase 1.")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GuionError(f"El archivo de guion no es JSON válido: {e}") from e

    _require(isinstance(data, dict), "El guion debe ser un objeto JSON.")
    _require(data.get("schema_version") == SCHEMA_VERSION,
             f"schema_version debe ser {SCHEMA_VERSION}.")

    params = data.get("parametros", {})
    _require(isinstance(params, dict), "Debe existir el objeto 'parametros'.")
    _require(params.get("duracion_segundos") is not None, "Falta 'parametros.duracion_segundos'.")
    _require(params.get("formato") in ("vertical", "horizontal"),
             "'parametros.formato' debe ser 'vertical' o 'horizontal'.")
    _require(not params.get("idioma") or isinstance(params["idioma"], str),
             "'parametros.idioma' debe ser un string.")

    escenas = data.get("escenas", [])
    _require(isinstance(escenas, list) and escenas, "Debe existir al menos una escena.")

    prev_fin = 0.0
    for idx, esc in enumerate(escenas):
        _require(isinstance(esc, dict), f"La escena {idx} no es un objeto.")
        _require(esc.get("narracion") and str(esc["narracion"]).strip(),
                 f"La escena {idx} no tiene 'narracion'.")
        _require(esc.get("prompt_imagen") and str(esc["prompt_imagen"]).strip(),
                 f"La escena {idx} no tiene 'prompt_imagen'.")
        ini = esc.get("inicio_segundos", 0)
        fin = esc.get("fin_segundos", ini)
        _require(isinstance(ini, (int, float)) and isinstance(fin, (int, float)),
                 f"La escena {idx} debe tener 'inicio_segundos' y 'fin_segundos' numéricos.")
        _require(fin >= ini, f"La escena {idx} tiene fin < inicio.")
        # Los timestamps estimados deberían ser contiguos; lo relajamos a solo una advertencia
        # para tolerar ajustes manuales, pero aseguramos un orden monotónico.
        _require(ini >= prev_fin - 0.01, f"La escena {idx} se solapa con la anterior.")
        prev_fin = max(prev_fin, fin)
        esc.setdefault("id", f"escena-{idx + 1:02d}")
    return data


def escenas(guion: dict[str, Any]) -> list[dict[str, Any]]:
    """Lista de escenas del guion, en orden."""
    return guion["escenas"]


def formato(guion: dict[str, Any]) -> str:
    return guion["parametros"]["formato"]


def duracion_objetivo(guion: dict[str, Any]) -> float:
    return float(guion["parametros"]["duracion_segundos"])


def mmss(segundos: float | int) -> str:
    """Formatea segundos como ``MM:SS`` (minutos sin acotar, segundos con dos dígitos)."""
    s = int(round(segundos))
    mm = s // 60
    ss = s % 60
    return f"{mm:02d}:{ss:02d}"


def mm_ss(segundos: float | int) -> str:
    """Formatea segundos como ``MM_SS`` (para el prefijo de los nombres de imagen)."""
    s = int(round(segundos))
    return f"{s // 60:02d}_{s % 60:02d}"


def ms_timestamp(segundos: float) -> str:
    """SRT timestamp: ``HH:MM:SS,mmm``."""
    ms = int(round(segundos * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, mm = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{mm:03d}"


def slug(texto: str, max_len: int = 40) -> str:
    """Convierte un prompt en una slug corta y segura para nombre de archivo."""
    import re

    s = re.sub(r"[^a-z0-9]+", "-", texto.lower().strip())
    s = s.strip("-") or "escena"
    return s[:max_len].rstrip("-")


def nombre_imagen(esc: dict[str, Any], prompt: str | None = None) -> str:
    """Nombre canónico de imagen: ``{MM_SS}_{slug}.png``."""
    prompt = prompt or esc.get("prompt_imagen", "")
    return f"{mm_ss(esc.get('inicio_segundos', 0))}_{slug(prompt)}.png"


def guardar_json(data: Any, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

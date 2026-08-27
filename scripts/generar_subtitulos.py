"""Genera subtítulos ASS palabra-a-palabra estilo TikTok para el pipeline AutoViral AI.

Lee ``palabras.json`` (word timestamps de faster-whisper) + ``guion.json`` y genera
un ``.ass`` con:

* Estilo por defecto **WWord** : amarillo (#FFFF00) / borde negro grueso, negrita,
  centrado abajo (Alignment 2), una palabra por evento → efecto karaoke TikTok
  (``no`` → ``corporations`` → ``borrow`` → ... como en las capturas del usuario).
* Estilo **TopHook** : rojo brillante (#FF2B2B) / borde blanco, mayúsculas, centrado
  arriba (Alignment 8), visible solo los primeros ~3 s → hook llamativo copiado
  de la primera frase de la narración.

El CSS es configurable sin código: vía ``parametros.subtitulos`` en el ``guion.json``
o flags CLI (color, posición, tamaño, hook). El pipeline **quema los subtítulos
por defecto** (ver ``ensamblar_video.py``); el ``.ass`` también queda como sidecar
para reproductores.

Uso:
    python scripts/generar_subtitulos.py --guion workspace/24-08-26/mi-video/guion.json
    python scripts/generar_subtitulos.py --guion sesion/guion.json --color blanco --no-hook
    python scripts/generar_subtitulos.py --guion sesion/guion.json --hook "WHY BANKS CREATE MONEY?" --color amarillo

Parámetro en guion.json (opcional, Fase 1 puede fijarlo):
    \"parametros\": {
      \"subtitulos\": {
        \"enabled\": true,               // false = no generar ni quemar
        \"color\": \"amarillo\",           // amarillo | blanco | verde | rojo | #RRGGBB
        \"font\": \"Arial Black\",         // familia (debe existir en el sistema)
        \"fontSize\": 72,                  // pt para 1080x1920 (WWord inferior, default aumentado de 64→72)
        \"hookFontSize\": 80,              // pt para TopHook superior (default 80, antes 72 fijo)
        \"outline\": 5,                    // grosor borde negro
        \"hook\": \"WHO REALLY RUNS...\",  // texto superior; null = auto de la narración; \"\" = desactivar
        \"hookColor\": \"rojo\",            // rojo | blanco | amarillo
        \"hookDuration\": 3.0               // segundos visible el hook
      }
    }
Prioridad: flags CLI > parametros.subtitulos del guion > default.
Si el usuario aporta una captura de referencia de subtítulos, ajusta estos valores a mano
o pide al agente que los traduzca a estilo.

Referencia visual del usuario (capturas TikTok How-Money-Works):
  - Abajo: palabra única, blanca/amarilla, negra con borde grueso, centrada.
  - Arriba: pregunta en rojo, borde blanco, grande, solo al inicio.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from guion import cargar_guion, directorio_sesion
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from guion import cargar_guion, directorio_sesion  # type: ignore

# Colores nombre -> hex RRGGBB
COLOR_MAP = {
    "amarillo": "FFFF00",
    "amarillo_claro": "FFFF99",
    "blanco": "FFFFFF",
    "rojo": "FF2B2B",
    "rojo_brillante": "FF0000",
    "verde": "00FF7F",
    "azul": "00BFFF",
    "naranja": "FF8C00",
    "rosa": "FF69B4",
}

def _normalizar_color(c: str) -> str:
    c = (c or "").strip().lower()
    if not c:
        return "FFFF00"
    if c in COLOR_MAP:
        return COLOR_MAP[c]
    # hex con o sin #
    m = re.match(r"#?([0-9a-f]{6})", c, re.I)
    if m:
        return m.group(1).upper()
    return "FFFF00"

def _hex_a_ass_bgr(hex6: str) -> str:
    """RRGGBB -> ASS &H00BBGGRR (ABGR little-endian). Alpha 00 = opaco."""
    r = hex6[0:2]
    g = hex6[2:4]
    b = hex6[4:6]
    return f"&H00{b}{g}{r}"

def _ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _resolver_config(args, guion) -> dict:
    params = (guion.get("parametros") or {}).get("subtitulos") or {}
    if not isinstance(params, dict):
        params = {}
    # enabled: CLI --no-subtitulos lo desactiva; si no, guion o default True
    enabled = True
    if args.no_subtitulos:
        enabled = False
    elif "enabled" in params:
        enabled = bool(params["enabled"])
    # color
    color_cli = getattr(args, "color", None)
    color = _normalizar_color(color_cli if color_cli else params.get("color") or "amarillo")
    hook_color_cli = getattr(args, "hook_color", None)
    hook_color = _normalizar_color(hook_color_cli if hook_color_cli else params.get("hookColor") or params.get("hook_color") or "rojo")
    # font / sizes
    font = (args.font or params.get("font") or "Arial Black").strip()
    try:
        fontSize = int(args.font_size or params.get("fontSize") or 72)
    except Exception:
        fontSize = 72
    try:
        hookFontSize = int(getattr(args, "hook_font_size", None) or params.get("hookFontSize") or params.get("hook_font_size") or (fontSize + 8))
    except Exception:
        hookFontSize = fontSize + 8
    # clamp a rango razonable para 1080p vertical
    fontSize = max(40, min(110, fontSize))
    hookFontSize = max(40, min(120, hookFontSize))
    try:
        outline = int(args.outline or params.get("outline") or 5)
    except Exception:
        outline = 5
    # hook text y duración
    hook_cli = getattr(args, "hook", None)
    if hook_cli is not None:
        # CLI presente: string vacío = desactivar; None = no pasado
        hook_text = hook_cli
    else:
        hook_text = params.get("hook") if "hook" in params else None
    try:
        hook_dur = float(args.hook_duration or params.get("hookDuration") or params.get("hook_duration") or 3.0)
    except Exception:
        hook_dur = 3.0
    # Si hook_text es None => auto de la narración; si es "" => desactivado
    return {
        "enabled": enabled,
        "color": color,
        "hookColor": hook_color,
        "font": font,
        "fontSize": fontSize,
        "hookFontSize": hookFontSize,
        "outline": outline,
        "hook": hook_text,
        "hookDuration": max(0.0, min(5.0, hook_dur)),
    }

def _hook_automatico(guion, max_len: int = 48) -> str:
    """Copia la primera frase de la narración para el hook superior (como pide el usuario)."""
    try:
        escenas = guion.get("escenas") or []
        if not escenas:
            return ""
        txt = str(escenas[0].get("narracion") or "").strip()
        # Primera frase (hasta . ! ?)
        m = re.split(r"[.!?]\s", txt, maxsplit=1)
        cand = (m[0] if m else txt).strip()
        # Limpiar comillas y truncar
        cand = cand.strip('"“”\'')
        if len(cand) > max_len:
            cand = cand[:max_len].rsplit(" ", 1)[0] + "…"
        # Mayúsculas como en la captura roja
        cand = cand.upper()
        # Si empieza con THIS IS THE BIGGEST... lo hace más gancho: WHO REALLY... style
        # No inventamos, usamos literal si es corto; si es muy largo lo dejamos igual
        return cand
    except Exception:
        return ""

# Plantilla ASS — PlayRes para vertical 1080x1920 (coordenadas = píxeles)
# Placeholders con llaves dobles para evitar colisión con format: se reemplaza vía str.replace
ASS_HEADER_TEMPLATE = """[Script Info]
Title: AutoViral AI - Word-by-Word Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1080
PlayResY: 1920
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: WWord,__FONT__,__FONTSIZE__,__PRIMARY__,__BACK__,__OUTLINE__,__BACK2__,-1,0,0,0,100,100,0,0,1,__OUTLINE_W__,2,2,10,10,280,1
Style: TopHook,__FONT__,__HOOK_FONTSIZE__,__HOOK_PRIMARY__,__BACK__,__HOOK_OUTLINE__,__BACK2__,-1,0,0,0,100,100,0,0,1,6,3,8,10,10,140,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def generar_ass(palabras: list[dict], frases: list[dict], guion: dict, cfg: dict, out: Path) -> int:
    if not cfg.get("enabled", True):
        print("[subtitulos] Desactivados (enabled=false). No se genera ASS.", flush=True)
        return 0
    if not palabras:
        # Fallback a frases si no hay palabras
        if frases:
            # Convertir frases en palabras con duración proporcional como fallback
            tmp = []
            for fr in frases:
                toks = str(fr.get("text") or "").split()
                dur = max(0.3, float(fr.get("end", 0)) - float(fr.get("start", 0)))
                per = dur / max(1, len(toks))
                for i, tok in enumerate(toks):
                    tmp.append({"start": float(fr["start"]) + i * per, "end": float(fr["start"]) + (i+1)*per, "word": tok})
            palabras = tmp
        else:
            print("[subtitulos] Sin palabras ni frases; no se genera ASS.", flush=True)
            return 0

    # Filtrar palabras vacías y ordenar
    palabras = [p for p in palabras if str(p.get("word") or "").strip()]
    palabras.sort(key=lambda x: float(x["start"]))

    primary = _hex_a_ass_bgr(cfg["color"])
    hook_primary = _hex_a_ass_bgr(cfg["hookColor"])
    # Outline negro para palabras, blanco para hook rojo (como en capturas)
    outline = "&H00000000"  # negro
    hook_outline = "&H00FFFFFF"  # blanco
    back = "&H64000000"  # semi transparente
    font = cfg["font"]
    outline_w = cfg["outline"]

    # Hook automático si no se pasó
    hook_raw = cfg.get("hook")
    if hook_raw is None:
        hook_text = _hook_automatico(guion)
    else:
        hook_text = str(hook_raw).strip()
    # hook desactivado si string vacío
    hook_enabled = bool(hook_text)
    hook_dur = float(cfg.get("hookDuration", 3.0))
    # Primera palabra start para alinear hook
    first_start = float(palabras[0]["start"]) if palabras else 0.0

    # Reemplazo en orden largo->corto para evitar colisión de substrings (ej. OUTLINE dentro de HOOK_OUTLINE)
    ass = ASS_HEADER_TEMPLATE.replace("__FONT__", font) \
        .replace("__FONTSIZE__", str(cfg.get("fontSize", 72))) \
        .replace("__HOOK_FONTSIZE__", str(cfg.get("hookFontSize", 80))) \
        .replace("__HOOK_PRIMARY__", hook_primary) \
        .replace("__HOOK_OUTLINE__", hook_outline) \
        .replace("__PRIMARY__", primary) \
        .replace("__OUTLINE__", outline) \
        .replace("__BACK2__", back) \
        .replace("__BACK__", back) \
        .replace("__OUTLINE_W__", str(outline_w))

    lineas = []
    # Hook superior (una sola línea, 0 -> hook_dur)
    if hook_enabled and hook_dur > 0:
        # Escapar texto ASS: \ es escape, { necesita \}
        safe_hook = hook_text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        lineas.append(f"Dialogue: 0,{_ass_time(first_start)},{_ass_time(first_start + hook_dur)},TopHook,,0,0,0,,{safe_hook}")

    # Palabras una a una (karaoke TikTok) — cada palabra es un evento independiente
    # Como en las capturas: la misma imagen permanece pero el texto cambia cada palabra.
    for i, pw in enumerate(palabras):
        s = float(pw["start"])
        # Fin = inicio de la siguiente palabra o el end propio, lo que sea menor, con mínimo 0.18s visible
        if i + 1 < len(palabras):
            nxt = float(palabras[i+1]["start"])
            e = min(float(pw["end"]), nxt)
            # Si el gap es muy pequeño, extiende un poco para legibilidad, pero sin solapar
            if e - s < 0.18:
                e = min(nxt, s + 0.28)
        else:
            e = float(pw["end"])
            if e - s < 0.18:
                e = s + 0.35
        # Texto: limpiar y escapar
        raw = str(pw["word"]).strip()
        # Quitar puntuación pegada al inicio/final para mejor lectura, pero mantener ?
        safe = raw.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        # Asegurar que no esté vacío después de limpiar
        if not safe:
            continue
        lineas.append(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},WWord,,0,0,0,,{safe}")

    ass += "\n".join(lineas) + "\n"
    out.write_text(ass, encoding="utf-8")
    print(f"[subtitulos] ASS generado -> {out} ({len(lineas)} eventos, {len(palabras)} palabras, hook={'sí' if hook_enabled else 'no'})")
    return len(lineas)

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generar ASS palabra-a-palabra estilo TikTok (amarillo abajo + hook rojo arriba).")
    ap.add_argument("--guion", default="workspace/guion.json", help="Ruta al guion.json")
    ap.add_argument("--palabras", default=None, help="Ruta a palabras.json (default <sesion>/transcripcion/palabras.json)")
    ap.add_argument("--frases", default=None, help="Ruta a narracion.json (fallback)")
    ap.add_argument("--out", default=None, help="Salida .ass (default <sesion>/transcripcion/narracion.ass)")
    ap.add_argument("--no-subtitulos", action="store_true", help="Desactivar generación (enabled=false)")
    ap.add_argument("--color", default=None, help="Color inferior: amarillo, blanco, verde, rojo o #RRGGBB (default amarillo)")
    ap.add_argument("--hook", default=None, help="Texto hook superior; usa '' para desactivar; si no se pasa se toma de la narración")
    ap.add_argument("--hook-color", dest="hook_color", default=None, help="Color hook: rojo, blanco, etc.")
    ap.add_argument("--hook-duration", dest="hook_duration", type=float, default=None, help="Duración hook superior en seg (default 3.0)")
    ap.add_argument("--font", default=None, help="Familia tipográfica (default Arial Black)")
    ap.add_argument("--font-size", dest="font_size", type=int, default=None, help="Tamaño fuente inferior (default 72, antes 64)")
    ap.add_argument("--hook-font-size", dest="hook_font_size", type=int, default=None, help="Tamaño fuente hook superior (default 80, antes 72 fijo; si no se pasa = fontSize+8)")
    ap.add_argument("--outline", type=int, default=None, help="Grosor borde (default 5)")
    args = ap.parse_args(argv)

    try:
        guion = cargar_guion(args.guion)
    except Exception as e:
        print(f"[subtitulos] Error cargando guion: {e}", flush=True)
        return 1
    sd = directorio_sesion(args.guion)
    palabras_path = Path(args.palabras) if args.palabras else sd / "transcripcion" / "palabras.json"
    frases_path = Path(args.frases) if args.frases else sd / "transcripcion" / "narracion.json"
    out = Path(args.out) if args.out else sd / "transcripcion" / "narracion.ass"

    palabras = []
    if palabras_path.is_file():
        try:
            palabras = json.loads(palabras_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[subtitulos] Aviso: no se pudo leer {palabras_path}: {e}", flush=True)
    frases = []
    if frases_path.is_file():
        try:
            frases = json.loads(frases_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    cfg = _resolver_config(args, guion)
    # Permitir que el guion desactive subtítulos por completo
    if not cfg.get("enabled", True):
        print("[subtitulos] Subtítulos desactivados por guion/flag. No se genera archivo.")
        return 0
    # Si no hay palabras, intenta transcribir con fallback frase->palabras dentro de generar_ass
    if not palabras and not frases:
        print(f"[subtitulos] No hay {palabras_path.name} ni {frases_path.name}. Ejecuta primero transcribir.py --word-timestamps.", flush=True)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    n = generar_ass(palabras, frases, guion, cfg, out)
    return 0 if n > 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())

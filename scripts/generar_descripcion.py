"""Genera descripcion.txt para TikTok (descripción corta + 5 hashtags virales).

Lee guion.json (título, descripción, nicho, primera narración) y crea
<sesion>/descripcion.txt  y <sesion>/transcripcion/descripcion.txt con:

- Línea 1-2: descripción corta, llamativa, con gancho (no necesariamente
  idéntica a la primera frase, pero basada en ella). Máx 150 caracteres,
  con emoji opcional, optimizada para TikTok SEO y retención.
- Línea 3: bloque con 5 hashtags cortos, virales, en inglés, relacionados.

Uso:
    python scripts/generar_descripcion.py --guion workspace/24-08-26/mi-video/guion.json
    python scripts/generar_descripcion.py --guion sesion/guion.json --dry-run

En guion.json puedes fijar manualmente:
    "parametros": {
      "descripcion_tiktok": "Tu descripción custom",
      "hashtags": ["#money", "#finance", "#investing", "#economy", "#wealth"]
    }
Si existen, se usan tal cual (prioridad a lo manual). Si no, se autogenera.

Heurística de hashtags por nicho (máx 5, cortos):
- finanzas: #money #finance #investing #wealth #economy #banking #stocks #crypto
- tech: #tech #ai #technology #gadgets #future
etc. Elige los 5 más relevantes por keywords del título.

Salida también copiada a transcripcion/ para compatibilidad con pipeline.
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

# Pools virales por nicho (cortos, máx 15 chars, sin frases largas)
HASHTAG_POOLS = {
    "finanzas": ["#money", "#finance", "#investing", "#wealth", "#economy", "#banking", "#stocks", "#crypto", "#inflation", "#personalfinance", "#financialfreedom", "#moneytok"],
    "tech": ["#tech", "#ai", "#technology", "#gadgets", "#future", "#innovation", "#coding", "#startup"],
    "salud_bienestar": ["#health", "#wellness", "#fitness", "#selfcare", "#healthy", "#mindset"],
    "misterio": ["#mystery", "#truecrime", "#creepy", "#unsolved", "#viral", "#storytime"],
    "motivacion": ["#motivation", "#mindset", "#success", "#discipline", "#growth"],
    "educacion": ["#learn", "#facts", "#didyouknow", "#education", "#viral", "#curiosity"],
    "default": ["#viral", "#fyp", "#foryou", "#trending", "#didyouknow", "#facts"],
}

# Keywords para scoring de hashtags dentro de finanzas
FINANZAS_KEYWORDS = {
    "#money": ["money", "cash", "dollar", "wealth"],
    "#finance": ["finance", "financial", "money"],
    "#investing": ["invest", "stock", "portfolio", "wealth"],
    "#banking": ["bank", "banking", "banker"],
    "#economy": ["economy", "economic", "market", "inflation"],
    "#stocks": ["stock", "stocks", "market", "invest"],
    "#crypto": ["crypto", "bitcoin", "btc", "eth"],
    "#inflation": ["inflation", "price", "expensive", "printer"],
    "#wealth": ["wealth", "rich", "million"],
    "#personalfinance": ["personal", "saving", "budget"],
}

def _normalizar_nicho(nicho: str) -> str:
    n = (nicho or "").strip().lower().replace(" ", "_")
    if n in HASHTAG_POOLS:
        return n
    if "finan" in n:
        return "finanzas"
    if "tech" in n or "ia" in n:
        return "tech"
    if "mister" in n:
        return "misterio"
    return "default"

def _elegir_hashtags(guion: dict, nicho_norm: str, max_n: int = 5) -> list[str]:
    titulo = (guion.get("titulo") or "").lower()
    descr = (guion.get("descripcion") or "").lower()
    texto = f"{titulo} {descr}"
    pool = HASHTAG_POOLS.get(nicho_norm, HASHTAG_POOLS["default"])

    # Si es finanzas, score por keywords, si no, toma top del pool
    if nicho_norm == "finanzas":
        scored = []
        for tag in pool:
            kws = FINANZAS_KEYWORDS.get(tag, [])
            score = sum(1 for kw in kws if kw in texto)
            # Bonus para siempre relevantes
            if tag in ("#money", "#finance", "#viral"):
                score += 0.5
            scored.append((score, tag))
        scored.sort(key=lambda x: (-x[0], pool.index(x[1])))
        # Asegura variedad: toma top con score>0 + rellena con virales
        top = [tag for s, tag in scored if s > 0][:max_n]
        # Rellena si faltan
        for _, tag in scored:
            if len(top) >= max_n:
                break
            if tag not in top:
                top.append(tag)
        return top[:max_n]
    else:
        return pool[:max_n]

def _generar_descripcion(guion: dict) -> str:
    # Si el usuario fijó descripcion_tiktok manual, úsala
    params = guion.get("parametros") or {}
    if isinstance(params, dict) and params.get("descripcion_tiktok"):
        return str(params["descripcion_tiktok"]).strip()
    titulo = (guion.get("titulo") or "").strip()
    descripcion = (guion.get("descripcion") or "").strip()
    escenas = guion.get("escenas") or []
    primera = ""
    if escenas:
        primera = str(escenas[0].get("narracion") or "").strip()
    # Primera frase como gancho
    gancho = primera.split(".")[0].strip() if primera else titulo
    # Limpia y recorta a 110-140 chars ideal para TikTok
    gancho = re.sub(r"\s+", " ", gancho).strip()
    # Quita comillas
    gancho = gancho.strip('"“”\'')
    # Si es muy corto (<30), usa título
    if len(gancho) < 30 and titulo:
        gancho = titulo.strip()
    # Si es muy largo (>130), recorta
    if len(gancho) > 130:
        gancho = gancho[:127].rsplit(" ", 1)[0] + "…"
    # Añade emoji relevante según nicho
    nicho = _normalizar_nicho(params.get("nicho") if isinstance(params, dict) else "")
    emoji = {"finanzas": "💰", "tech": "🚀", "misterio": "😱", "educacion": "🧠"}.get(nicho, "⚡")
    # No duplicar si ya tiene emoji
    if not any(e in gancho for e in ["💰", "🚀", "😱", "🧠", "⚡", "🔥", "💸"]):
        gancho = f"{gancho} {emoji}"
    # Opcional segunda línea corta CTA (solo si no supera 150)
    cta = ""
    idioma = params.get("idioma") if isinstance(params, dict) else "en"
    if idioma == "en":
        cta = "You need to know this."
    else:
        cta = "Tienes que saber esto."
    # Si gancho + cta < 150, añade CTA
    if len(gancho) + 1 + len(cta) < 150:
        # Evita repetir si el gancho ya termina con punto
        if not gancho.endswith("."):
            gancho = f"{gancho} • {cta}"
        else:
            gancho = f"{gancho} {cta}"
    return gancho

def generar(guion_path: Path, dry_run: bool = False) -> tuple[str, list[str], Path]:
    guion = cargar_guion(str(guion_path))
    sd = directorio_sesion(str(guion_path))

    params = guion.get("parametros") or {}
    # Hashtags manuales si existen
    hashtags_manual = None
    if isinstance(params, dict) and isinstance(params.get("hashtags"), list):
        hashtags_manual = [str(h).strip() for h in params["hashtags"] if str(h).strip()]
        # Normaliza con #
        hashtags_manual = [h if h.startswith("#") else f"#{h}" for h in hashtags_manual][:5]
    descripcion = _generar_descripcion(guion)
    nicho_norm = _normalizar_nicho(params.get("nicho") if isinstance(params, dict) else "")
    hashtags = hashtags_manual if hashtags_manual else _elegir_hashtags(guion, nicho_norm, 5)

    # Construir contenido TXT
    # Línea 1-2: descripción, línea vacía, línea 3: hashtags separados por espacio
    hashtags_line = " ".join(hashtags)
    contenido = f"{descripcion}\n\n{hashtags_line}\n"

    out = sd / "descripcion.txt"
    out2 = sd / "transcripcion" / "descripcion.txt"

    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(contenido, encoding="utf-8")
        out2.parent.mkdir(parents=True, exist_ok=True)
        out2.write_text(contenido, encoding="utf-8")
        print(f"[descripcion] -> {out}")
        print(f"[descripcion] -> {out2}")
    else:
        print(f"[descripcion] (dry-run) -> {out}:\n{contenido}")

    return descripcion, hashtags, out

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generar descripcion.txt para TikTok (gancho + 5 hashtags).")
    ap.add_argument("--guion", default="workspace/guion.json", help="Ruta al guion.json")
    ap.add_argument("--out", default=None, help="Ruta salida TXT (default <sesion>/descripcion.txt)")
    ap.add_argument("--dry-run", action="store_true", help="Solo mostrar, no escribir")
    args = ap.parse_args(argv)

    guion_path = Path(args.guion)
    if not guion_path.is_file():
        print(f"[descripcion] No existe el guion: {guion_path}", flush=True)
        return 2

    descripcion, hashtags, out = generar(guion_path, dry_run=args.dry_run)

    if args.out:
        Path(args.out).write_text(f"{descripcion}\n\n{' '.join(hashtags)}\n", encoding="utf-8")
        print(f"[descripcion] -> {args.out}")

    # Respuesta concisa para el agente
    print(f"[descripcion] OK: \"{descripcion}\" | {' '.join(hashtags)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

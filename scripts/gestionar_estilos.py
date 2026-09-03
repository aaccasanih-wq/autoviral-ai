"""Gestión del catálogo de estilos de animación + voz (AutoViral AI).

Cada estilo vive en ``estilos/<id>/`` con ``estilo.json`` + ``tts.json`` +
``referencias/``. El agente NUNCA hardcodea estilos: los descubre con este script
o leyendo ``estilos/catalogo.json`` (funciona igual en macOS/Linux/Windows).

Uso:
    python scripts/gestionar_estilos.py --listar
    python scripts/gestionar_estilos.py --mostrar tom-jerry
    python scripts/gestionar_estilos.py --validar
    python scripts/gestionar_estilos.py --crear --id mi-estilo --nombre "Mi estilo" \\
        --descripcion "..." --referencia /ruta/a/ref.png --voz-descripcion "narrador..."
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ESTILOS_DIR = RAIZ / "estilos"
CATALOGO = ESTILOS_DIR / "catalogo.json"


def _cargar_catalogo() -> dict:
    if not CATALOGO.is_file():
        raise SystemExit(f"No existe {CATALOGO}. Crea estilos/ primero.")
    return json.loads(CATALOGO.read_text(encoding="utf-8"))


def _cargar_estilo(estilo_id: str) -> tuple[dict, dict, dict]:
    cat = _cargar_catalogo()
    entry = next((e for e in cat.get("estilos", []) if e["id"] == estilo_id), None)
    if not entry:
        raise SystemExit(f"Estilo '{estilo_id}' no está en catalogo.json. Usa --listar.")
    estilo_path = RAIZ / entry["estilo_json"]
    tts_path = RAIZ / entry["tts_json"]
    estilo = json.loads(estilo_path.read_text(encoding="utf-8"))
    tts = json.loads(tts_path.read_text(encoding="utf-8"))
    return entry, estilo, tts


def cmd_listar() -> int:
    cat = _cargar_catalogo()
    print(f"Catálogo v{cat.get('version', 1)} | default_tts_motor={cat.get('default_tts_motor', 'gcp')}")
    for e in cat.get("estilos", []):
        print(f"- {e['id']}: {e.get('nombre', '')} — {e.get('descripcion', '')}")
        print(f"  carpeta: {e.get('carpeta', '')}")
    return 0


def cmd_mostrar(estilo_id: str) -> int:
    entry, estilo, tts = _cargar_estilo(estilo_id)
    print(f"=== {entry['id']} — {entry.get('nombre', '')} ===")
    print(f"Descripción: {entry.get('descripcion', '')}")
    print(f"\n[CHARACTER]\n{estilo.get('character_ficha', '')}")
    print(f"\n[STYLE]\n{estilo.get('style_ficha', '')}")
    print(f"\n[ANTI-DRIFT]\n{estilo.get('anti_drift', '')}")
    print(f"\n[REFERENCIAS]\n" + "\n".join(f"  - {r}" for r in estilo.get("referencias", [])))
    print(f"\n[TTS default {tts.get('motor', 'gcp')}] voz_en={tts.get('voz_en')} voz_es={tts.get('voz_es')} "
          f"rate={tts.get('rate')} pitch={tts.get('pitch')}")
    print(f"  estilo: {tts.get('estilo_narracion', '')}")
    print(f"  fallback edge: {tts.get('edge_fallback_en')}/{tts.get('edge_fallback_es')}")
    print(f"\n[TEMPLATE]\n{estilo.get('prompt_template', '')}")
    return 0


def cmd_validar() -> int:
    cat = _cargar_catalogo()
    errores: list[str] = []
    ids = [e["id"] for e in cat.get("estilos", [])]
    if len(ids) != len(set(ids)):
        errores.append("IDs duplicados en catalogo.json")
    for e in cat.get("estilos", []):
        sid = e.get("id", "?")
        for key in ("estilo_json", "tts_json"):
            p = RAIZ / e.get(key, "")
            if not p.is_file():
                errores.append(f"{sid}: falta {key} -> {p}")
        estilo_path = RAIZ / e.get("estilo_json", "")
        if estilo_path.is_file():
            estilo = json.loads(estilo_path.read_text(encoding="utf-8"))
            for req in ("character_ficha", "style_ficha", "anti_drift", "referencias"):
                if not estilo.get(req):
                    errores.append(f"{sid}: estilo.json sin '{req}'")
            for r in estilo.get("referencias", []):
                if not (RAIZ / r).is_file():
                    errores.append(f"{sid}: referencia no encontrada -> {r}")
    if errores:
        print("[estilos] ERRORES:")
        for er in errores:
            print(f"  - {er}")
        return 1
    print(f"[estilos] OK: {len(ids)} estilos válidos ({', '.join(ids)})")
    return 0


def cmd_crear(args) -> int:
    estilo_id = args.id.strip().lower().replace(" ", "-")
    carpeta = ESTILOS_DIR / estilo_id
    if carpeta.exists() and not args.overwrite:
        print(f"[estilos] Ya existe {carpeta}. Usa --overwrite para recrear.", file=sys.stderr)
        return 1
    (carpeta / "referencias").mkdir(parents=True, exist_ok=True)
    # Copiar referencias aportadas
    refs_dest: list[str] = []
    for ref in (args.referencia or []):
        src = Path(ref)
        if not src.is_file():
            print(f"[estilos] AVISO: referencia no encontrada, se omite: {ref}", file=sys.stderr)
            continue
        dst = carpeta / "referencias" / src.name
        shutil.copy(src, dst)
        refs_dest.append(f"estilos/{estilo_id}/referencias/{src.name}")
    # Si no hay referencias, avisar (el estilo quedará incompleto hasta añadirlas)
    if not refs_dest:
        print("[estilos] AVISO: sin referencias. Añade imágenes a referencias/ y actualiza estilo.json.",
              file=sys.stderr)
    estilo = {
        "id": estilo_id,
        "nombre": args.nombre or estilo_id,
        "descripcion": args.descripcion or "",
        "character_ficha": args.character or "CHARACTER: (completar: protagonista fijo, ropa, colores hex, sin zapatos/gorra salvo que sea parte del personaje)",
        "style_ficha": args.style or "STYLE: (completar: técnica, trazo, fondo hex, sin fotorealismo/3D, vertical 9:16)",
        "fondo": args.fondo or "",
        "paleta": [],
        "trazo": "",
        "anti_drift": "Keep the SAME protagonist identical in EVERY scene: same clothes, colors, proportions. Do NOT change outfit, add shoes/hats/glasses, or switch to photorealistic/3D. Keep background identical.",
        "negativos": ["photorealistic", "3D", "cambiar ropa", "zapatos", "gorra"],
        "personajes_secundarios": "Declarar color fijo por secundario, nunca el del protagonista.",
        "referencias": refs_dest,
        "prompt_template": "{character_ficha} {style_ficha} {accion}. {anti_drift}",
        "seed_policy": "misma seed por video, prompt_extend=false",
        "version": 1,
    }
    tts = {
        "motor": "gcp",
        "voz_en": "en-US-Neural2-F",
        "voz_es": "es-ES-Neural2-F",
        "edge_fallback_en": "en-US-AriaNeural",
        "edge_fallback_es": "es-ES-ElviraNeural",
        "rate": "+0%",
        "pitch": "0",
        "estilo_narracion": args.voz_descripcion or "(sugerir según estilo visual si el usuario no dio muestra/descripción)",
        "expresividad": "",
        "notas": "Default gcp. Fallback edge si no hay API key.",
    }
    (carpeta / "estilo.json").write_text(json.dumps(estilo, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "tts.json").write_text(json.dumps(tts, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.voz_descripcion:
        (carpeta / "descripcion-voz.txt").write_text(args.voz_descripcion, encoding="utf-8")
    # Registrar en catalogo.json
    cat = _cargar_catalogo()
    cat["estilos"] = [e for e in cat.get("estilos", []) if e["id"] != estilo_id]
    cat["estilos"].append({
        "id": estilo_id,
        "nombre": estilo["nombre"],
        "descripcion": estilo["descripcion"],
        "carpeta": f"estilos/{estilo_id}",
        "estilo_json": f"estilos/{estilo_id}/estilo.json",
        "tts_json": f"estilos/{estilo_id}/tts.json",
    })
    CATALOGO.write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[estilos] Creado {estilo_id} -> {carpeta}")
    print("[estilos] Completa character_ficha/style_ficha y corre --validar.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gestionar catálogo de estilos de animación + voz.")
    ap.add_argument("--listar", action="store_true", help="Listar estilos del catálogo.")
    ap.add_argument("--mostrar", default=None, help="Mostrar detalle de un estilo (id).")
    ap.add_argument("--validar", action="store_true", help="Validar catálogo y referencias.")
    ap.add_argument("--crear", action="store_true", help="Crear esqueleto de estilo nuevo.")
    ap.add_argument("--id", default=None, help="ID del estilo a crear (slug).")
    ap.add_argument("--nombre", default=None, help="Nombre legible del estilo.")
    ap.add_argument("--descripcion", default=None, help="Descripción corta del estilo.")
    ap.add_argument("--referencia", action="append", default=None, help="Imagen de referencia (repetible).")
    ap.add_argument("--voz-descripcion", default=None, help="Descripción del estilo de voz.")
    ap.add_argument("--character", default=None, help="Ficha CHARACTER verbatim.")
    ap.add_argument("--style", default=None, help="Ficha STYLE verbatim.")
    ap.add_argument("--fondo", default=None, help="Fondo (ej. #FFFFFF blanco puro).")
    ap.add_argument("--overwrite", action="store_true", help="Sobrescribir si existe.")
    args = ap.parse_args(argv)
    if args.listar:
        return cmd_listar()
    if args.mostrar:
        return cmd_mostrar(args.mostrar)
    if args.validar:
        return cmd_validar()
    if args.crear:
        if not args.id:
            print("[estilos] --crear requiere --id", file=sys.stderr)
            return 2
        return cmd_crear(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

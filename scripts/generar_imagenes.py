"""Paso 4 del pipeline: generar una imagen por escena con Gemini "Nano Banana 2".

Esta es la vía CLI (Google GenAI SDK) hacia el mismo modelo que usa el servidor MCP
``nano-banana-2`` (``gemini-3.1-flash-image-preview``). Requiere ``GEMINI_API_KEY``.

Salida: ``<outdir>/MM_SS_descripcion.png`` por escena.

Uso:
    GEMINI_API_KEY=... python scripts/generar_imagenes.py --guion workspace/guion.json \
      --outdir workspace/imagenes --model gemini-3.1-flash-image-preview
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from guion import cargar_guion, escenas, guardar_json, imagen_referencia, nombre_imagen
except ImportError:  # pragma: no cover - permit run from anywhere via PYTHONPATH
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from guion import cargar_guion, escenas, guardar_json, imagen_referencia, nombre_imagen  # type: ignore

from envutil import cargar_env, model_imagen_por_defecto

cargar_env()

MODELO_DEF = model_imagen_por_defecto()  # por defecto gemini-3.1-flash-image-preview (Nano Banana 2)


def _formato_a_ratio(formato: str) -> str:
    return "9:16" if formato == "vertical" else "16:9"


def _mime_tipo(path: Path) -> str:
    """MIME a partir de la extensión de la imagen de referencia."""
    ext = path.suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}.get(ext, "image/png")


def _leer_referencia(path: str | None) -> tuple[bytes, str] | None:
    """Lee la imagen de referencia. Devuelve (bytes, mime) o ``None`` si no hay / falla."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        print(f"[imagenes] AVISO: imagen de referencia no encontrada: {p}. "
              f"Se ignora y se genera sin referencia.", file=sys.stderr)
        return None
    try:
        data = p.read_bytes()
    except OSError as e:
        print(f"[imagenes] AVISO: no se pudo leer la referencia {p}: {e}. "
              f"Se genera sin referencia.", file=sys.stderr)
        return None
    return data, _mime_tipo(p)


def _generar(client, modelo: str, prompt: str, ratio: str, out: Path,
             referencia: tuple[bytes, str] | None = None) -> bool:
    """Genera una imagen y la guarda en ``out``. Devuelve True si se escribió."""
    from google.genai import types

    config_kwargs = {"response_modalities": ["IMAGE"]}
    # El ratio es opcional y varía por versión del SDK; lo enviamos de forma tolerante.
    try:
        config_kwargs["image_config"] = types.ImageConfig(aspect_ratio=ratio)
    except Exception:
        pass

    # Si hay imagen de referencia, la enviamos como input junto con el prompt para
    # anclar el estilo animado de forma consistente en todas las escenas.
    contents: list = []
    if referencia:
        contents.append(types.Part.from_bytes(data=referencia[0], mime_type=referencia[1]))
    contents.append(prompt)

    try:
        response = client.models.generate_content(
            model=modelo,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as e:
        print(f"[imagenes] Error de Gemini en '{prompt[:40]}...': {e}", file=sys.stderr)
        return False

    img_bytes = None
    try:
        for cand in response.candidates:
            for part in cand.content.parts:
                inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
                if inline is not None and getattr(inline, "data", None):
                    img_bytes = bytes(inline.data)
                    break
                blob = getattr(part, "blob", None)
                if blob is not None and getattr(blob, "data", None):
                    img_bytes = bytes(blob.data)
                    break
            if img_bytes:
                break
    except Exception as e:
        print(f"[imagenes] No se pudo extraer la imagen: {e}", file=sys.stderr)
        return False

    if not img_bytes:
        texto = response.text or ""
        print(f"[imagenes] La respuesta no contenía una imagen para '{prompt[:40]}...'. "
              f"Texto: {texto[:120]}", file=sys.stderr)
        return False

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(img_bytes)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generar imágenes por escena (Gemini Nano Banana 2).")
    ap.add_argument("--guion", default="workspace/guion.json", help="Ruta al guion.json.")
    ap.add_argument("--outdir", default="workspace/imagenes", help="Carpeta de salida.")
    ap.add_argument("--model", default=MODELO_DEF, help="Modelo de imagen de Gemini.")
    ap.add_argument("--apikey", default=None, help="Gemini API key (o env GEMINI_API_KEY).")
    ap.add_argument("--solo", default=None, help="Solo regenerar esta escena (id).")
    ap.add_argument("--overwrite", action="store_true", help="Regenera aunque exista el archivo.")
    ap.add_argument("--aspect", default=None, help="Forzar ratio (p. ej. 9:16).")
    ap.add_argument("--referencia", default=None,
                    help="Ruta a una imagen de referencia (.png/.jpg/...) cuyo estilo animado se "
                         "usará de forma consistente en todas las escenas. Si no se pasa, se usa "
                         "parametros.imagen_referencia del guion (si existe).")
    args = ap.parse_args(argv)

    apikey = args.apikey or os.environ.get("GEMINI_API_KEY")
    if not apikey:
        print("[imagenes] Falta la API key de Gemini. Usa --apikey o la variable GEMINI_API_KEY.",
              file=sys.stderr)
        return 2

    guion = cargar_guion(args.guion)
    ratio = args.aspect or _formato_a_ratio(guion["parametros"]["formato"])
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Imagen de referencia: prioridad al argumento, luego al campo del guion.
    referencia = _leer_referencia(args.referencia or imagen_referencia(guion))
    if args.referencia or imagen_referencia(guion):
        print(f"[imagenes] Estilo anclado a imagen de referencia: "
              f"{args.referencia or imagen_referencia(guion)}")

    try:
        from google import genai
    except ImportError:
        print("[imagenes] Falta 'google-genai'. Instala con: pip install google-genai",
              file=sys.stderr)
        return 2

    client = genai.Client(api_key=apikey)

    escs = [e for e in escenas(guion) if not args.solo or e["id"] == args.solo]
    if not escs:
        print(f"[imagenes] No hay escenas que regenerar (solo={args.solo}).", file=sys.stderr)
        return 1

    ok = 0
    fallidas: list[str] = []
    for idx, esc in enumerate(escs, 1):
        out = outdir / nombre_imagen(esc)
        if out.is_file() and not args.overwrite:
            print(f"[imagenes] {idx}/{len(escs)} existe, omitido: {out.name}")
            ok += 1
            continue
        prompt = f"{esc['prompt_imagen']}. Aspect ratio {ratio}. High quality, crisp details."
        if _generar(client, args.model, prompt, ratio, out, referencia):
            print(f"[imagenes] {idx}/{len(escs)} -> {out.name}")
            ok += 1
        else:
            fallidas.append(esc["id"])
            print(f"[imagenes] {idx}/{len(escs)} FALLÓ {esc['id']}")

    guardar_json({"model": args.model, "ratio": ratio, "fallidas": fallidas}, outdir / "reporte.json")
    print(f"[imagenes] OK: {ok} generadas, {len(fallidas)} fallidas.")
    return 0 if not fallidas else 1


if __name__ == "__main__":
    raise SystemExit(main())

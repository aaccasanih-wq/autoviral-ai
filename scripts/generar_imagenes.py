"""Paso 4 del pipeline: generar una imagen por escena con el proveedor elegido.

Soporta **dos proveedores intercambiables**:

* ``gemini`` — google-genai (Nano Banana 2: ``gemini-3.1-flash-image-preview`` /
  ``gemini-2.5-flash-image``). Requiere ``GEMINI_API_KEY``.
* ``qwen`` — Alibaba Cloud DashScope (``qwen-image-3.0`` / ``qwen-image-3.0-pro``).
  Requiere ``QWEN_API_KEY`` (o ``DASHSCOPE_API_KEY``) + ``QWEN_API_HOST``.

El proveedor se elige con ``--proveedor`` o la variable de entorno ``IMAGEN_PROVEEDOR``
(ver ``envutil.py`` para las claves/modelos por defecto de cada uno).

Tras generar las imágenes se escribe además un **contact sheet**
(``<workspace>/revision/contact_sheet.png``) que reúne todas las escenas en una sola imagen.
La skill de producción lo usa para preguntar al usuario si el estilo / colores / animación /
fondos están bien. Si no están conformes, se regenera aplicando su feedback con ``--estilo``
(un ajuste global a todos los prompts) y/o ``--solo`` (regenerar solo una escena).

Salida: ``<outdir>/MM_SS_descripcion.png`` por escena.

Uso:
    # Gemini:
    GEMINI_API_KEY=... python scripts/generar_imagenes.py --guion workspace/guion.json \\
      --outdir workspace/imagenes --proveedor gemini --model gemini-3.1-flash-image-preview

    # Qwen (Alibaba DashScope):
    QWEN_API_KEY=... QWEN_API_HOST=ws-xx.maas.aliyuncs.com \\
      python scripts/generar_imagenes.py --guion workspace/guion.json \\
      --outdir workspace/imagenes --proveedor qwen --model qwen-image-3.0

    # Revisar el montaje sin regenerar:
    python scripts/generar_imagenes.py --outdir workspace/imagenes --contact-sheet
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from guion import cargar_guion, escenas, guardar_json, imagen_referencia, nombre_imagen
except ImportError:  # pragma: no cover - permit run from anywhere via PYTHONPATH
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from guion import cargar_guion, escenas, guardar_json, imagen_referencia, nombre_imagen  # type: ignore

from envutil import (apikey_proveedor, cargar_env, model_imagen_por_defecto,
                     proveedor_imagen_por_defecto, qwen_generacion_url, qwen_modelo_por_defecto)

cargar_env()

MODELO_DEF = model_imagen_por_defecto()  # por defecto gemini-3.1-flash-image-preview (Nano Banana 2)

# Tamaño de celda del contact sheet (mantiene proporción 9:16 vertical).
CS = (480, 854)


def _formato_a_ratio(formato: str) -> str:
    return "9:16" if formato == "vertical" else "16:9"


def _ratio_a_size(ratio: str) -> str:
    """Tamaño de imagen para Qwen DashScope a partir del aspect ratio."""
    return {"9:16": "768*1344", "16:9": "1344*768"}.get(ratio, "768*1344")


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


# ---------------------------------------------------------------------------
# Generador Gemini
# ---------------------------------------------------------------------------

def _generar_gemini(client, modelo: str, prompt: str, ratio: str, out: Path,
                    referencia: tuple[bytes, str] | None = None) -> bool:
    """Genera una imagen con Gemini (Nano Banana) y la guarda en ``out``."""
    from google.genai import types

    config_kwargs = {"response_modalities": ["IMAGE"]}
    # El ratio es opcional y varía por versión del SDK; lo enviamos de forma tolerante.
    try:
        config_kwargs["image_config"] = types.ImageConfig(aspect_ratio=ratio)
    except Exception:
        pass

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

    img_bytes = _extraer_payload_gemini(response)
    if not img_bytes:
        texto = response.text or ""
        print(f"[imagenes] La respuesta no contenía una imagen para '{prompt[:40]}...'. "
              f"Texto: {texto[:120]}", file=sys.stderr)
        return False

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(img_bytes)
    return True


def _extraer_payload_gemini(response) -> bytes | None:
    try:
        for cand in response.candidates:
            for part in cand.content.parts:
                inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
                if inline is not None and getattr(inline, "data", None):
                    return bytes(inline.data)
                blob = getattr(part, "blob", None)
                if blob is not None and getattr(blob, "data", None):
                    return bytes(blob.data)
    except Exception as e:
        print(f"[imagenes] No se pudo extraer la imagen: {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Generador Qwen (Alibaba Cloud DashScope)
# ---------------------------------------------------------------------------

def _extraer_img_qwen(data: dict) -> str | None:
    """Extrae la URL/base64 de la imagen de la respuesta DashScope."""
    for choice in data.get("output", {}).get("choices", []):
        msg = choice.get("message", {})
        for part in msg.get("content", []):
            if isinstance(part, dict) and part.get("image"):
                return part["image"]
    return None


def _descargar_qwen(url: str) -> bytes | None:
    """Baja la imagen: decodifica data-URI o descarga la URL firmada de OSS."""
    if url.startswith("data:"):
        try:
            return base64.b64decode(url.split(",", 1)[1])
        except Exception as e:
            print(f"[imagenes] No se pudo decodificar la imagen en base64: {e}", file=sys.stderr)
            return None
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=180) as resp:
            return resp.read()
    except Exception as e:
        print(f"[imagenes] No se pudo descargar la imagen de Qwen: {e}", file=sys.stderr)
        return None


def _generar_qwen(apikey: str, modelo: str, prompt: str, size: str, out: Path,
                  referencia: tuple[bytes, str] | None = None) -> bool:
    """Genera una imagen con Qwen vía DashScope y la guarda en ``out``."""
    import urllib.error
    import urllib.request

    content: list[dict] = []
    if referencia:
        b64 = base64.b64encode(referencia[0]).decode()
        content.append({"image": f"data:{referencia[1]};base64,{b64}"})
    content.append({"text": prompt})

    payload = {
        "model": modelo,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"prompt_extend": True, "size": size, "n": 1},
    }
    req = urllib.request.Request(
        qwen_generacion_url(), data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {apikey}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        print(f"[imagenes] Error Qwen {e.code}: {e.read().decode('utf-8', 'replace')[:400]}",
              file=sys.stderr)
        return False
    except Exception as e:
        print(f"[imagenes] Error de red con Qwen: {e}", file=sys.stderr)
        return False

    img_url = _extraer_img_qwen(data)
    if not img_url:
        print(f"[imagenes] Qwen no devolvió imagen para '{prompt[:40]}...'. "
              f"Respuesta: {json.dumps(data)[:300]}", file=sys.stderr)
        return False

    img_bytes = _descargar_qwen(img_url)
    if not img_bytes:
        return False

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(img_bytes)
    return True


# ---------------------------------------------------------------------------
# Despacho genérico
# ---------------------------------------------------------------------------

def _generar(proveedor: str, client, apikey: str | None, modelo: str, prompt: str,
             ratio: str, out: Path, referencia: tuple[bytes, str] | None = None) -> bool:
    if proveedor == "gemini":
        return _generar_gemini(client, modelo, prompt, ratio, out, referencia)
    return _generar_qwen(apikey or "", modelo, prompt, _ratio_a_size(ratio), out, referencia)


# ---------------------------------------------------------------------------
# Contact sheet (montaje para revisión del usuario)
# ---------------------------------------------------------------------------

def generar_contact_sheet(outdir: Path, out: Path, max_cols: int = 3) -> bool:
    """Construye una sola imagen con todas las escenas (grid) para revisar el estilo."""
    imgs = sorted(p for p in Path(outdir).glob("*.png"))
    if not imgs:
        print(f"[imagenes] Contact sheet: no hay imágenes en {outdir}.", file=sys.stderr)
        return False
    cols = min(max_cols, len(imgs))
    cw, ch = CS
    inputs: list[str] = []
    vf: list[str] = []
    for i, p in enumerate(imgs):
        inputs += ["-i", str(p)]
        vf.append(f"[{i}:v]scale={cw}:{ch}:force_original_aspect_ratio=decrease,"
                  f"pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];")
    layout = "|".join(f"{(i % cols) * cw}_{(i // cols) * ch}" for i in range(len(imgs)))
    vf.append(f"{''.join(f'[v{i}]' for i in range(len(imgs)))}"
              f"xstack=inputs={len(imgs)}:layout={layout}:fill=black")
    # Crear el directorio ANTES de que ffmpeg escriba el archivo de salida.
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", "".join(vf),
                               "-frames:v", "1", str(out)], capture_output=True, text=True)
    except FileNotFoundError:
        print("[imagenes] Contact sheet: 'ffmpeg' no está en el PATH.", file=sys.stderr)
        return False
    if proc.returncode != 0:
        print(f"[imagenes] Contact sheet: ffmpeg falló: {proc.stderr[-500:]}", file=sys.stderr)
        return False
    print(f"[imagenes] Contact sheet -> {out}")
    return True


def _ruta_contact_sheet(outdir: Path) -> Path:
    """Ruta por defecto del contact sheet: ``<workspace>/revision/contact_sheet.png``."""
    return outdir.parent / "revision" / "contact_sheet.png"


def main(argv: list[str] | None = None) -> int:
    proveedor_por_defecto = proveedor_imagen_por_defecto()
    ap = argparse.ArgumentParser(
        description="Generar imágenes por escena (Gemini / Qwen·Alibaba).")
    ap.add_argument("--guion", default="workspace/guion.json", help="Ruta al guion.json.")
    ap.add_argument("--outdir", default="workspace/imagenes", help="Carpeta de salida.")
    ap.add_argument("--proveedor", default=proveedor_por_defecto, choices=["gemini", "qwen"],
                    help="Proveedor de imágenes (default: IMAGEN_PROVEEDOR, o 'gemini').")
    ap.add_argument("--model", default=None,
                    help="Modelo de imagen del proveedor. Default: el del proveedor activo.")
    ap.add_argument("--apikey", default=None,
                    help="API key del proveedor (o env GEMINI_API_KEY / QWEN_API_KEY).")
    ap.add_argument("--solo", default=None, help="Solo regenerar esta escena (id).")
    ap.add_argument("--overwrite", action="store_true", help="Regenera aunque exista el archivo.")
    ap.add_argument("--aspect", default=None, help="Forzar ratio (p. ej. 9:16).")
    ap.add_argument("--estilo", default=None,
                    help="Ajuste global de estilo/feedback del usuario (p. ej. 'más colores "
                         "cálidos, estilo anime, fondos urbanos'). Se añade a todos los prompts.")
    ap.add_argument("--referencia", default=None,
                    help="Ruta a una imagen de referencia (.png/.jpg/...) cuyo estilo se usará de "
                         "forma consistente en todas las escenas. Si no se pasa, se usa "
                         "parametros.imagen_referencia del guion (si existe).")
    ap.add_argument("--contact-sheet", action="store_true",
                    help="Solo construye el montaje de las imágenes existentes y sale, "
                         "sin regenerar nada. Ruta: <workspace>/revision/contact_sheet.png.")
    args = ap.parse_args(argv)

    proveedor = (args.proveedor or proveedor_por_defecto).strip().lower()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Modo exclusivo: contact sheet (no regenera).
    if args.contact_sheet:
        return 0 if generar_contact_sheet(outdir, _ruta_contact_sheet(outdir)) else 1

    guion = cargar_guion(args.guion)
    ratio = args.aspect or _formato_a_ratio(guion["parametros"]["formato"])
    modelo = args.model or (qwen_modelo_por_defecto() if proveedor == "qwen" else MODELO_DEF)
    apikey = args.apikey or apikey_proveedor(proveedor)

    if proveedor != "gemini" and not apikey:
        print(f"[imagenes] Falta la API key para el proveedor '{proveedor}'. "
              f"Usa --apikey o la variable "
              f"{'QWEN_API_KEY' if proveedor == 'qwen' else 'GEMINI_API_KEY'}.", file=sys.stderr)
        return 2

    # Imagen de referencia: prioridad al argumento, luego al campo del guion.
    referencia = _leer_referencia(args.referencia or imagen_referencia(guion))
    if args.referencia or imagen_referencia(guion):
        print(f"[imagenes] Estilo anclado a imagen de referencia: "
              f"{args.referencia or imagen_referencia(guion)}")

    gemini_client = None
    if proveedor == "gemini":
        try:
            from google import genai
        except ImportError:
            print("[imagenes] Falta 'google-genai'. Instala con: pip install google-genai",
                  file=sys.stderr)
            return 2
        gemini_client = genai.Client(api_key=apikey)

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
        if args.estilo:
            prompt += f"\nAjuste solicitado por el usuario: {args.estilo}"
        if _generar(proveedor, gemini_client, apikey, modelo, prompt, ratio, out, referencia):
            print(f"[imagenes] {idx}/{len(escs)} ({proveedor}/{modelo}) -> {out.name}")
            ok += 1
        else:
            fallidas.append(esc["id"])
            print(f"[imagenes] {idx}/{len(escs)} FALLÓ {esc['id']}")

    guardar_json({"proveedor": proveedor, "model": modelo, "ratio": ratio,
                  "estilo": args.estilo, "fallidas": fallidas}, outdir / "reporte.json")
    print(f"[imagenes] OK: {ok} generadas, {len(fallidas)} fallidas.")
    if not fallidas:
        # Montaje de revisión para que el usuario apruebe el estilo.
        generar_contact_sheet(outdir, _ruta_contact_sheet(outdir))
    return 0 if not fallidas else 1


if __name__ == "__main__":
    raise SystemExit(main())

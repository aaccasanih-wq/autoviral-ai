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
import time
import zlib
from pathlib import Path

try:
    from guion import (cargar_guion, cargar_prompts_txt, directorio_sesion, escenas,
                       exportar_prompts_txt, guardar_json, imagenes_referencia,
                       incluye_protagonista, nombre_imagen)
except ImportError:  # pragma: no cover - permit run from anywhere via PYTHONPATH
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from guion import (cargar_guion, cargar_prompts_txt, directorio_sesion, escenas,  # type: ignore
                       exportar_prompts_txt, guardar_json, imagenes_referencia,
                       incluye_protagonista, nombre_imagen)  # type: ignore

from envutil import (apikey_proveedor, cargar_env, imagen_seed, model_imagen_por_defecto,
                     proveedor_imagen_por_defecto, qwen_generacion_url, qwen_modelo_por_defecto,
                     qwen_prompt_extend, qwen_rpm)

cargar_env()

MODELO_DEF = model_imagen_por_defecto()  # por defecto gemini-3.1-flash-image-preview (Nano Banana 2)

# Tamaño de celda del contact sheet (mantiene proporción 9:16 vertical).
CS = (480, 854)


class _Throttle:
    """Limita las peticiones a ``rpm`` por minuto (mínimo un intervalo entre cada una).

    Usado para no exceder el límite del free tier de Alibaba (``QWEN_RPM``): si con 5 escenas
    el límite es 2/min, se espera ~30 s entre peticiones (60/rpm).
    """

    def __init__(self, rpm: int) -> None:
        self._intervalo = (60.0 / rpm) if rpm and rpm > 0 else 0.0
        self._ultima: float = 0.0

    def esperar(self) -> None:
        if self._intervalo <= 0:
            return
        ahora = time.monotonic()
        falta = self._intervalo - (ahora - self._ultima)
        if falta > 0:
            time.sleep(falta)
        self._ultima = time.monotonic()


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


def _leer_referencias(paths: list[str]) -> list[tuple[bytes, str]]:
    """Lee una o más imágenes de referencia (pueden estar fuera del proyecto).

    Devuelve una lista de ``(bytes, mime)``. Si una ruta no existe o no se puede leer,
    se avisa y se omite (las que sí existen se siguen usando).
    """
    out: list[tuple[bytes, str]] = []
    for path in paths:
        p = Path(path)
        if not p.is_file():
            print(f"[imagenes] AVISO: imagen de referencia no encontrada: {p}. Se omite.",
                  file=sys.stderr)
            continue
        try:
            data = p.read_bytes()
        except OSError as e:
            print(f"[imagenes] AVISO: no se pudo leer la referencia {p}: {e}. Se omite.",
                  file=sys.stderr)
            continue
        out.append((data, _mime_tipo(p)))
    return out


# ---------------------------------------------------------------------------
# Generador Gemini
# ---------------------------------------------------------------------------

def _generar_gemini(client, modelo: str, prompt: str, ratio: str, out: Path,
                    referencias: list[tuple[bytes, str]] | None = None) -> bool:
    """Genera una imagen con Gemini (Nano Banana) y la guarda en ``out``."""
    from google.genai import types

    config_kwargs = {"response_modalities": ["IMAGE"]}
    # El ratio es opcional y varía por versión del SDK; lo enviamos de forma tolerante.
    try:
        config_kwargs["image_config"] = types.ImageConfig(aspect_ratio=ratio)
    except Exception:
        pass

    contents: list = []
    for data, mime in (referencias or []):
        contents.append(types.Part.from_bytes(data=data, mime_type=mime))
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


def _retry_after(exc) -> float:
    """Segundos a esperar según la cabecera ``Retry-After`` de un error 429 (o 30 por defecto)."""
    val = exc.headers.get("Retry-After") if getattr(exc, "headers", None) else None
    try:
        return float(val) if val else 30.0
    except (ValueError, TypeError):
        return 30.0


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


def _seed_auto(guion: dict) -> int:
    """Seed determinista a partir del guion (misma idea = misma seed; otra idea = otra seed)."""
    base = f"{guion.get('titulo', '')}|{guion.get('descripcion', '')}"
    return zlib.crc32(base.encode("utf-8")) % 2147483648  # rango 0..2147483647


def _generar_qwen(apikey: str, modelo: str, prompt: str, size: str, out: Path,
                  referencias: list[tuple[bytes, str]] | None = None,
                  seed: int | None = None, prompt_extend: bool = False) -> bool:
    """Genera una imagen con Qwen vía DashScope y la guarda en ``out``."""
    import urllib.error
    import urllib.request

    content: list[dict] = []
    for data, mime in (referencias or []):
        b64 = base64.b64encode(data).decode()
        content.append({"image": f"data:{mime};base64,{b64}"})
    content.append({"text": prompt})

    parameters: dict = {"prompt_extend": prompt_extend, "size": size, "n": 1}
    if seed is not None:
        # Misma seed para todas las escenas del video -> resultados más consistentes.
        parameters["seed"] = max(0, min(int(seed), 2147483647))
    payload = {
        "model": modelo,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": parameters,
    }
    req = urllib.request.Request(
        qwen_generacion_url(), data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {apikey}"},
        method="POST",
    )
    data = None
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
                break
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento < 2:
                espera = _retry_after(e)
                print(f"[imagenes] Límite de peticiones Qwen (429); reintento en {espera:.0f}s ...",
                      file=sys.stderr)
                time.sleep(espera)
                continue
            print(f"[imagenes] Error Qwen {e.code}: {e.read().decode('utf-8', 'replace')[:400]}",
                  file=sys.stderr)
            return False
        except Exception as e:
            print(f"[imagenes] Error de red con Qwen: {e}", file=sys.stderr)
            return False
    if data is None:
        print("[imagenes] Qwen: reintentos agotados tras el límite de peticiones.", file=sys.stderr)
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
             ratio: str, out: Path, referencias: list[tuple[bytes, str]] | None = None,
             seed: int | None = None, prompt_extend: bool = False) -> bool:
    if proveedor == "gemini":
        return _generar_gemini(client, modelo, prompt, ratio, out, referencias)
    return _generar_qwen(apikey or "", modelo, prompt, _ratio_a_size(ratio), out, referencias,
                         seed=seed, prompt_extend=prompt_extend)


def _ffmpeg_bin() -> str:
    """Binario ffmpeg: PATH o fallback imageio-ffmpeg/.venv."""
    p = __import__("shutil").which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        pp = imageio_ffmpeg.get_ffmpeg_exe()
        if pp and Path(pp).is_file():
            return pp
    except Exception:
        pass
    for cand in (Path(".venv/bin/ffmpeg"), Path(".venv/Scripts/ffmpeg.exe"), Path(".venv/Scripts/ffmpeg")):
        if cand.is_file():
            return str(cand)
    return "ffmpeg"


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
        proc = subprocess.run([_ffmpeg_bin(), "-y", *inputs, "-filter_complex", "".join(vf),
                               "-frames:v", "1", str(out)], capture_output=True, text=True)
    except FileNotFoundError:
        print("[imagenes] Contact sheet: 'ffmpeg' no está en el PATH (ni en imageio-ffmpeg). Ejecuta bash setup.sh.", file=sys.stderr)
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
    ap.add_argument("--outdir", default=None,
                    help="Carpeta de salida. Por defecto <carpeta del guion>/imagenes.")
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
    ap.add_argument("--estilo-id", default=None,
                    help="ID del catálogo estilos/<id> (ej. tom-jerry, palitos-doodle). "
                         "Carga STYLE + anti_drift_estilo siempre y CHARACTER + "
                         "anti_drift_personaje solo si la escena trae incluye_protagonista=true. "
                         "También se lee de guion.parametros.estilo_id si no se pasa por CLI.")
    ap.add_argument("--referencia", action="append", default=None,
                    help="Ruta a una imagen de referencia (.png/.jpg/...) cuyo estilo se usará de "
                         "forma consistente en todas las escenas. Se puede repetir para varias "
                         "imágenes, o separar con comas. Si no se pasa, se usa "
                         "parametros.imagen_referencia del guion (lista o string).")
    ap.add_argument("--seed", type=int, default=None,
                    help="Seed de generación (Qwen). Misma seed para todas las escenas del video "
                         "-> resultados más consistentes. Default: IMAGEN_SEED del .env, o "
                         "auto-derivada del título del guion (misma idea = misma seed).")
    ap.add_argument("--prompt-extend", action="store_true",
                    help="Activa la reescritura automática del prompt de Qwen (prompt_extend). "
                         "Por defecto está DESACTIVADA (QWEN_PROMPT_EXTEND=false) para maximizar "
                         "la consistencia entre escenas.")
    ap.add_argument("--contact-sheet", action="store_true",
                    help="Solo construye el montaje de las imágenes existentes y sale, "
                         "sin regenerar nada. Ruta: <session>/revision/contact_sheet.png.")
    ap.add_argument("--export-prompts", action="store_true",
                    help="Escribe el archivo de prompts editable (prompts.txt) a partir del guion "
                         "y sale, sin generar imágenes. Es para que el usuario revise/edite los "
                         "prompts antes de generar.")
    ap.add_argument("--prompts-file", default=None,
                    help="Ruta al archivo de prompts editable. Por defecto <carpeta del guion>/prompts.txt. "
                         "Si existe, se usan sus prompts como input final en vez de los del guion.")
    args = ap.parse_args(argv)

    proveedor = (args.proveedor or proveedor_por_defecto).strip().lower()

    guion = cargar_guion(args.guion)
    session = directorio_sesion(args.guion)
    outdir = Path(args.outdir) if args.outdir else session / "imagenes"
    outdir.mkdir(parents=True, exist_ok=True)

    # Archivo de prompts editable por el usuario (antes de generar las imágenes).
    prompts_path = Path(args.prompts_file) if args.prompts_file else session / "prompts.txt"
    if args.export_prompts:
        p = exportar_prompts_txt(guion, prompts_path)
        print(f"[imagenes] Prompts exportados -> {p}")
        print("[imagenes] El usuario puede editar ese archivo; luego vuelve a "
              "generar para usarlo como input.")
        return 0

    # Modo exclusivo: contact sheet (no regenera).
    if args.contact_sheet:
        return 0 if generar_contact_sheet(outdir, _ruta_contact_sheet(outdir)) else 1

    ratio = args.aspect or _formato_a_ratio(guion["parametros"]["formato"])
    modelo = args.model or (qwen_modelo_por_defecto() if proveedor == "qwen" else MODELO_DEF)
    apikey = args.apikey or apikey_proveedor(proveedor)

    if proveedor != "gemini" and not apikey:
        print(f"[imagenes] Falta la API key para el proveedor '{proveedor}'. "
              f"Usa --apikey o la variable "
              f"{'QWEN_API_KEY' if proveedor == 'qwen' else 'GEMINI_API_KEY'}.", file=sys.stderr)
        return 2

    # Prompts de imagen: si el usuario editó prompts.txt, se usan esos; si no, los del guion.
    # Siempre garantizamos que el archivo exista para que el usuario pueda editarlo.
    if not prompts_path.is_file():
        exportar_prompts_txt(guion, prompts_path)
        print(f"[imagenes] Prompts de imagen -> {prompts_path} (editables a mano).")
    prompts_editados = cargar_prompts_txt(prompts_path, guion)
    if prompts_editados:
        print(f"[imagenes] Usando {len(prompts_editados)} prompts editados de {prompts_path}.")

    # Estilo del catálogo: prioridad CLI --estilo-id > guion.parametros.estilo_id.
    # Aporta character_ficha/style_ficha/anti_drift + referencias fijas anti-drift.
    estilo_id = (args.estilo_id or (guion.get("parametros") or {}).get("estilo_id") or "").strip()
    estilo_data: dict = {}
    if estilo_id:
        try:
            import json as _json
            from pathlib import Path as _P
            _raiz = _P(__file__).resolve().parent.parent
            _cat = _json.loads((_raiz / "estilos" / "catalogo.json").read_text(encoding="utf-8"))
            _entry = next((e for e in _cat.get("estilos", []) if e["id"] == estilo_id), None)
            if _entry:
                estilo_data = _json.loads((_raiz / _entry["estilo_json"]).read_text(encoding="utf-8"))
                print(f"[imagenes] Estilo catálogo '{estilo_id}': {estilo_data.get('nombre', '')} "
                      f"(anti-drift activo, {len(estilo_data.get('referencias', []))} refs)")
            else:
                print(f"[imagenes] AVISO: estilo_id '{estilo_id}' no está en catalogo.json. Se ignora.",
                      file=sys.stderr)
        except Exception as e:
            print(f"[imagenes] AVISO: no se pudo cargar estilo '{estilo_id}': {e}", file=sys.stderr)

    # Imágenes de referencia: prioridad CLI --referencia > --estilo-id > guion.
    refs_cli: list[str] = []
    for v in (args.referencia or []):
        refs_cli += [x.strip() for x in v.split(",") if x.strip()]
    refs_estilo = estilo_data.get("referencias", []) if estilo_data else []
    referencias = _leer_referencias(refs_cli or refs_estilo or imagenes_referencia(guion))
    # Qwen solo soporta 0-3 imágenes de referencia (0 = T2I, 1-3 = I2I). Si se pasan más, trunca automáticamente.
    if proveedor == "qwen" and len(referencias) > 3:
        print(f"[imagenes] AVISO: Qwen soporta máximo 3 referencias, se recibieron {len(referencias)}. "
              f"Se usan solo las 3 primeras y se ignoran las demás para evitar error 400.", file=sys.stderr)
        referencias = referencias[:3]
    if refs_cli or imagenes_referencia(guion):
        print(f"[imagenes] Estilo anclado a {len(referencias)} imagen(es) de referencia: "
              f"{(refs_cli or imagenes_referencia(guion))[:3] if proveedor == 'qwen' and len(refs_cli or imagenes_referencia(guion)) > 3 else (refs_cli or imagenes_referencia(guion))}")

    gemini_client = None
    if proveedor == "gemini":
        try:
            from google import genai
        except ImportError:
            print("[imagenes] Falta 'google-genai'. Instala con: pip install google-genai",
                  file=sys.stderr)
            return 2
        gemini_client = genai.Client(api_key=apikey)

    # Seed: --seed > IMAGEN_SEED > auto-derivada del guion (misma idea = misma seed).
    seed = args.seed if args.seed is not None else imagen_seed()
    if seed is None:
        seed = _seed_auto(guion)
    prompt_extend = args.prompt_extend or qwen_prompt_extend()
    if proveedor == "qwen":
        print(f"[imagenes] Seed de consistencia: {seed}"
              f"{' (auto-derivada del guion)' if args.seed is None and imagen_seed() is None else ''}"
              f" | prompt_extend={'on' if prompt_extend else 'off'}")
    else:
        print("[imagenes] Aviso: el proveedor 'gemini' no soporta seed; se ignora.", file=sys.stderr)

    escs = [e for e in escenas(guion) if not args.solo or e["id"] == args.solo]
    if not escs:
        print(f"[imagenes] No hay escenas que regenerar (solo={args.solo}).", file=sys.stderr)
        return 1

    # Límite de peticiones por minuto (free tier de Alibaba; QWEN_RPM). Espacia las peticiones
    # para no superar el máximo (p. ej. 2/min en qwen-image-2.0, 5/min en qwen-image-3.0).
    rpm = qwen_rpm()
    throttle = _Throttle(rpm)
    if proveedor == "qwen" and rpm > 0:
        # Estimación de tiempo total para que el usuario no piense que se colgó
        pendientes = sum(1 for esc in escs if not (outdir / nombre_imagen(esc)).is_file() or args.overwrite)
        if pendientes > 0:
            est_min = (pendientes * 60.0 / rpm) / 60.0
            print(f"[imagenes] Límite de peticiones activado: {rpm}/min (QWEN_RPM). "
                  f"Pendientes: {pendientes} escenas → ~{est_min:.1f} min estimados (throttle).")
        else:
            print(f"[imagenes] Límite de peticiones activado: {rpm}/min (QWEN_RPM). Todas las imágenes ya existen, sin espera.")

    ok = 0
    fallidas: list[str] = []
    for idx, esc in enumerate(escs, 1):
        out = outdir / nombre_imagen(esc)
        if out.is_file() and not args.overwrite:
            print(f"[imagenes] {idx}/{len(escs)} existe, omitido: {out.name}")
            ok += 1
            continue
        # Prompt final: el editado por el usuario (prompts.txt) si existe; si no, el del guion.
        # Los prompts de Fase 1 ya vienen listos para copiar/pegar (frase EN de referencia +
        # CHARACTER solo si incluye_protagonista=true). Aquí solo se refuerza lo que falte.
        base_prompt = prompts_editados.get(esc["id"]) or esc["prompt_imagen"]
        _flag = incluye_protagonista(esc)
        con_prota = (_flag if _flag is not None else ("CHARACTER:" in base_prompt))
        # Anti-drift dividido: STYLE siempre; CHARACTER solo cuando el protagonista aparece.
        if estilo_data:
            cf = estilo_data.get("character_ficha", "")
            sf = estilo_data.get("style_ficha", "")
            ad_e = estilo_data.get("anti_drift_estilo") or estilo_data.get("anti_drift", "")
            ad_p = estilo_data.get("anti_drift_personaje", "")
            fr_con = estilo_data.get("frase_referencia_con", "")
            fr_sin = estilo_data.get("frase_referencia_sin", "")
            if "attached reference image" not in base_prompt:
                base_prompt = f"{(fr_con if con_prota else fr_sin) + ' ' if (fr_con if con_prota else fr_sin) else ''}{base_prompt}"
            if con_prota:
                if cf and "CHARACTER:" not in base_prompt:
                    base_prompt = f"{cf} {base_prompt}"
                if sf and "STYLE:" not in base_prompt:
                    base_prompt = f"{base_prompt} {sf}"
                for ad in (ad_p, ad_e):
                    if ad and ad[:30] not in base_prompt:
                        base_prompt = f"{base_prompt} {ad}"
            else:
                if _flag is False and "CHARACTER:" in base_prompt:
                    print(f"[imagenes] AVISO {esc['id']}: incluye_protagonista=false pero el prompt "
                          f"menciona CHARACTER (guion viejo). Se respeta el texto; revisa el guion.",
                          file=sys.stderr)
                if sf and "STYLE:" not in base_prompt:
                    base_prompt = f"{base_prompt} {sf}"
                if ad_e and ad_e[:30] not in base_prompt:
                    base_prompt = f"{base_prompt} {ad_e}"
        prompt = f"{base_prompt}. Aspect ratio {ratio}. High quality, crisp details."
        # Referencias: con protagonista replica personaje+estilo; sin él, solo estilo/fondo.
        # (Sin esto, el modelo puede ignorar la(s) imagen(es) o añadir una mascota no pedida.)
        if referencias:
            if con_prota:
                prompt += " Replicate the exact character and art style from the reference image(s). Keep the main character identical in appearance to the reference across all scenes."
            else:
                prompt += " Match the art style and background from the reference image(s). Do not add any mascot or character unless named in the prompt."
            _ad_extra = (estilo_data.get("anti_drift_personaje", "") + " " +
                         estilo_data.get("anti_drift_estilo", "")).strip() if estilo_data else ""
            if not _ad_extra and estilo_data:
                _ad_extra = estilo_data.get("anti_drift", "")
            if _ad_extra and _ad_extra[:30] not in prompt:
                prompt += f" {_ad_extra}"
        if args.estilo:
            prompt += f"\nAjuste solicitado por el usuario: {args.estilo}"
        throttle.esperar()  # respetar el RPM antes de cada petición
        if _generar(proveedor, gemini_client, apikey, modelo, prompt, ratio, out, referencias,
                    seed=seed, prompt_extend=prompt_extend):
            print(f"[imagenes] {idx}/{len(escs)} ({proveedor}/{modelo}) -> {out.name}")
            ok += 1
        else:
            fallidas.append(esc["id"])
            print(f"[imagenes] {idx}/{len(escs)} FALLÓ {esc['id']}")

    guardar_json({"proveedor": proveedor, "model": modelo, "ratio": ratio,
                  "estilo": args.estilo, "estilo_id": estilo_id or None,
                  "seed": seed if proveedor == "qwen" else None,
                  "prompt_extend": prompt_extend if proveedor == "qwen" else None,
                  "fallidas": fallidas}, outdir / "reporte.json")
    print(f"[imagenes] OK: {ok} generadas, {len(fallidas)} fallidas.")
    if not fallidas:
        # Montaje de revisión para que el usuario apruebe el estilo.
        generar_contact_sheet(outdir, _ruta_contact_sheet(outdir))
    return 0 if not fallidas else 1


if __name__ == "__main__":
    raise SystemExit(main())

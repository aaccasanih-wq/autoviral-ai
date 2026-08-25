"""Paso 5 del pipeline: ensamblar el video final con FFmpeg.

Toma las imágenes por escena (``MM_SS_descripcion.png``), aplica **efectos de edición** a cada una
(movimiento tipo Ken Burns vía ``zoompan``), une las escenas con **transiciones** (``xfade``),
añade fades globales y superpone la narración. La duración de cada escena es la real del audio
(``timings.json``) y las transiciones se calculan sobre los tiempos originales del guion, de modo
que **el audio nunca se desincroniza** (cada segmento se extiende lo que dura su transición).

Efectos (catálogo — ver ``--list-efectos``):
    * Movimiento por escena: ``static``, ``zoom_in``, ``zoom_out``, ``pan_left``, ``pan_right``,
      ``kenburns`` (zoom + paneo diagonal).
    * Transición de salida de cada escena: ``none`` (corte seco), ``fade``, ``dissolve``,
      ``wipeleft``, ``slideup``, ``circleopen``.
    * Grading opcional: ``none``, ``warm``, ``cool``.
    * Fades globales de entrada/salida.

Los efectos se resuelven con prioridad: ``efectos`` de la escena (en ``guion.json``, opcional) >
``--preset suave|dinamico|off`` (default ``suave``). Con ``off`` (y sin efectos por escena) el
comportamiento es el clásico: imagen fija + concat, sin fades.

Uso:
    python scripts/ensamblar_video.py --guion <sesión>/guion.json --formato vertical
    python scripts/ensamblar_video.py --guion <sesión>/guion.json --preset dinamico
    python scripts/ensamblar_video.py --list-efectos
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from guion import (cargar_guion, directorio_sesion, duracion_objetivo, escenas, mmss)
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from guion import (cargar_guion, directorio_sesion, duracion_objetivo, escenas, mmss)  # type: ignore

FPS = 30
DIMS = {"vertical": (1080, 1920), "horizontal": (1920, 1080)}

# --- Catálogo de efectos ---------------------------------------------------
MOVIMIENTOS = ("static", "zoom_in", "zoom_out", "pan_left", "pan_right", "kenburns")
TRANSICIONES = ("none", "fade", "dissolve", "wipeleft", "slideup", "circleopen")
GRADES = ("none", "warm", "cool")

GRADE_FILTROS = {
    # Antes eran valores más fuertes (.07) que en combinación con zoompan + yuv420p
    # lavaban los colores en fondos claros (caso reportado: 00_35, 01_05, 01_48).
    # Ahora son más sutiles y con leve boost de saturación para no desteñir.
    "warm": "colorbalance=rm=0.03:gm=0.005:bm=-0.03:rh=0.02:bh=-0.02,eq=saturation=1.04:contrast=1.02",
    "cool": "colorbalance=rm=-0.03:bm=0.03:rh=-0.01:bh=0.02,eq=saturation=1.04:contrast=1.02",
}

PRESETS: dict[str, dict | None] = {
    "suave": {  # Ken Burns lento + crossfade — look editorial para historias
        "movimientos": ("kenburns", "zoom_in", "pan_right", "zoom_out", "pan_left"),
        "intensidad": 1.12,
        "transiciones": ("fade",),
        "transicion_duracion": 0.4,
        "grade": "none",
    },
    "dinamico": {  # Movimientos marcados + transiciones variadas — más energía
        "movimientos": ("zoom_in", "kenburns", "pan_left", "zoom_out", "pan_right"),
        "intensidad": 1.22,
        "transiciones": ("dissolve", "slideup", "wipeleft", "circleopen", "fade"),
        "transicion_duracion": 0.35,
        "grade": "none",
    },
    "off": None,  # comportamiento clásico: imagen fija + concat
}


def _imprimir_catalogo() -> None:
    print("Catálogo de efectos de edición (ensamblar_video.py)\n")
    print("Movimiento por escena (zoompan / Ken Burns):")
    for m in MOVIMIENTOS:
        print(f"  - {m}")
    print("\nTransición de salida de cada escena (xfade):")
    for t in TRANSICIONES:
        print(f"  - {t}" + ("  (corte seco)" if t == "none" else ""))
    print("\nGrading de color opcional:")
    for g in GRADES:
        print(f"  - {g}")
    print("\nFades globales: entrada 0.5s / salida 0.6s (solo con preset activo).\n")
    print("Presets:")
    for nombre, p in PRESETS.items():
        if p is None:
            print(f"  - {nombre}: sin efectos (imagen fija + concat, como la v1)")
        else:
            print(f"  - {nombre}: intensidad {p['intensidad']} | transición "
                  f"{'/'.join(p['transiciones'])} {p['transicion_duracion']}s | grade {p['grade']}")
    print("\nPrioridad: efectos de la escena (guion.json) > --preset > off.")
    print('Ejemplo por escena en guion.json: "efectos": {"movimiento": "zoom_in", '
          '"intensidad": 1.15, "transicion": "dissolve", "transicion_duracion": 0.4, "grade": "cool"}')


# ---------------------------------------------------------------------------
# Utilidades ffmpeg
# ---------------------------------------------------------------------------

def _escape_filter_path(path: str) -> str:
    """Escapa un path para usarlo dentro de un filtro de ffmpeg (p. ej. subtitles=)."""
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg falló ({' '.join(cmd[:2])} ...):\n{proc.stderr[-2000:]}\n"
            f"{proc.stdout[-1000:]}"
        )


def _soporta_filtro(nombre: str) -> bool:
    """True si el ffmpeg en PATH incluye el filtro ``nombre`` (p. ej. 'subtitles', 'xfade')."""
    import re
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                             capture_output=True, text=True).stdout
    except Exception:
        return False
    return re.search(rf"(?<![-\w]){re.escape(nombre)}(?![-\w])", out) is not None


def _cargar_timings(audio_dir: Path) -> dict[str, dict]:
    p = audio_dir / "timings.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("escenas", {})
    except Exception:
        return {}


def _buscar_imagen(imagedir: Path, esc: dict, usadas: set[Path]) -> tuple[Path | None, str]:
    """Busca la imagen que corresponde a una escena por su prefijo ``MM_SS_``."""
    prefijo = mmss(int(esc.get("inicio_segundos", 0))).replace(":", "_") + "_"
    candidatos = sorted(p for p in imagedir.glob("*.png") if p.name.startswith(prefijo))
    for c in candidatos:
        if c not in usadas:
            return c, "match"
    restantes = sorted(p for p in imagedir.glob("*.png") if p not in usadas)
    if restantes:
        return restantes[0], "order"
    return None, "none"


# ---------------------------------------------------------------------------
# Segmentos por escena (con movimiento Ken Burns opcional)
# ---------------------------------------------------------------------------

def _zoompan_expr(mov: str, intens: float, frames: int) -> tuple[str, str, str]:
    """Devuelve las expresiones (z, x, y) de zoompan para un movimiento."""
    if mov == "zoom_in":
        return (f"1+({intens}-1)*on/{frames}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2")
    if mov == "zoom_out":
        return (f"{intens}-({intens}-1)*on/{frames}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2")
    if mov == "pan_left":
        z = 1.0 + (intens - 1.0) / 2.0
        return (f"{z:.4f}", f"(iw-iw/zoom)*(1-on/{frames})", "(ih-ih/zoom)/2")
    if mov == "pan_right":
        z = 1.0 + (intens - 1.0) / 2.0
        return (f"{z:.4f}", f"(iw-iw/zoom)*on/{frames}", "(ih-ih/zoom)/2")
    # kenburns: zoom in + paneo diagonal hacia el centro
    return (f"1+({intens}-1)*on/{frames}",
            f"(iw-iw/zoom)*on/{frames}", f"(ih-ih/zoom)*on/{frames}")


def _segmento_imagen(img: Path | None, w: int, h: int, dur: float, out: Path,
                     movimiento: str = "static", intens: float = 1.0,
                     grade: str = "none") -> None:
    """Renderiza un segmento de video (imagen estática o con movimiento) de duración ``dur``."""
    grade_f = GRADE_FILTROS.get(grade, "")
    # veryfast + crf 22 es ~3x más rápido que medium/crf20 y mantiene calidad suficiente para Shorts
    # (antes medium hacía que 9 escenas tardaran >10min y el timeout de la tool mataba el proceso)
    codec = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22"]
    if img is None:
        # Placeholder negro para escenas sin imagen.
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={FPS}",
              "-t", f"{dur:.3f}", *codec, "-pix_fmt", "yuv420p", str(out)])
        return

    if movimiento in ("", "static"):
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}")
        if grade_f:
            vf += f",{grade_f}"
        vf += ",format=yuv420p"
        _run(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-t", f"{dur:.3f}",
              "-vf", vf, *codec, str(out)])
        return

    # Movimiento Ken Burns: upscale x2 (reduce el jitter del zoompan) -> zoompan -> tamaño final.
    frames = max(1, int(round(dur * FPS)))
    z, x, y = _zoompan_expr(movimiento, intens, frames)
    vf = (f"scale={2 * w}:{2 * h}:force_original_aspect_ratio=increase,crop={2 * w}:{2 * h},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={FPS},setsar=1")
    if grade_f:
        vf += f",{grade_f}"
    vf += ",format=yuv420p"
    _run(["ffmpeg", "-y", "-i", str(img), "-vf", vf, "-frames:v", str(frames), *codec, str(out)])


# ---------------------------------------------------------------------------
# Unión de segmentos: concat clásico o xfade con transiciones
# ---------------------------------------------------------------------------

def _concatenar_simple(segmentos: list[Path], base: Path) -> None:
    lista = base.parent / "concat.txt"
    # Rutas ABSOLUTAS: el demuxer concat resuelve las rutas relativas respecto a la carpeta
    # del archivo de lista, no del cwd.
    lista.write_text("".join(f"file '{s.resolve().as_posix()}'\n" for s in segmentos),
                     encoding="utf-8")
    try:
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
              "-c", "copy", str(base)])
    finally:
        lista.unlink(missing_ok=True)


def _unir_con_transiciones(segmentos: list[Path], transiciones: list[tuple[str, float]],
                           durs: list[float], base: Path) -> None:
    """Une segmentos con xfade preservando los tiempos del guion (audio sincronizado).

    Cada segmento se renderizó extendido la duración de su transición de salida; el ``offset``
    de cada xfade es el inicio original de la escena siguiente menos la transición, de modo que
    la transición ocurre en ``[T_{k} - t, T_{k}]`` y las escenas siguen empezando exactamente
    cuando empieza su narración.
    """
    inputs: list[str] = []
    for s in segmentos:
        inputs += ["-i", str(s)]
    partes: list[str] = []
    prev = "[0:v]"
    acumulado = 0.0
    for k, (nombre, t) in enumerate(transiciones):
        acumulado += durs[k]
        off = max(0.0, acumulado - t)
        etiqueta = f"[x{k + 1}]" if k + 1 < len(segmentos) - 1 else "[vout]"
        partes.append(f"{prev}[{k + 1}:v]xfade=transition={nombre}:duration={t:.3f}"
                      f":offset={off:.3f}{etiqueta}")
        prev = etiqueta
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(partes),
           "-map", "[vout]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
           "-pix_fmt", "yuv420p", str(base)])


# ---------------------------------------------------------------------------
# Resolución de efectos por escena
# ---------------------------------------------------------------------------

def _resolver_efectos(escs: list[dict], preset_nombre: str) -> list[dict]:
    """Prioridad: efectos de la escena (guion) > preset. Devuelve config por escena."""
    preset = PRESETS.get(preset_nombre)
    res: list[dict] = []
    for i, esc in enumerate(escs):
        ef = esc.get("efectos") if isinstance(esc.get("efectos"), dict) else {}

        mov = str(ef.get("movimiento") or (preset["movimientos"][i % len(preset["movimientos"])]
                                           if preset else "static")).strip()
        if mov not in MOVIMIENTOS:
            print(f"[ensamblar] Aviso: movimiento '{mov}' desconocido en {esc['id']}; uso 'static'.",
                  file=sys.stderr)
            mov = "static"
        try:
            intens = max(1.0, min(1.6, float(ef.get("intensidad",
                                                     preset["intensidad"] if preset else 1.0))))
        except (TypeError, ValueError):
            intens = preset["intensidad"] if preset else 1.0

        trans = str(ef.get("transicion") or (preset["transiciones"][i % len(preset["transiciones"])]
                                             if preset else "none")).strip()
        if trans not in TRANSICIONES:
            print(f"[ensamblar] Aviso: transición '{trans}' desconocida en {esc['id']}; uso 'none'.",
                  file=sys.stderr)
            trans = "none"
        try:
            tdur = max(0.0, min(1.5, float(ef.get("transicion_duracion",
                                                  preset["transicion_duracion"] if preset else 0.0))))
        except (TypeError, ValueError):
            tdur = preset["transicion_duracion"] if preset else 0.0
        if trans == "none":
            tdur = 0.0

        grade = str(ef.get("grade") or (preset["grade"] if preset else "none")).strip()
        if grade not in GRADES:
            grade = "none"

        res.append({"movimiento": mov, "intensidad": round(intens, 3), "transicion": trans,
                    "transicion_duracion": round(tdur, 3), "grade": grade})

    if res:
        res[-1]["transicion"] = "none"  # la última escena no tiene transición de salida
        res[-1]["transicion_duracion"] = 0.0
    return res


# ---------------------------------------------------------------------------
# Ensamblado principal
# ---------------------------------------------------------------------------

def ensamblar(guion: dict, imagedir: Path, audio: Path, srt: Path, outdir: Path,
              formato: str, salida: str, preset_nombre: str = "suave") -> Path:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("No se encontró 'ffmpeg' en el PATH. Instálalo para ensamblar el video.")
    if preset_nombre not in PRESETS:
        raise RuntimeError(f"Preset desconocido '{preset_nombre}'. "
                           f"Opciones: {', '.join(PRESETS)} (o --list-efectos).")

    w, h = DIMS[formato]
    escs = escenas(guion)
    timings = _cargar_timings(audio.parent)
    efectos = _resolver_efectos(escs, preset_nombre)

    outdir.mkdir(parents=True, exist_ok=True)
    tmp = outdir / "_work"
    tmp.mkdir(parents=True, exist_ok=True)

    # 1) Segmentos: una escena = un segmento, extendido la duración de su transición de salida.
    segmentos: list[Path] = []
    durs: list[float] = []
    usadas: set[Path] = set()
    faltantes: list[str] = []
    reporte: list[dict] = []
    for i, esc in enumerate(escs):
        dur = timings.get(esc["id"], {}).get("duracion_segundos")
        if not dur:
            dur = float(esc.get("fin_segundos", esc.get("inicio_segundos", 0))) - float(
                esc.get("inicio_segundos", 0))
        if dur <= 0:
            dur = 1.0
        # Cuantizar a la grilla de frames: los offsets del xfade deben coincidir con lo
        # realmente codificado, o el error de redondeo se acumula entre escenas.
        dur = round(round(float(dur) * FPS) / FPS, 6)
        durs.append(dur)

        ef = efectos[i]
        t_salida = ef["transicion_duracion"] if i < len(escs) - 1 else 0.0
        # Colchón en el último segmento: evita que -shortest recorte el final de la narración
        # por diferencias de redondeo entre el video y el audio.
        pad = 0.5 if i == len(escs) - 1 else 0.0
        img, modo = _buscar_imagen(imagedir, esc, usadas)
        if img is None:
            faltantes.append(esc["id"])
        else:
            usadas.add(img)
        seg = tmp / f"{esc['id']}.mp4"
        _segmento_imagen(img, w, h, dur + t_salida + pad, seg,
                         movimiento=ef["movimiento"], intens=ef["intensidad"], grade=ef["grade"])
        segmentos.append(seg)
        reporte.append({"id": esc["id"], "imagen": str(img) if img else None, "modo": modo,
                        "duracion_segundos": round(float(dur), 3), **ef})

    if faltantes:
        print(f"[ensamblar] Aviso: sin imagen para {', '.join(faltantes)} (placeholder negro).",
              file=sys.stderr)

    # 2) Unir segmentos: xfade si hay transiciones válidas (y ffmpeg las soporta); si no, concat clásico.
    # Nota: ffmpeg 7.1 (imageio-ffmpeg con libass) es estricto con xfade: transition=none no existe.
    # Por eso filtramos "none" o duraciones 0 para no generar xfade inválido.
    transiciones_raw = [(efectos[i]["transicion"], efectos[i]["transicion_duracion"])
                        for i in range(len(escs) - 1)]
    # Normalizar: "none" o duración 0 => hard cut (no xfade). Solo xfade si hay al menos una válida.
    transiciones = []
    for nombre, dur in transiciones_raw:
        if nombre == "none" or dur <= 0:
            transiciones.append(("none", 0.0))
        else:
            transiciones.append((nombre, dur))
    # xfade solo si hay al menos una transición real y ffmpeg la soporta
    usa_xfade = (len(escs) > 1 and any(t[0] != "none" and t[1] > 0 for t in transiciones)
                 and _soporta_filtro("xfade"))
    if len(escs) > 1 and any(t[0] != "none" and t[1] > 0 for t in transiciones) and not _soporta_filtro("xfade"):
        print("[ensamblar] Aviso: este ffmpeg no soporta 'xfade'; uno sin transiciones.",
              file=sys.stderr)
    # Si alguna transición es "none", el xfade no puede representar un hard cut directamente.
    # En ese caso, usamos concat simple para evitar error de ffmpeg 7.1; se pierde el xfade
    # pero el video sigue correcto. Una futura mejora es implementar xfade mixto.
    if usa_xfade and any(t[0] == "none" for t in transiciones):
        print("[ensamblar] Aviso: transiciones mixtas con 'none' (hard cut) no se pueden hacer con xfade en ffmpeg 7.1; "
              "usando concat simple (cortes secos) para todas las escenas.", file=sys.stderr)
        usa_xfade = False
    base = outdir / "_base.mp4"
    if usa_xfade:
        _unir_con_transiciones(segmentos, transiciones, durs, base)
    else:
        _concatenar_simple(segmentos, base)

    # 3) Mux audio + fades globales + subtítulos (quemados por defecto) + exportar.
    final = outdir / salida
    total = sum(durs)
    vf: list[str] = []
    if usa_xfade or preset_nombre != "off":
        vf.append("fade=t=in:st=0:d=0.5")
        if total > 1.0:
            vf.append(f"fade=t=out:st={max(0.0, total - 0.6):.3f}:d=0.6")
    # Subtítulos: por defecto SÍ se queman (estilo TikTok amarillo + hook rojo).
    # Prioridad: <sesion>/transcripcion/narracion.ass (palabra-a-palabra) > .srt frase-a-frase.
    # Se puede desactivar con parametros.subtitulos.enabled=false en guion.json o --no-subtitulos.
    subt_cfg = (guion.get("parametros") or {}).get("subtitulos") or {}
    subt_enabled = True if not isinstance(subt_cfg, dict) else subt_cfg.get("enabled", True)
    # Flag CLI --no-subtitulos tiene prioridad (se maneja en main, pero también aquí por si se llama directo)
    # Buscar ASS primero (word-by-word), luego SRT.
    ass_path = srt.parent / "narracion.ass"
    sub_path = None
    if subt_enabled and ass_path.is_file():
        sub_path = ass_path
    elif subt_enabled and srt.is_file():
        sub_path = srt
    if sub_path is not None:
        if _soporta_filtro("subtitles") or _soporta_filtro("ass"):
            # subtitles funciona para .srt y .ass (libass detecta por extensión)
            vf.append(f"subtitles={_escape_filter_path(str(sub_path))}")
            print(f"[ensamblar] Quemando subtítulos -> {sub_path.name} ({'ASS palabra-a-palabra' if sub_path.suffix == '.ass' else 'SRT'})")
        else:
            print("[ensamblar] Aviso: ffmpeg sin filtro 'subtitles'/'ass' (sin libass); "
                  "subtítulos no quemados. Instala ffmpeg con libass: pip install imageio-ffmpeg "
                  "y copia el binario a tu PATH, o usa conda-forge con libass.", file=sys.stderr)
            print(f"[ensamblar] Sidecar disponible: {sub_path}", file=sys.stderr)
    elif not subt_enabled:
        print("[ensamblar] Subtítulos desactivados (parametros.subtitulos.enabled=false).", file=sys.stderr)
    cmd = ["ffmpeg", "-y", "-i", str(base), "-i", str(audio), "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest"]
    if total > 0:
        # Recorte exacto a la suma de las duraciones reales (= duración del audio): evita que
        # el colchón del último segmento o el interleave de -shortest dejen cola en silencio.
        cmd += ["-t", f"{total:.3f}"]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd.append(str(final))
    _run(cmd)

    # Limpieza de intermedios.
    base.unlink(missing_ok=True)
    shutil.rmtree(tmp, ignore_errors=True)
    (outdir / "reporte_ensamblado.json").write_text(
        json.dumps({
            "formato": formato, "resolucion": f"{w}x{h}", "preset": preset_nombre,
            "efectos_activos": bool(preset_nombre != "off" or
                                    any(e["movimiento"] != "static" or e["grade"] != "none"
                                        or e["transicion_duracion"] > 0 for e in efectos)),
            "transiciones_xfade": usa_xfade,
            "escenas": reporte, "objetivo_segundos": duracion_objetivo(guion),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return final


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ensamblar el video final (FFmpeg, con efectos).")
    ap.add_argument("--guion", default="workspace/guion.json")
    ap.add_argument("--imagedir", default=None,
                    help="Carpeta de imágenes. Por defecto <carpeta del guion>/imagenes.")
    ap.add_argument("--audio", default=None,
                    help="Audio narrado (.mp3). Por defecto <carpeta del guion>/audio/narracion.mp3.")
    ap.add_argument("--srt", default=None,
                    help="Subtítulos (.srt). Por defecto <carpeta del guion>/transcripcion/narracion.srt.")
    ap.add_argument("--outdir", default=None,
                    help="Carpeta de salida. Por defecto <carpeta del guion>/video.")
    ap.add_argument("--formato", default=None, choices=["vertical", "horizontal"],
                    help="Por defecto toma el formato del guion.")
    ap.add_argument("--salida", default="final.mp4", help="Nombre del archivo final.")
    ap.add_argument("--preset", default="suave", choices=list(PRESETS),
                     help="Preset de edición cuando la escena no define 'efectos'. "
                          "Default: suave (Ken Burns lento + crossfade). 'off' = como la v1.")
    ap.add_argument("--no-subtitulos", action="store_true",
                     help="No quemar subtítulos en el video (por defecto se queman si existe .ass/.srt).")
    ap.add_argument("--list-efectos", action="store_true",
                     help="Muestra el catálogo de efectos y presets, y sale.")
    args = ap.parse_args(argv)

    if args.list_efectos:
        _imprimir_catalogo()
        return 0

    try:
        guion = cargar_guion(args.guion)
        sd = directorio_sesion(args.guion)
        imagedir = Path(args.imagedir) if args.imagedir else sd / "imagenes"
        audio = Path(args.audio) if args.audio else sd / "audio" / "narracion.mp3"
        srt = Path(args.srt) if args.srt else sd / "transcripcion" / "narracion.srt"
        outdir = Path(args.outdir) if args.outdir else sd / "video"
        formato = args.formato or guion["parametros"]["formato"]
        if args.no_subtitulos:
            guion.setdefault("parametros", {}).setdefault("subtitulos", {})["enabled"] = False
        out = ensamblar(guion, imagedir, audio, srt, outdir, formato, args.salida,
                        preset_nombre=args.preset)
    except Exception as e:
        print(f"[ensamblar] Error: {e}", file=sys.stderr)
        return 1

    print(f"[ensamblar] OK -> {out}")
    print(f"[ensamblar] reporte -> {outdir / 'reporte_ensamblado.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

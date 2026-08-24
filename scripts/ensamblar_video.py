"""Paso 5 del pipeline: ensamblar el video final con FFmpeg.

Toma las imágenes por escena (``MM_SS_descripcion.png``), ajusta cada una a la duración real de su
escena (desde ``timings.json``), concatena, superpone la narración, quema los subtítulos (``.srt``)
y exporta al formato/resolución objetivo.

Uso:
    python scripts/ensamblar_video.py --guion workspace/guion.json \
      --imagedir workspace/imagenes --audio workspace/audio/narracion.mp3 \
      --srt workspace/transcripcion/narracion.srt --outdir workspace/video --formato vertical
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from guion import (cargar_guion, duracion_objetivo, escenas, mmss)
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from guion import cargar_guion, duracion_objetivo, escenas, mmss  # type: ignore

FPS = 30
DIMS = {"vertical": (1080, 1920), "horizontal": (1920, 1080)}


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
    """True si el ffmpeg en PATH incluye el filtro ``nombre`` (p. ej. 'subtitles')."""
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
    # Match exacto por prefijo del inicio en MM:SS.
    prefijo = mmss(int(esc.get("inicio_segundos", 0))).replace(":", "_") + "_"
    candidatos = sorted(p for p in imagedir.glob("*.png") if p.name.startswith(prefijo))
    for c in candidatos:
        if c not in usadas:
            return c, "match"
    # Fallback: primera imagen sin usar (por orden de nombre), para tolerar renombres.
    restantes = sorted(p for p in imagedir.glob("*.png") if p not in usadas)
    if restantes:
        return restantes[0], "order"
    return None, "none"


def _segmento_imagen(img: Path | None, w: int, h: int, dur: float, out: Path) -> None:
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},format=yuv420p")
    if img is not None:
        _run(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-t", f"{dur:.3f}",
              "-vf", vf, "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(out)])
    else:
        # Placeholder negro para escenas sin imagen.
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={FPS}",
              "-t", f"{dur:.3f}", "-an", "-c:v", "libx264", "-preset", "medium", "-crf",
              "20", str(out)])


def ensamblar(guion: dict, imagedir: Path, audio: Path, srt: Path, outdir: Path,
              formato: str, salida: str) -> Path:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("No se encontró 'ffmpeg' en el PATH. Instálalo para ensamblar el video.")

    w, h = DIMS[formato]
    escs = escenas(guion)
    timings = _cargar_timings(audio.parent)

    outdir.mkdir(parents=True, exist_ok=True)
    tmp = outdir / "_work"
    tmp.mkdir(parents=True, exist_ok=True)

    # 1) Segmentos (una escena = una duración real = un segmento).
    segmentos: list[Path] = []
    usadas: set[Path] = set()
    faltantes: list[str] = []
    reporte: list[dict] = []
    for esc in escs:
        dur = timings.get(esc["id"], {}).get("duracion_segundos")
        if not dur:
            dur = float(esc.get("fin_segundos", esc.get("inicio_segundos", 0))) - float(
                esc.get("inicio_segundos", 0))
        if dur <= 0:
            dur = 1.0
        img, modo = _buscar_imagen(imagedir, esc, usadas)
        img_final: Path | None = img
        if img_final is None:
            faltantes.append(esc["id"])
        else:
            usadas.add(img_final)
        seg = tmp / f"{esc['id']}.mp4"
        _segmento_imagen(img_final, w, h, dur, seg)
        segmentos.append(seg)
        reporte.append({"id": esc["id"], "imagen": str(img_final) if img_final else None,
                        "modo": modo, "duracion_segundos": round(float(dur), 3)})

    if faltantes:
        print(f"[ensamblar] Aviso: sin imagen para {', '.join(faltantes)} (placeholder negro).",
              file=sys.stderr)

    # 2) Concatenar segmentos (mismo codec/tamaño).
    lista = tmp / "concat.txt"
    # Rutas ABSOLUTAS: el demuxer concat resuelve las rutas relativas respecto a la carpeta
    # del archivo de lista, no del cwd. Usamos rutas absolutas para que sea independiente.
    lista.write_text("".join(f"file '{s.resolve().as_posix()}'\n" for s in segmentos), encoding="utf-8")
    base = outdir / "_base.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(base)])

    # 3) Mux audio + quemar subtítulos + exportar.
    final = outdir / salida
    cmd = ["ffmpeg", "-y", "-i", str(base), "-i", str(audio), "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest"]
    if srt.is_file():
        if _soporta_filtro("subtitles"):
            cmd += ["-vf", f"subtitles={_escape_filter_path(str(srt))}"]
        else:
            print("[ensamblar] Aviso: el ffmpeg actual no soporta el filtro 'subtitles' "
                  "(compilado sin libass); se omite quemar subtítulos. El .srt queda en "
                  "workspace/transcripcion/narracion.srt.", file=sys.stderr)
    cmd.append(str(final))
    _run(cmd)

    # Limpieza de intermedios.
    base.unlink(missing_ok=True)
    shutil.rmtree(tmp, ignore_errors=True)
    (outdir / "reporte_ensamblado.json").write_text(
        json.dumps({
            "formato": formato, "resolucion": f"{w}x{h}", "escenas": reporte,
            "objetivo_segundos": duracion_objetivo(guion),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return final


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ensamblar el video final (FFmpeg).")
    ap.add_argument("--guion", default="workspace/guion.json")
    ap.add_argument("--imagedir", default="workspace/imagenes")
    ap.add_argument("--audio", default="workspace/audio/narracion.mp3")
    ap.add_argument("--srt", default="workspace/transcripcion/narracion.srt")
    ap.add_argument("--outdir", default="workspace/video")
    ap.add_argument("--formato", default=None, choices=["vertical", "horizontal"],
                    help="Por defecto toma el formato del guion.")
    ap.add_argument("--salida", default="final.mp4", help="Nombre del archivo final.")
    args = ap.parse_args(argv)

    try:
        guion = cargar_guion(args.guion)
        formato = args.formato or guion["parametros"]["formato"]
        out = ensamblar(guion, Path(args.imagedir), Path(args.audio), Path(args.srt),
                        Path(args.outdir), formato, args.salida)
    except Exception as e:
        print(f"[ensamblar] Error: {e}", file=sys.stderr)
        return 1

    print(f"[ensamblar] OK -> {out}")
    print(f"[ensamblar] reporte -> {Path(args.outdir) / 'reporte_ensamblado.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

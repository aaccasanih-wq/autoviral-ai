"""Integra imágenes generadas manualmente (vía B) al pipeline AutoViral AI.

Vía B = el usuario genera las imágenes en la web (Qwen u otra IA) copiando/peando
los prompts de ``prompts.txt`` (adjuntando la referencia indicada en cada bloque)
y las descarga. Este script las copia a ``<sesión>/imagenes/`` con el nombrado
canónico ``MM_SS_<slug>.png`` (el mismo que usa ``generar_imagenes.py``), valida
cantidad/legibilidad y genera el ``contact_sheet.png`` para revisión.

Uso:
    python scripts/integrar_imagenes_manuales.py --guion workspace/03-09-26/tema/guion.json --desde ~/Downloads
    python scripts/integrar_imagenes_manuales.py --guion <sesión>/guion.json --desde ~/Downloads --mapa "1.png:escena-01,2.png:escena-02"

Mapeo:
    - Si los archivos se llaman ``1.png``..``N.png`` (tu flujo habitual), se mapean por
      número al orden de escenas (``1.png`` -> escena-01, etc.) sin necesidad de ``--mapa``.
    - Si no, usa ``--mapa "archivo:escena-id,..."`` o deja que se mapeen por orden
      alfabético (requiere que el conteo coincida con las escenas).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from guion import (cargar_guion, directorio_sesion, escenas, guardar_json,
                       nombre_imagen)
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from guion import (cargar_guion, directorio_sesion, escenas, guardar_json,  # type: ignore
                       nombre_imagen)

EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _es_imagen_valida(p: Path) -> bool:
    """Chequeo barato por firma mágica (sin dependencias extra)."""
    try:
        if not p.is_file() or p.stat().st_size < 1024:
            return False
        with open(p, "rb") as f:
            cab = f.read(16)
        if cab.startswith(b"\x89PNG"):
            return True
        if cab.startswith(b"\xff\xd8\xff"):
            return True
        if cab.startswith(b"RIFF") and b"WEBP" in cab:
            return True
        return False
    except OSError:
        return False


def _parsear_mapa(raw: str | None, escs: list[dict]) -> dict[str, str] | None:
    """``--mapa "1.png:escena-01,..."`` -> {escena_id: archivo}."""
    if not raw:
        return None
    ids = {e["id"] for e in escs}
    out: dict[str, str] = {}
    for par in raw.split(","):
        par = par.strip()
        if not par or ":" not in par:
            raise SystemExit(f"--mapa inválido: '{par}'. Formato archivo:escena-id.")
        arch, eid = (x.strip() for x in par.split(":", 1))
        if eid not in ids:
            raise SystemExit(f"--mapa: escena desconocida '{eid}'. IDs: {sorted(ids)}")
        out[eid] = arch
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Integrar imágenes manuales (vía B) al pipeline.")
    ap.add_argument("--guion", default="workspace/guion.json", help="Ruta al guion.json.")
    ap.add_argument("--desde", default=None,
                    help="Carpeta con las imágenes descargadas (ej. ~/Downloads).")
    ap.add_argument("--mapa", default=None,
                    help="Mapeo explícito archivo:escena-id separado por comas. "
                         "Si se omite y hay 1.png..N.png, se mapea por número.")
    ap.add_argument("--outdir", default=None,
                    help="Carpeta de salida. Por defecto <carpeta del guion>/imagenes.")
    ap.add_argument("--overwrite", action="store_true", help="Sobrescribe si ya existen.")
    ap.add_argument("--no-contact-sheet", action="store_true",
                    help="No genera el contact sheet de revisión.")
    args = ap.parse_args(argv)

    guion = cargar_guion(args.guion)
    session = directorio_sesion(args.guion)
    outdir = Path(args.outdir) if args.outdir else session / "imagenes"
    outdir.mkdir(parents=True, exist_ok=True)

    if not args.desde:
        print("[manuales] Falta --desde (carpeta con tus descargas, ej. ~/Downloads).",
              file=sys.stderr)
        return 2
    origen = Path(args.desde).expanduser()
    if not origen.is_dir():
        print(f"[manuales] No existe la carpeta: {origen}", file=sys.stderr)
        return 2

    escs = escenas(guion)
    mapa = _parsear_mapa(args.mapa, escs)

    # Flujo habitual del usuario: 1.png -> escena-01, ..., N.png -> escena-N.
    numeradas = {p.name: p for p in origen.glob("*") if p.suffix.lower() in EXTS}
    if mapa is None and all(f"{i}.png" in numeradas or f"{i}.jpg" in numeradas
                            for i in range(1, len(escs) + 1)):
        mapa = {}
        for i, esc in enumerate(escs, 1):
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                cand = origen / f"{i}{ext}"
                if cand.is_file():
                    mapa[esc["id"]] = cand.name
                    break

    if mapa is None:
        cands = sorted((p for p in origen.iterdir() if p.suffix.lower() in EXTS),
                       key=lambda p: p.name)
        if len(cands) != len(escs):
            print(f"[manuales] Hay {len(cands)} imágenes en {origen} pero {len(escs)} escenas. "
                  f"Usa --mapa archivo:escena-id o deja exactamente una imagen por escena.",
                  file=sys.stderr)
            return 2
        mapa = {esc["id"]: cands[i].name for i, esc in enumerate(escs)}

    faltan = [e["id"] for e in escs if e["id"] not in mapa]
    if faltan:
        print(f"[manuales] Sin archivo para escenas: {faltan}. Revisa --mapa.", file=sys.stderr)
        return 2

    copiadas: list[str] = []
    for esc in escs:
        src = origen / mapa[esc["id"]]
        if not _es_imagen_valida(src):
            print(f"[manuales] Archivo inválido o vacío: {src} (escena {esc['id']}).",
                  file=sys.stderr)
            return 2
        dst = outdir / nombre_imagen(esc)
        if dst.is_file() and not args.overwrite:
            print(f"[manuales] existe, omitido: {dst.name}")
        else:
            dst.write_bytes(src.read_bytes())
            print(f"[manuales] {src.name} -> {dst.name} ({esc['id']})")
        copiadas.append(dst.name)

    guardar_json({"origen": "manual", "fuente": str(origen),
                  "mapeo": mapa, "archivos": copiadas, "fallidas": []},
                 outdir / "reporte.json")

    if not args.no_contact_sheet:
        try:
            from generar_imagenes import generar_contact_sheet, _ruta_contact_sheet
            generar_contact_sheet(outdir, _ruta_contact_sheet(outdir))
        except Exception as e:
            print(f"[manuales] AVISO: no se pudo generar el contact sheet: {e}",
                  file=sys.stderr)

    print(f"[manuales] OK: {len(copiadas)} imágenes integradas en {outdir}.")
    print(f"[manuales] Siguiente: python scripts/ensamblar_video.py --guion {args.guion} --formato vertical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

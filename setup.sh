#!/usr/bin/env bash
# Setup de AutoViral AI: crea el entorno virtual, instala dependencias, prepara el .env
# y verifica el entorno. Pensado para que, tras clonar el repo, baste ejecutar:
#     bash setup.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

PY="python3"
command -v "$PY" >/dev/null 2>&1 || { echo "No se encontró python3. Instala Python 3.11+." >&2; exit 1; }

echo "==> Python: $($PY --version 2>&1)"

echo "==> Creando entorno virtual en .venv ..."
if [[ ! -d .venv ]]; then
  "$PY" -m venv .venv
else
  echo "    (.venv ya existe; se reutiliza)"
fi

echo "==> Instalando dependencias (requirements.txt) ..."
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt

echo "==> Preparando .env ..."
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "    Se creó .env desde .env.example. Edita .env y pega tu GEMINI_API_KEY."
else
  echo "    .env ya existe; no se sobrescribe."
fi

echo "==> Verificando FFmpeg ..."
if command -v ffmpeg >/dev/null 2>&1; then
  echo "    ffmpeg OK: $(ffmpeg -version 2>&1 | head -1)"
else
  echo "    AVISO: ffmpeg NO está en el PATH. Es necesario para ensamblar el video."
  echo "    En macOS:  brew install ffmpeg"
  echo "    En Ubuntu: sudo apt install ffmpeg"
  echo "    (edge-tts y la transcripción funcionan sin ffmpeg; el ensamblado no.)"
fi

echo "==> Chequeo del entorno ..."
.venv/bin/python scripts/verificar_entorno.py || true

cat <<'EOF'

✓ Listo. Siguientes pasos:

  1) Edita .env y pega tu GEMINI_API_KEY (https://aistudio.google.com/apikey).
     Si usarás el free tier de imágenes, pon NANO_BANANA_MODEL=gemini-2.5-flash-image.
  2) Activa el entorno:   source .venv/bin/activate
  3) Crea un guion con la Fase 1 (/ideacion-video) y guárdalo en workspace/guion.json.
  4) Produce el video:    python scripts/pipeline.py

  Más detalle en README.md.
EOF

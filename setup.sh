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

  1) Edita .env y pega tu API key de imágenes:
       gemini -> GEMINI_API_KEY  (https://aistudio.google.com/apikey)
       qwen   -> QWEN_API_KEY + QWEN_API_HOST (Alibaba Cloud DashScope)
     Elige el proveedor activo con IMAGEN_PROVEEDOR=gemini|qwen.
  2) Activa el entorno:   source .venv/bin/activate
  3) Crea un guion con la Fase 1 (/ideacion-video); se guarda en
       workspace/<fecha DD-MM-AA>/<tema>/guion.json  (una carpeta por video).
  4) Produce el video:    python scripts/pipeline.py --guion workspace/<fecha>/<tema>/guion.json

  Más detalle en README.md.
EOF

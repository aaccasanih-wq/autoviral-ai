# AutoViral AI

Pipeline **automatizado y modular** para crear videos cortos (YouTube Shorts, TikTok, Instagram
Reels) con IA: describe una idea en lenguaje natural y un agente orquesta toda la producción — de la
ideación y el guion al audio narrado, la transcripción con timestamps, la imagen por escena y el
video final editado.

> **Estado:** v1.0 · Licencia MIT · [Detalles y hoja de ruta](./PROJECT.md)

---

## Qué hace

El pipeline tiene **dos fases**, cada una gobernada por una **skill** que el agente carga según la
fase:

| Fase | Skill | Qué produce |
|---|---|---|
| **1 · Ideación Creativa** | `/ideacion-video` | Idea refinada + parámetros + **guion estructurado** (`guion.json`) confirmado. Nunca genera media. |
| **2 · Producción** | `/generacion-video` | Audio (`edge-tts`) → `.srt` (`faster-whisper`) → imagen por escena (Gemini *Nano Banana 2*) → **video final** (FFmpeg / Kinocut MCP) + revisión post-producción. |

El flujo es **agente-orquestado**: el agente interpreta lenguaje natural, carga la skill y ejecuta
cada etapa con herramientas locales (`scripts/*.py`) y servidores **MCP** (Gemini imagenes, Kinocut
edición).

---

## Stack

| Componente | Rol | Tipo |
|---|---|---|
| **edge-tts** | Audio narrado (TTS) | Local (Python) |
| **faster-whisper** | Transcripción a `.srt` con timestamps | Local (Python) |
| **Gemini Nano Banana 2** (`gemini-3.1-flash-image-preview`) | Imagen por escena | MCP (`nano-banana-2-mcp`) vía `npx` |
| **Kinocut** (`kino`) | Edición: concat, overlay, subtítulos, resize, quality gate | MCP local / CLI |
| **FFmpeg** | Motor multimedia subyacente | Dependencia del sistema |
| **Agente** (Claude Code · OpenCode · DeepSeek Harness) | Orquesta el pipeline | Cliente IA |

> **Costo:** `edge-tts`, `faster-whisper` y Kinocut son gratuitos/open-source. Gemini *Nano Banana 2*
> opera en el free tier de Google AI Studio. No hace falta suscripción de pago.

---

## Estructura

```
autoviral-ai/
├── skills/                     # Skills (bundle <nombre>/SKILL.md) — fuente canónica
│   ├── ideacion-video/SKILL.md
│   └── generacion-video/SKILL.md
├── scripts/                    # Herramientas locales del pipeline
│   ├── verificar_entorno.py    # Paso 1: chequeo de dependencias
│   ├── generar_audio.py        # Paso 2: edge-tts
│   ├── transcribir.py          # Paso 3: faster-whisper -> .srt
│   ├── generar_imagenes.py     # Paso 4: Gemini (Nano Banana 2)
│   ├── ensamblar_video.py      # Paso 5: FFmpeg
│   ├── pipeline.py             # Orquestador end-to-end
│   ├── verificar_entorno.py    # Paso 1: chequeo de dependencias
│   ├── guion.py                # Carga/validación del guion + utilidades
│   ├── empaquetar_skills.py    # Genera zips de skill para Claude Desktop
│   └── copiar_skills.sh        # Resincroniza las copias de skill (proyecto + global)
├── config/
│   ├── guion.example.json      # Esquema de guion (lo consume la Fase 2)
│   ├── mcp-nano-banana-2.json  # Servidor MCP de imagenes
│   ├── mcp-kinocut.json        # Servidor MCP de edición
│   └── settings.example.json
├── .mcp.json                   # Config MCP combinada para clientes de agente
├── workspace/                  # Artefactos generados (gitignored)
│   ├── audio/  transcripcion/  imagenes/  video/
├── dist/                       # Zips de skill para Claude Desktop
├── .dsh/skills/                # Skills (copias) para DeepSeek Harness — proyecto
├── .agents/skills/             # Skills (copias) vía config compartida de agentes
├── .github/workflows/          # (Futuro) CI del pipeline
├── PROJECT.md   README.md   LICENSE   requirements.txt   pyproject.toml
```

---

## Prerrequisitos

- **Python 3.9+** (Kinocut opcional requiere **3.11+**).
- **FFmpeg** en el PATH (requerido por el ensamblado y por Kinocut). En macOS:
  `brew install ffmpeg` (o usa tu gestor de paquetes).
- **Node.js + npx** (para el servidor MCP de imágenes `nano-banana-2-mcp`).
- **API key de Gemini** de [Google AI Studio](https://aistudio.google.com/apikey) (free tier).

### Instalar dependencias locales

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Verifica el entorno:

```bash
python scripts/verificar_entorno.py
```

---

## Uso del pipeline

### Fase 1 — Crear el guion

Carga la skill de ideación y describe tu idea (o pide propuestas). La skill refina, fija parámetros
(duración, formato, idioma, estilo, público) y escribe el guion en `workspace/guion.json`
(respetando el esquema de `config/guion.example.json`). Pedirá tu confirmación explícita.

### Fase 2 — Producir el video

Carga la skill de producción con el guion ya confirmado. El agente ejecuta las etapas en orden:

```bash
python scripts/verificar_entorno.py            # 1. chequeo
python scripts/generar_audio.py                # 2. audio (edge-tts)
python scripts/transcribir.py                  # 3. .srt (faster-whisper)
GEMINI_API_KEY=... python scripts/generar_imagenes.py   # 4a. imágenes (CLI)
# 4b. alternativa: llamar a la herramienta MCP generate_image por escena
python scripts/ensamblar_video.py              # 5. video (FFmpeg)
```

O todo de una vez con el orquestador:

```bash
GEMINI_API_KEY=... python scripts/pipeline.py   # ejecuta las 4 etapas
python scripts/pipeline.py --pasos ensamblado   # solo reensamblar (si ya hay media)
```

El video final queda en `workspace/video/final.mp4`. La skill presenta el resultado y permite
ajustes post-producción (cortes, reemplazo de escena, cambio de duración o de voz).

> **Imágenes vía MCP:** si prefieres que el agente llame a Gemini a través del servidor MCP (en
> lugar del script CLI), conecta `.mcp.json` y usa la herramienta `generate_image` por escena
> guardando cada resultado como `workspace/imagenes/MM_SS_descripcion.png`
> (`MM_SS` = `inicio_segundos` de la escena formateado como `00_05`; ej. `00_05_gancho.png`).

---

## Cargar las skills en los agentes

Cada skill es un bundle `<nombre>/SKILL.md` que define el comportamiento del agente en esa fase.

### Claude Code / OpenCode

En **Claude Code (CLI)** escribe `/ideacion-video` o `/generacion-video`. En **OpenCode**, el
mecanismo es similar (`/nombre`). Las skills viven en `skills/`.

### DeepSeek Harness

DeepSeek Harness descubre skills en estas rutas (nivel de proyecto y nivel de usuario):

- **Proyecto (versionable):** `<raíz-proyecto>/.dsh/skills/<nombre>/SKILL.md`
  y `<raíz-proyecto>/.agents/skills/<nombre>/SKILL.md`.
- **Global (todas las sesiones):** `~/.dsh/skills/<nombre>/SKILL.md`
  y `~/.agents/skills/<nombre>/SKILL.md`.

Este repo ya contiene copias instaladas en `.dsh/skills` y `.agents/skills` (proyecto) **y** en
`~/.dsh/skills` y `~/.agents/skills` (global). Al reiniciar (oir recargar) la sesión de DeepSeek
Harness, `ideacion-video` y `generacion-video` aparecen en el catálogo de skills y pueden invocarse
por nombre.

> Cada juego de archivos es una **copia** idéntica. Edítalas en `skills/` y, si cambias el contenido,
> resincroniza las copias con `bash scripts/copiar_skills.sh` (proyecto **y** global).

### Claude Desktop (`.zip`)

Los zips de distribución se generan y guardan en `dist/`:

- `dist/ideacion-video-skill.zip`
- `dist/generacion-video-skill.zip`

Cada zip sigue la estructura oficial (`skill.json`, `instructions.md`, `README.md`). Generar con:

```bash
# desde tu máquina (una vez que definas los metadatos en dist/) — o manualmente:
#   skill.json  + instructions.md + README.md en cada zip
```

## Publicación y branches

Sigue la política de `PROJECT.md`: **nunca** trabajes directamente en `main`. Crea una branch por
etapa (`setup/estructura-proyecto`, `feature/skill-ideacion-video`, …), haz commits descriptivos y
mergea vía Pull Request (GitHub Desktop o CLI).

---

## License

MIT — ver [LICENSE](./LICENSE).

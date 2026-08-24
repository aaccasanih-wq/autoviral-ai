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

- **Python 3.9+** — recomendado **3.11+** (para Kinocut y para evitar avisos de fin de vida útil en
  algunas librerías de Google).
- **FFmpeg** en el PATH (requerido por el ensamblado del video). En macOS:
  `brew install ffmpeg`; en Ubuntu: `sudo apt install ffmpeg`.
- **Node.js + npx** (para el servidor MCP de imágenes `nano-banana-2-mcp`).
- **API key de Gemini** de [Google AI Studio](https://aistudio.google.com/apikey).

### Instalación fácil (todo en uno)

Tras clonar el repo, ejecuta `setup.sh` desde la raíz: crea `.venv`, instala las dependencias,
prepara `.env` y verifica el entorno.

```bash
bash setup.sh
```

**Nota:** `setup.sh` **no** instala FFmpeg (es una dependencia del sistema). Si no lo tienes, el
pipeline funciona hasta la transcripción; el paso de ensamblado te pedirá instalarlo.

### Dónde van las claves API (`.env`)

Las credenciales van en un archivo **`.env`** en la raíz del proyecto (ya está en `.gitignore`, así
que nunca se sube a GitHub). Copia la plantilla y pega tu clave:

```bash
cp .env.example .env      # una sola vez
# edita .env y completa GEMINI_API_KEY=
```

`.env` ya trae valores por defecto sensatos y comentados:

| Variable | Uso | Default |
|---|---|---|
| `GEMINI_API_KEY` | Imágenes Gemini (script CLI) | *(vacía — complétala)* |
| `NANO_BANANA_MODEL` | Modelo de imagen | `gemini-3.1-flash-image-preview` |
| `EDGE_TTS_VOZ` | Voz de edge-tts | `es-ES-ElviraNeural` |
| `WHISPER_MODEL` | Modelo de whisper | `small` |

> **Servidor MCP de imágenes:** si además usas `.mcp.json` (p. ej. desde Claude Code/OpenCode), la
> clave va también en su campo `env.GEMINI_API_KEY` (ver `config/mcp-nano-banana-2.json`).

---

## Uso del pipeline

### Fase 1 — Crear el guion

Carga la skill de ideación y describe tu idea (o pide propuestas). La skill refina, fija parámetros
(duración, formato, idioma, estilo, público) y escribe el guion en `workspace/guion.json`
(respetando el esquema de `config/guion.example.json`). Pedirá tu confirmación explícita.

### Fase 2 — Producir el video

Carga la skill de producción con el guion ya confirmado. El agente ejecuta las etapas en orden
**sin intervenir** (ver el principio de "mínima intervención" en la skill) y te presenta el video
final:

```bash
python scripts/verificar_entorno.py            # 1. chequeo
python scripts/generar_audio.py                # 2. audio (edge-tts)
python scripts/transcribir.py                  # 3. .srt (faster-whisper)
python scripts/generar_imagenes.py             # 4a. imágenes (CLI, lee la clave de .env)
# 4b. alternativa: llamar a la herramienta MCP generate_image por escena
python scripts/ensamblar_video.py              # 5. video (FFmpeg)
```

O todo de una vez con el orquestador (lee los valores por defecto de `.env`):

```bash
python scripts/pipeline.py                     # ejecuta las 4 etapas
python scripts/pipeline.py --pasos ensamblado  # solo reensamblar (si ya hay media)
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

Cada zip sigue la estructura oficial (`skill.json`, `instructions.md`, `README.md`). Se generan con:

```bash
python scripts/empaquetar_skills.py   # -> dist/ideacion-video-skill.zip, dist/generacion-video-skill.zip
```

---

## FAQ y detalles

### ¿Qué usas para editar el video: Kinocut o FFmpeg?

Por defecto el pipeline usa **FFmpeg directamente** (script `scripts/ensamblar_video.py`), porque es
autocontenido y portátil. **Kinocut** es un **servidor MCP local** (`pip install kinocut`, se ejecuta
con `kino --mcp`) que envuelve FFmpeg con herramientas tipadas, *guardrails*, *Video Receipts* y
*quality gates*. Es la alternativa "guardrailed" y está descrita en la skill como opción B.

Ambos cumplen lo que pide el pipeline: concatenar las imágenes por escena (cada una con la duración
real de su escena), superponer el audio narrado, **quemar** los subtítulos (`.srt`), hacer **resize**
al formato (vertical 1080x1920 / horizontal 1920x1080) y exportar MP4 (H.264+AAC).

> Kinocut requiere **Python 3.11+** y FFmpeg. Si no usas Kinocut, la vía FFmpeg es la que funciona.

### ¿Cuánto tarda / recursos usa la transcripción (whisper)?

Depende del modelo (`--model` / `WHISPER_MODEL`) y de si hay GPU. En **CPU** (valores orientativos,
el tiempo crece ≈ lineal con la duración del audio, más una carga fija del modelo):

| Modelo | Peso | RAM aprox. | Tiempo por ~60 s de audio (CPU) | Precisión |
|---|---|---|---|---|
| `tiny` | ~75 MB | ~0.5 GB | ~5–15 s | baja |
| `base` | ~145 MB | ~0.7 GB | ~10–30 s | media-baja |
| `small` (default) | ~460 MB | ~1 GB | ~20–60 s | buena |
| `medium` | ~1.5 GB | ~3–5 GB | ~60–150 s | muy buena |
| `large-v3` | ~3 GB | ~6+ GB | ~150–300 s | máxima |

Para guiones cortos (15–60 s) el default **`small`** es el mejor equilibrio velocidad/calidad. La
primera ejecución descarga el modelo una sola vez (cache en `workspace/.cache_hf`). Si tienes GPU
(CUDA), se acelera mucho: usa `--device cuda --compute-type float16`.

### ¿Gemini "Nano Banana" es gratis? ¿Cuántas imágenes al día?

- **Nano Banana 2** (`gemini-3.1-flash-image-preview`) es un modelo **de pago / preview**; en el
  free tier suele no estar disponible o con límites mínimos.
- **Nano Banana** (`gemini-2.5-flash-image`) es la que típicamente tiene **free tier** en Google AI
  Studio. Para usarla cambia `NANO_BANANA_MODEL=gemini-2.5-flash-image` en `.env`.
- El free tier de Gemini no publica un número fijo de "imágenes/día": es una **cuota por minuto
  (RPM)** que depende del modelo y la región. Para un video de 30–60 s solo necesitas ~5–8 imágenes
  por video, así que incluso una cuota ajustada alcanza para varios videos al día. Confirma la cuota
  exacta de tu clave en el panel de **Rate limits** de [AI Studio](https://aistudio.google.com/apikey).

> Recomendación para no gastar: usa `gemini-2.5-flash-image` (free tier) salvo que necesites la
> calidad de Nano Banana 2; ambas se configuran en `.env`.

### ¿Cuántos tokens gasta el LLM del agente al correr el pipeline?

Con el principio de **mínima intervención** (la skill `generacion-video` manda a no editar ni "arreglar"
salidas), un video normal cuesta pocas llamadas: cargar la skill (~1–2k tokens), ejecutar el
orquestador y leer el output final, y preguntar. **Aproximadamente 5–15k tokens por video** en
conversación más las salidas de los comandos. Si un script fallara y el agente tuviera que depurar,
crecería a 20–60k; por eso el diseño apunta a que los scripts funcionen solos y el agente solo
**espere el resultado y pregunte**.

## Publicación y branches

Sigue la política de `PROJECT.md`: **nunca** trabajes directamente en `main`. Crea una branch por
etapa (`setup/estructura-proyecto`, `feature/skill-ideacion-video`, …), haz commits descriptivos y
mergea vía Pull Request (GitHub Desktop o CLI).

---

## License

MIT — ver [LICENSE](./LICENSE).

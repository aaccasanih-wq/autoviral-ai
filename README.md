# AutoViral AI

Pipeline **automatizado y modular** para crear videos cortos (YouTube Shorts, TikTok, Instagram
Reels) con IA: describe una idea en lenguaje natural y un agente orquesta toda la producción — de la
ideación y el guion al audio narrado, la transcripción con timestamps, la imagen por escena y el
video final editado.

> **Estado:** v1.1 · Licencia MIT · [Detalles y hoja de ruta](./PROJECT.md)

---

## Qué hace

El pipeline tiene **dos fases + catálogo de estilos**, cada una gobernada por una **skill**:

| Fase | Skill | Qué produce |
|---|---|---|
| **1 · Ideación Creativa** | `/ideacion-video` | Idea refinada + `estilo_id` + `motor TTS (gcp default)` + **guion** (`guion.json`) confirmado. Nunca genera media. |
| **2 · Producción** | `/generacion-video` | Audio (`gcp` default, fallback `edge`) → `.srt/.ass` (`faster-whisper`) → imagen por escena (**Gemini** o **Qwen**, con estilo + anti-drift) → aprobación (contact sheet) → **video final** (FFmpeg con subtítulos quemados) + revisión. |
| **Estilos** | `/creacion-estilo` | Guarda/crea estilos reutilizables en `estilos/<id>/` (look + voz) a partir de referencias + muestra de voz. |

El flujo es **agente-orquestado**: el agente interpreta lenguaje natural, carga la skill y ejecuta
cada etapa con herramientas locales (`scripts/*.py`) y servidores **MCP** (Gemini imagenes, Kinocut
edición).

---

## Stack

| Componente | Rol | Tipo |
|---|---|---|
| **Google Cloud TTS / edge-tts** | Audio narrado (TTS default **`gcp`**, fallback `edge`) | gcp: mejor calidad, free tier mensual · edge: gratis sin clave |
| **faster-whisper** | Transcripción a `.srt/.ass` con timestamps palabra-a-palabra | Local (Python) |
| **Gemini Nano Banana 2** (`gemini-3.1-flash-image-preview`) | Imagen por escena | MCP (`nano-banana-2-mcp`) vía `npx` |
| **Alibaba Qwen** (`qwen-image-2.0/3.0`) | Imagen por escena — con **seed por video + estilos reutilizables + anti-drift** | DashScope (HTTP) |
| **Kinocut** (`kino`) | Edición alternativa: concat, overlay, subtítulos, resize, quality gate | MCP local / CLI (opcional) |
| **FFmpeg (imageio-ffmpeg)** | Motor multimedia + subtítulos quemados (libass) | Fallback automático sin instalar nada |
| **Agente** (Claude Code · OpenCode · DeepSeek Harness) | Orquesta el pipeline | Cliente IA |

> **Costo:** `edge-tts`, `faster-whisper` y Kinocut son gratuitos/open-source. Gemini *Nano Banana 2*
> opera en el free tier de Google AI Studio. No hace falta suscripción de pago. Para TTS premium,
> **Google Cloud TTS** ofrece free tier mensual permanente (WaveNet 4M chars, Neural2 1M chars).

---

## Estructura

```
autoviral-ai/
├── skills/                     # Skills (bundle <nombre>/SKILL.md) — fuente canónica
│   ├── ideacion-video/SKILL.md
│   ├── generacion-video/SKILL.md
│   └── creacion-estilo/SKILL.md
├── estilos/                    # Catálogo reutilizable (no hardcodeado en skills)
│   ├── catalogo.json           # índice {id, nombre, carpeta}
│   ├── tom-jerry/              # estilo.json + tts.json + referencias/
│   └── palitos-doodle/
├── scripts/                    # Herramientas locales del pipeline
│   ├── verificar_entorno.py    # Paso 1: chequeo de dependencias
│   ├── gestionar_estilos.py    # Listar/mostrar/crear/validar estilos
│   ├── generar_audio.py        # Paso 2: TTS default gcp, fallback edge
│   ├── transcribir.py          # Paso 3: faster-whisper -> .srt/.ass
│   ├── generar_imagenes.py     # Paso 4: imágenes (Gemini o Qwen + --estilo-id anti-drift)
│   ├── ensamblar_video.py      # Paso 5: FFmpeg con subtítulos quemados
│   ├── pipeline.py             # Orquestador end-to-end
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

- **Python 3.11+** — requerido (3.9 funciona pero 3.11+ evita avisos y es necesario para Kinocut opcional).
  Descarga desde [python.org/downloads](https://www.python.org/downloads/) y marca **Add to PATH**.
- **FFmpeg** — **opcional**: si no está en el PATH, `setup.sh`/`setup.bat` vinculan automáticamente
  el binario de `imageio-ffmpeg` (ffmpeg 7.1 con libass para subtítulos quemados). Solo instálalo
  manual si quieres el binario del sistema:
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: `winget install ffmpeg` — cierra y reabre la terminal después
- **Node.js 18+ + npx** — solo si usarás el servidor MCP `nano-banana-2-mcp`. Si usas los scripts
  (`generar_imagenes.py` con Gemini/Qwen por HTTP) no lo necesitas.
- **API keys** (cada persona usa las suyas, nunca se suben — `.env` está en `.gitignore`):
  - Imágenes: `GEMINI_API_KEY` ([AI Studio](https://aistudio.google.com/apikey)) o `QWEN_API_KEY`+`QWEN_API_HOST` (Alibaba).
  - Voz default `gcp`: `GCP_TTS_API_KEY` (Cloud Text-to-Speech API + billing; free tier Neural2 1M chars/mes).

> **Clonar el repo:** puedes clonarlo en cualquier carpeta (`git clone
> https://github.com/aaccasanih-wq/autoviral-ai.git`); el pipeline usa rutas relativas y funciona
> en cualquier ubicación. Recomendado: una ruta corta y **sin espacios ni acentos**, p. ej.
> `C:\Proyectos\autoviral-ai` (Windows) o `~/Desktop/autoviral-ai` (macOS/Linux).
>
> **Importante:** cada persona usa **sus propias claves API**. El archivo `.env` no se sube al repo
> (está en `.gitignore`): cada quien lo crea desde `.env.example` y pega sus claves de Gemini /
> Qwen / Google Cloud TTS.

### Instalación fácil (todo en uno)

Tras clonar el repo, desde la raíz del proyecto:

```bash
# macOS / Linux / Git Bash en Windows:
bash setup.sh

# Windows (CMD o PowerShell, sin necesidad de Git Bash):
setup.bat
```

Crea `.venv`, instala las dependencias, prepara `.env` (desde `.env.example`), vincula FFmpeg
fallback (imageio-ffmpeg con libass) y verifica el entorno.

**FFmpeg:** no necesitas instalarlo manual: si no está en el PATH, el setup lo vincula desde
`imageio-ffmpeg` a `.venv/bin/ffmpeg` (macOS/Linux) o `.venv\Scripts\ffmpeg.exe` (Windows).

**Notas Windows (probado con `setup.bat`):**
- Usa **PowerShell** como usuario normal (no administrador). Si PowerShell bloquea scripts:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` una sola vez.
- Clona en ruta corta **sin espacios ni acentos**, ej. `C:\Proyectos\autoviral-ai`.
- Para activar el venv: `.venv\Scripts\Activate.ps1` (PowerShell) o `.venv\Scripts\activate.bat` (CMD).
  O llama directo sin activar: `.venv\Scripts\python.exe scripts\verificar_entorno.py`.
- `setup.bat` es equivalente a `setup.sh`; los `.sh` (`scripts/copiar_skills.sh`) requieren **Git Bash**
  (viene con Git para Windows) — en Windows sin Git Bash usa `setup.bat` y copia skills manual si editas `skills/`.
- `faster-whisper` (`small` ~460MB, ~1GB RAM) y TTS funcionan en CPU. Si tu laptop es básica, usa
  `WHISPER_MODEL=tiny` o `base` en `.env` para transcribir más rápido.
- `py -3` es el launcher de Python en Windows (`python3` en macOS/Linux).

### Dónde van las claves API (`.env`)

Las credenciales van en un archivo **`.env`** en la raíz del proyecto (ya está en `.gitignore`, así
que nunca se sube a GitHub). Copia la plantilla y pega tus claves (solo una vez):

```bash
# macOS / Linux / Git Bash:
cp .env.example .env
# Windows (CMD o PowerShell):
copy .env.example .env
# Luego edita .env con Bloc de notas/VS Code y completa tus claves.
```

`.env` ya trae valores por defecto sensatos y comentados:

| Variable | Uso | Default |
|---|---|---|
| `IMAGEN_PROVEEDOR` | Proveedor de imágenes: `gemini` o `qwen` | `gemini` |
| `GEMINI_API_KEY` | Clave de imágenes Gemini (si `IMAGEN_PROVEEDOR=gemini`) | *(vacía — complétala)* |
| `NANO_BANANA_MODEL` | Modelo de imagen Gemini | `gemini-3.1-flash-image-preview` |
| `QWEN_API_KEY` | Clave de imágenes Alibaba Qwen (si `IMAGEN_PROVEEDOR=qwen`) | *(vacía)* |
| `QWEN_API_HOST` | Host DashScope de tu workspace Qwen | `dashscope.aliyuncs.com` |
| `QWEN_IMAGE_MODEL` | Modelo Qwen | `qwen-image-2.0` |
| `QWEN_RPM` | Máx. peticiones/min a Qwen (el script las espacia) | `2` (free tier `qwen-image-2.0`; `3.0` → `5`) |
| `IMAGEN_SEED` | Seed fija de imágenes; vacía = auto-derivada del título (misma idea = misma seed) | *(vacía)* |
| `QWEN_PROMPT_EXTEND` | Reescritura del prompt por Qwen; `false` (default) = máxima consistencia entre escenas | `false` |
| `TTS_MOTOR` | Motor TTS default **`gcp`**; `edge` solo fallback o a pedido. La Fase 1 pregunta: “¿confirmas `gcp` o cambias a `edge`?” | `gcp` |
| `GCP_TTS_API_KEY` | Clave de Google Cloud Text-to-Speech (motor `gcp` default) | *(vacía — complétala)* |
| `GCP_TTS_VOZ` | Voz default gcp (se sobrescribe por estilo: `estilos/<id>/tts.json`) | `es-ES-Neural2-F` |
| `EDGE_TTS_VOZ` | Voz fallback edge (si no hay API key o se pide `edge`) | `es-ES-ElviraNeural` |
| `WHISPER_MODEL` | Modelo de whisper | `small` |

> **Servidor MCP de imágenes:** si además usas `.mcp.json` (p. ej. desde Claude Code/OpenCode), la
> clave va también en su campo `env.GEMINI_API_KEY` (ver `config/mcp-nano-banana-2.json`).

---

## Uso del pipeline

### Estructura de carpetas por video

Cada video vive en su **propia carpeta de sesión**, para que un video no pise a otro:

```
workspace/
└── 24-08-26/                     # carpeta del día (DD-MM-AA)
    └── inflacion_y_deuda/        # una carpeta por idea/video (slug sin acentos)
        ├── guion.json            # el guion confirmado
        ├── prompts.txt           # prompts de imagen editables a mano
        ├── audio/ transcripcion/ imagenes/ revision/ video/
```

El **directorio de sesión es la carpeta donde está `guion.json`**. Todos los scripts derivan sus
rutas de ahí al pasarles `--guion <sesión>/guion.json`, así no hay que descubrir cada carpeta con
tool calls.

### Fase 1 — Crear el guion

Carga la skill de ideación y describe tu idea (o pide propuestas). La skill refina, fija parámetros
(duración, formato, idioma, estilo, público) y **crea la carpeta de sesión**
(`workspace/<fecha>/<tema>/`) y escribe allí `guion.json` (respetando el esquema de
`config/guion.example.json`). Pedirá tu confirmación explícita y te dirá la ruta exacta.

### Fase 2 — Producir el video

Carga la skill de producción con el guion ya confirmado (pásale `--guion <sesión>/guion.json`). En
lugar de `workspace/...`, todas las rutas se derivan de la carpeta de la sesión:

```bash
python scripts/verificar_entorno.py                             # 1. chequeo
python scripts/gestionar_estilos.py --listar                    # 1b. ver estilos guardados
python scripts/generar_audio.py --guion <sesión>/guion.json     # 2. audio (TTS default gcp)
python scripts/transcribir.py --audio <sesión>/audio/narracion.mp3 \
  --outdir <sesión>/transcripcion                               # 3. .srt/.ass (faster-whisper)
python scripts/generar_imagenes.py --guion <sesión>/guion.json --export-prompts  # 4a. prompts editables
python scripts/generar_imagenes.py --guion <sesión>/guion.json  # 4b. imágenes (usa prompts.txt + estilo_id)
python scripts/generar_imagenes.py --guion <sesión>/guion.json --contact-sheet  # 4c. montaje
python scripts/ensamblar_video.py --guion <sesión>/guion.json   # 5. video con subtítulos quemados — tras aprobar
```

O el orquestador:

```bash
python scripts/pipeline.py --guion <sesión>/guion.json
python scripts/pipeline.py --guion <sesión>/guion.json --pasos ensamblado
```

**Dos aprobaciones obligatorias** antes de ensamblar (ambas las consulta la skill mediante el
contact sheet / panel visual):

1. **Prompts de imagen** (`<sesión>/prompts.txt`): el agente los muestra y pregunta si están bien.
   Si no, los ajusta él o **el usuario los edita a mano** en `prompts.txt` (recomendado: es un txt
   fácil de editar).
2. **Imágenes** (`<sesión>/revision/contact_sheet.png`): el agente muestra el montaje y pregunta
   por estilo/colores/fondos. Si no hay visto bueno, regenera (con `--estilo` o `--solo escena-XX`).

El video final queda en `<sesión>/video/final.mp4` **con subtítulos TikTok quemados por defecto**
(palabra-a-palabra amarillo + hook rojo superior, vía `narracion.ass` + ffmpeg con libass de
`imageio-ffmpeg`). El `.srt` queda como sidecar. Para sin subtítulos: `--no-subtitulos` o
`parametros.subtitulos.enabled=false`.

> **Imágenes vía MCP:** si prefieres que el agente llame a Gemini a través del servidor MCP (en
> lugar del script CLI), conecta `.mcp.json` y usa la herramienta `generate_image` por escena
> guardando cada resultado como `workspace/imagenes/MM_SS_descripcion.png`
> (`MM_SS` = `inicio_segundos` de la escena formateado como `00_05`; ej. `00_05_gancho.png`).

### Cambiar de proveedor de imágenes (Gemini ↔ Qwen)

El paso de imágenes es **independiente del proveedor**. Cambia el activo con la variable
`IMAGEN_PROVEEDOR` del `.env` o con `--proveedor` al ejecutar:

```bash
# Gemini (Google AI Studio / Nano Banana)
GEMINI_API_KEY=... python scripts/generar_imagenes.py --proveedor gemini \
  --model gemini-3.1-flash-image-preview --overwrite

# Alibaba Cloud DashScope / Qwen (deja IMAGEN_PROVEEDOR=qwen en .env, o pásalo por flag)
QWEN_API_KEY=... QWEN_API_HOST=ws-emxfi567101fw62r.ap-southeast-1.maas.aliyuncs.com \
  python scripts/generar_imagenes.py --proveedor qwen --model qwen-image-3.0 --overwrite
```

El orquestador respeta el proveedor activo:

```bash
python scripts/pipeline.py --proveedor qwen --model qwen-image-3.0
```

### Motor de TTS (default `gcp`, fallback `edge`)

El paso de audio usa por defecto **Google Cloud TTS** (mejor calidad). `edge-tts` es fallback
gratis sin clave o a pedido explícito.

| Motor | Clave `.env` | Calidad | Costo |
|---|---|---|---|
| `gcp` (default) | `GCP_TTS_API_KEY` | Muy buena (Neural2/WaveNet/Chirp 3 HD) | **Free tier mensual**: WaveNet 4M, Neural2 1M (≈ USD 16), Chirp 3 HD 1M; luego USD 4–30/1M |
| `edge` (fallback) | *(ninguna)* | Buena | Gratis — Microsoft Edge Read-Aloud (online, sin API key) |

**Selección:** default `gcp` (`TTS_MOTOR=gcp`). Si no hay API key, fallback automático a `edge`
con aviso (no falla). Prioridad: **CLI > guion.tts > estilos/<id>/tts.json > `.env` > `gcp`**.
La Fase 1 **pregunta siempre**: “Uso `gcp` por defecto, ¿confirmas o cambias a `edge`?”.

**Tono según estilo:** si el guion trae `estilo_id`, se usan su `voz_en/voz_es + rate/pitch`
(ej. tom-jerry `+3%/+2` juguetón, palitos `+5%/0` ingenioso). Si es ad-hoc, según emoción:
misterio `rate -10% pitch -2`, motivación `rate +5%`.

**Cómo obtener la API key de Google Cloud TTS:**

1. Crea un proyecto en [console.cloud.google.com](https://console.cloud.google.com) (requiere
   billing activo — el free tier mensual se mantiene sin cargo dentro de la cuota).
2. *APIs y servicios → Biblioteca* → habilita **Cloud Text-to-Speech API**.
3. *APIs y servicios → Credenciales → Crear credenciales → Clave de API*.
4. Pégala en `.env`: `GCP_TTS_API_KEY=AIza...` y (opcional) `GCP_TTS_VOZ=es-ES-Neural2-F`.
5. Verifica con `python scripts/verificar_entorno.py` (sección *Motores TTS*).

> Con 1M chars/mes gratis (Neural2) puedes narrar ~20 horas de audio al mes: de sobra para
> varios videos semanales. Otras alternativas con free tier: Azure TTS F0 (500k chars/mes),
> ElevenLabs (~10k chars/mes, calidad top), Amazon Polly (1M chars/mes solo el primer año);
> OpenAI TTS no tiene free tier.

### Catálogo de estilos reutilizables (`estilos/`)

No digas “estilo lúgubre con Batman” solo en texto: guarda el look + voz una vez y reutilízalo por `id`.

```bash
python scripts/gestionar_estilos.py --listar          # ver tom-jerry, palitos-doodle, ...
python scripts/gestionar_estilos.py --mostrar palitos-doodle
python scripts/gestionar_estilos.py --validar
# Crear uno nuevo desde referencias + descripción de voz:
python scripts/gestionar_estilos.py --crear --id batman-90s --nombre "Batman 90s" \
  --descripcion "Comic 90s lúgubre" --referencia "/ruta/a/comic.png" \
  --voz-descripcion "narrador grave noir, pausado"
```

Cada `estilos/<id>/` tiene `estilo.json` (fichas CHARACTER/STYLE + `anti_drift` + hex),
`tts.json` (motor `gcp` + voces EN/ES + rate/pitch) y `referencias/` (se envían reales cada escena).
En ideación el agente pregunta qué estilo usar y deja `parametros.estilo_id`; en producción
`--estilo-id` lo inyecta solo. Para crear/editar con guía usa la skill `/creacion-estilo`.
Incluidos: `tom-jerry` (fondo `#BFE0EC`, Tom jersey oliva + Jerry tuxedo, voz cartoon `gcp +3%/+2`)
y `palitos-doodle` (fondo blanco, protagonista siempre polo amarillo `#FFD93D`, voz ingeniosa `+5%/0`).

### Anti-drift Qwen (por qué ya no cambia el polo/gorra)

Qwen olvida el outfit entre llamadas. El catálogo lo fija en 5 capas:

1. Outfit ÚNICO en `character_ficha` (`ALWAYS wearing` + hex + `NO shoes/hat/glasses`).
2. Fichas verbatim en CADA prompt + `anti_drift` al final (Fase 1 + `--estilo-id` automático).
3. Misma `seed` por video + `prompt_extend=false`.
4. Referencia(s) reales en cada llamada (máx 3 en Qwen).
5. Contact sheet antes de ensamblar; si una escena driftea, `--solo escena-XX --overwrite`.

Secundarios con color fijo distinto al protagonista (nunca amarillo en palitos).

### Estilo ad-hoc (sin guardar)

Para un video puntual puedes seguir con `--referencia` suelto (puede estar fuera del proyecto)
o `parametros.imagen_referencia` en el guion. Pero si lo reutilizarás, guárdalo con `/creacion-estilo`.

### Consistencia de personaje con seed (Qwen)

`qwen-image-2.0/3.0` soporta el parámetro `seed` (0–2147483647): la misma seed produce resultados
**más consistentes** (no idénticos). El pipeline usa **una seed por video** para todas sus escenas:

1. `--seed 12345` (CLI), o
2. `IMAGEN_SEED` en `.env`, o
3. **auto-derivada del título del guion** (crc32): la misma idea siempre usa la misma seed; otra
   idea usa otra distinta. Queda registrada en `<sesión>/imagenes/reporte.json`.

La seed estabiliza estilo y paleta. Para que el **personaje** sea idéntico entre escenas, la skill
de ideación repite además una *ficha de personaje* literal en cada `prompt_imagen` y se envían las
imágenes de referencia. `prompt_extend` está **desactivado por defecto**
(`QWEN_PROMPT_EXTEND=false`) para que el modelo no reescriba los prompts (cada reescritura añade
varianza). Gemini no soporta seed (se ignora con un aviso).

### Edición y efectos (Ken Burns + transiciones)

El ensamblado no es un simple concat: aplica **efectos de edición** con FFmpeg y mantiene el audio
perfectamente sincronizado (cada segmento se extiende la duración de su transición y el `offset`
del `xfade` se calcula sobre los tiempos del guion).

| Tipo | Valores |
|---|---|
| Movimiento por escena (`zoompan`) | `static`, `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `kenburns` |
| Transición de salida (`xfade`) | `none` (corte seco), `fade`, `dissolve`, `wipeleft`, `slideup`, `circleopen` |
| Grading | `none`, `warm`, `cool` |
| Fades globales | entrada 0.5s / salida 0.6s |

**Presets** (`--preset`): `suave` (**default**: Ken Burns lento + crossfade 0.4s — look editorial
para historias), `dinamico` (movimientos marcados + transiciones variadas — humor/gaming) y `off`
(comportamiento v1: imagen fija + concat).

**Efectos por escena** (decisión creativa de la Fase 1; el agente puede refinarlos en Fase 2):

```json
{
  "id": "escena-06",
  "efectos": {"movimiento": "zoom_in", "intensidad": 1.15, "transicion": "dissolve",
              "transicion_duracion": 0.4, "grade": "cool"}
}
```

Prioridad: `efectos` de la escena > `--preset` > `off`. Catálogo completo:
`python scripts/ensamblar_video.py --list-efectos`. Los efectos aplicados quedan registrados en
`<sesión>/video/reporte_ensamblado.json`. Para ajustar ("más zoom en la escena 6", "transición más
lenta") edita `efectos` en el guion y re-ensambla — no regenera imágenes ni audio.

---

## Cargar las skills en los agentes

Cada skill es un bundle `<nombre>/SKILL.md` que define el comportamiento del agente en esa fase.

### Claude Code / OpenCode

Claude Code y OpenCode **no** leen la carpeta `skills/` ni las raíces DSH: descubren las skills en
**`.claude/skills/<nombre>/SKILL.md`** (proyecto) o **`~/.claude/skills/<nombre>/SKILL.md`**
(global). Este repo ya incluye copias en `.claude/skills/` (proyecto, versionable) y el script las
sincroniza también a `~/.claude/skills/`.

Para usarlas en Claude Code, ábrelo en este directorio (o `cd` a él). Al pedir algo que encaje con
la `description` de la skill (p. ej. "genera el video a partir del guion"), Claude Code la carga
automáticamente y sigue su procedimiento (que ya le indica que tiene acceso a Bash, dónde está el
proyecto y que use `.venv`).

### DeepSeek Harness

DeepSeek Harness descubre skills en estas rutas (nivel de proyecto y nivel de usuario):

- **Proyecto (versionable):** `<raíz-proyecto>/.dsh/skills/<nombre>/SKILL.md`
  y `<raíz-proyecto>/.agents/skills/<nombre>/SKILL.md`.
- **Global (todas las sesiones):** `~/.dsh/skills/<nombre>/SKILL.md`
  y `~/.agents/skills/<nombre>/SKILL.md`.

Este repo ya contiene copias instaladas en `.dsh/skills` y `.agents/skills` (proyecto) **y** en
`~/.dsh/skills` y `~/.agents/skills` (global). Al reiniciar la sesión, `ideacion-video`,
`generacion-video` y `creacion-estilo` aparecen en el catálogo y pueden invocarse por nombre.

> Cada juego es una **copia** idéntica. Edítalas en `skills/` y resincroniza con
> `bash scripts/copiar_skills.sh` (proyecto **y** global). En Windows sin Git Bash, copia manual
> `skills/<nombre>/SKILL.md` → `.claude/skills/<nombre>/SKILL.md` etc.

### Claude Desktop (`.zip`)

Los zips de distribución se generan y guardan en `dist/`:

- `dist/ideacion-video-skill.zip`
- `dist/generacion-video-skill.zip`
- `dist/creacion-estilo-skill.zip`

Cada zip usa la **estructura de skill de Claude Desktop**: una **carpeta con el nombre de la skill**
(ej. `ideacion-video/`) y dentro su **`SKILL.md`** (definición completa con frontmatter). No va un
plano de `skill.json`/`instructions.md`/`README.md`.

```bash
python scripts/empaquetar_skills.py   # -> dist/*-skill.zip (3 zips, incluye creacion-estilo)
```

Los tres `SKILL.md` indican al agente que tiene disponible el conector **Desktop Commander**
(ejecución de código/bash) en el equipo del usuario. `generacion-video` lo usa para correr los
scripts del pipeline; `ideacion-video` recuerda que, pese a disponer del conector, **nunca** ejecuta
comandos (es solo ideación).

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

> **¿Y si Gemini no tiene cuota?** El pipeline ya no depende solo de Gemini: con
> `IMAGEN_PROVEEDOR=qwen` usa **Alibaba Cloud DashScope** (`qwen-image-3.0` / `qwen-image-3.0-pro`),
> que en el modelo base suele tener un *free tier* por workspace. Configura `QWEN_API_KEY` y
> `QWEN_API_HOST` en `.env` (la clave aparece en el CSV `Default Workspace-apiKey-.csv`:
> `apiKey` → `QWEN_API_KEY`, `apiHost` → `QWEN_API_HOST`).

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

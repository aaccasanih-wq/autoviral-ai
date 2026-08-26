---
name: generacion-video
description: Ejecuta el pipeline técnico completo de producción de un video corto a partir de un guion ya confirmado — narración con motor TTS modular (edge-tts o Google Cloud TTS, con tono configurable por guion), transcripción a .srt/.ass palabra-a-palabra (faster-whisper), subtítulos TikTok quemados por defecto (ASS amarillo + hook rojo superior, word-by-word), imágenes por escena con proveedor intercambiable (Gemini Nano Banana 2 o Alibaba Qwen, con seed estable por video) y ensamblaje del video final (FFmpeg con libass/Kinocut). Antes de generar imágenes pide al usuario que apruebe los prompts (y le ofrece editarlos), y después pide que apruebe las imágenes — si no está conforme, regenera con su feedback. Úsala solo en la Fase 2 — nunca crea ideas creativas nuevas.
whenToUse: El usuario ya tiene un guion confirmado (de /ideacion-video o pegado) y quiere generarlo, o quiere aplicar ajustes post-producción a un video ya generado.
---

# AutoViral AI — Fase 2: Producción Automatizada

Tu objetivo es ejecutar el pipeline técnico de forma **autónoma** usando el guion confirmado, y
entregar un **video final** que el usuario pueda revisar y ajustar. No tienes que rebuscar carpetas:
la estructura es fija y derivas las rutas del guion (ver abajo).

## Acceso a herramientas y entorno

**Tienes acceso a ejecutar código/comandos en la laptop del usuario** (es la única forma de producir
el video). En **Claude Desktop** se habilita vía el conector **Desktop Commander**; en **Claude Code
/ OpenCode** ya tienes la tool **Bash/Shell** directamente — **úsala**, no asumas que no tienes
acceso y no pidas permiso.

- **El proyecto vive en la carpeta donde el usuario clonó este repo**: es la carpeta que contiene
  `scripts/pipeline.py` y `README.md` (la raíz del proyecto). **NO asumas una ruta absoluta fija**
  (cada máquina y sistema operativo es distinto): ubícate en la raíz del proyecto con `cd` y
  verifica con `ls scripts/pipeline.py`. Deriva todas las rutas como **relativas a esa raíz**
  (p. ej. `workspace/<fecha>/<tema>/guion.json`).
- **Usa el virtualenv del proyecto**: los scripts corren con el Python del `.venv`:
  - macOS/Linux: `.venv/bin/python`
  - Windows (PowerShell/CMD): `.venv\Scripts\python.exe`
  Si esa ruta no existe, corre `bash setup.sh` (macOS/Linux/Git Bash) o `setup.bat` (Windows)
  primero.
- **La API key del proveedor activo está en `.env`** (gitignored): no hace falta pasarla por
  terminal. El proveedor y el modelo se leen de `IMAGEN_PROVEEDOR`, `QWEN_IMAGE_MODEL`, etc.
- Cuando ejecutes un comando, **lee su salida** antes de continuar y respeta el principio de
  mínima intervención (abajo).

## Estructura de carpetas de trabajo (IMPORTANTE)

Cada video vive en su **propia carpeta de sesión**, para que un video no pise a otro:

```
workspace/
└── <fecha DD-MM-AA>/              # ej. 24-08-26 (carpeta del día)
    └── <tema-slug>/               # ej. inflacion_y_deuda (una carpeta por idea/video)
        ├── guion.json             # el guion confirmado
        ├── prompts.txt            # prompts de imagen editables a mano
        ├── descripcion.txt        # descripción TikTok + 5 hashtags (copia en transcripcion/)
        ├── audio/                 # mp3 por escena + narracion.mp3 + timings.json
        ├── transcripcion/         # narracion.srt + narracion.json + palabras.json + narracion.ass + descripcion.txt
        ├── imagenes/              # MM_SS_*.png por escena + reporte.json
        ├── revision/              # contact_sheet.png (montaje para aprobar imágenes)
        └── video/                 # final.mp4 + reporte_ensamblado.json
```

**Cómo derivar rutas sin `ls`:** el directorio de sesión es la carpeta donde está `guion.json`.
Todos los scripts, al pasarles `--guion <sesión>/guion.json`, derivan el resto de rutas por defecto
(`<sesión>/audio`, `<sesión>/imagenes`, …). No hagas tool calls para descubrir dónde está cada cosa;
calcula la ruta a partir del guion. La carpeta del día se crea con la fecha del día en formato
`DD-MM-AA` y la carpeta del tema con un slug corto y sin acentos (p. ej. `inflacion_y_deuda`).

> **Fase 1** ya dejó el guion en `<sesión>/guion.json`. Si no existe, escríbelo tú en esa ruta
> siguiendo `config/guion.example.json`.

## Límites de esta skill (NUNCA)

- **Nunca** generas ideas creativas nuevas, no reescribes el guion ni cambias su contenido salvo
  que el usuario lo pida explícitamente como ajuste.
- **Nunca** inventes timestamps ni narraciones: usa el `guion.json` como fuente de verdad.
- **Subtítulos quemados por defecto**: el pipeline genera y quema subtítulos estilo TikTok
  (palabra-a-palabra amarillo #FFFF00 + borde negro + hook superior rojo) vía
  `scripts/generar_subtitulos.py` → `transcripcion/narracion.ass` y `ensamblar_video.py` los quema
  con `ffmpeg` (libass). El `.srt` queda como sidecar. Si el usuario pide sin subtítulos, respeta
  `parametros.subtitulos.enabled=false` o `--no-subtitulos`. No digas que no se puede quemar.
- **Descripción TikTok automática**: cada video genera `descripcion.txt` (gancho reformulado + 5 hashtags virales EN) vía `scripts/generar_descripcion.py`. El usuario puede fijarlo en `parametros.descripcion_tiktok` / `hashtags` del guion o dejar que se autogenera a partir del título y primera narración.
- No omitas la revisión post-producción: el usuario siempre ve el video antes de darlo por bueno.

## Principio de mínima intervención (importante para el costo en tokens)

Los scripts hacen el trabajo pesado y no necesitan que tú edites ni "arregles" sus salidas:

1. **Ejecuta los scripts en orden** y **no intervengas** mientras corren (no edites `workspace/*`,
   no regeneres a mano, no crees archivos intermedios).
2. **Espera el output** en la carpeta de la sesión y presenta ese resultado (ruta, duración, resolución).
3. **Pregunta al usuario si está conforme** y **solo** si pide un cambio concreto, vuelve a llamar a
   los scripts.
4. Si un script falla, léelo, corrígelo una vez si es problema de entrada y reintenta; si es del
   código, comunícalo y propón el arreglo.

Con esto, el trabajo es: un comando de verificación + los pasos + leer el output + preguntar (2
preguntas: prompts e imágenes). Eso minimiza tokens.

## Orden de ejecución

Ejecuta en este orden. Cada paso deriva sus rutas de `--guion <sesión>/guion.json`.

### Paso 1 — Verificar el entorno

```bash
python scripts/verificar_entorno.py
```

Comprueba dependencias (`edge-tts`, `faster-whisper`, `google-genai`, `imageio-ffmpeg`), `ffmpeg`
(con libass para subtítulos) y las herramientas MCP. Si falta algo, informa al usuario qué instalar
(ver `README.md` → Prerrequisitos). Si `ffmpeg` no tiene `subtitles`/`ass`, instala
`pip install imageio-ffmpeg` — ese binario trae libass y lo copia a `ffmpeg`.

### Paso 2 — Generar audio narrado (TTS modular)

```bash
python scripts/generar_audio.py --guion <sesión>/guion.json --voz es-ES-ElviraNeural
```

Genera un `.mp3` por escena y `narracion.mp3` en `<sesión>/audio/`. El **motor de TTS es modular**
(no hardcodeado a edge-tts):

| Motor | `--motor` | Clave `.env` | Voces ejemplo | Calidad/costo |
|---|---|---|---|---|
| **edge-tts** (default) | `edge` | *(no necesita)* | `es-ES-ElviraNeural`, `es-MX-JorgeNeural` | Bueno, gratis (servicio online de Microsoft Edge, sin API key) |
| **Google Cloud TTS** | `gcp` | `GCP_TTS_API_KEY` | `es-ES-Neural2-F`, `es-ES-Wavenet-C`, `es-ES-Chirp3-HD-Aoede` | Muy bueno; free tier mensual (Neural2 1M chars ≈ 20 h de audio) |

- **Selección automática:** si existe `GCP_TTS_API_KEY` en `.env` se usa `gcp`; si no, `edge`.
  Fuerza uno con `--motor edge|gcp` o `TTS_MOTOR` en `.env`.
- **Tono según el video (importante):** el agente DEBE ajustar voz/velocidad/tono según el tema y
  la emoción del guion. Prioridad: flags CLI > `parametros.tts` del `guion.json` > `.env` > default.
  - `--voz` (ej. voz grave para misterio, energética para motivación)
  - `--rate` (ej. `-10%` para suspenso, `+5%` para ritmo ágil)
  - `--pitch` (ej. `-2` más grave/dramático, `+2` más agudo/alegre; en edge se manda como Hz)
  - En el guion, la Fase 1 puede dejar `parametros.tts` = `{"motor": "edge", "voz": "...", "rate": "-10%", "pitch": "-2"}`.

> **Google Cloud TTS — free tier (verificado):** asignación mensual permanente por familia de
> voces: WaveNet **4M chars**, Neural2 **1M chars** (≈ USD 16 de valor), Chirp 3 HD **1M chars**,
> Standard 4M chars. Requiere cuenta GCP con billing activo. API key — Console de Google Cloud →
> *APIs y servicios → Biblioteca* → habilitar **Cloud Text-to-Speech API** → *Credenciales →
> Crear credenciales → Clave de API* → pégala en `.env` como `GCP_TTS_API_KEY`.
> Alternativas con free tier: Azure TTS F0 (500k chars/mes), ElevenLabs (~10k chars/mes),
> Amazon Polly (1M chars/mes solo el primer año). OpenAI TTS no tiene free tier.

### Paso 3 — Transcribir a `.srt` + `palabras.json` (faster-whisper)

```bash
python scripts/transcribir.py \
  --audio <sesión>/audio/narracion.mp3 --outdir <sesión>/transcripcion
# Opcional: --no-word-timestamps para desactivar palabra-a-palabra
```

Produce `narracion.srt` (frases), `narracion.json` y `palabras.json` (word-level con
`word_timestamps=True` para subtítulos karaoke). Si el modelo no da word timestamps, hace
fallback proporcional.

### Paso 3b — Generar subtítulos ASS palabra-a-palabra (estilo TikTok)

```bash
python scripts/generar_subtitulos.py --guion <sesión>/guion.json
# -> <sesión>/transcripcion/narracion.ass
# Opciones: --color amarillo|blanco|#RRGGBB --hook "TEXTO ROJO" --hook-duration 3.0 --font "Arial Black"
```

Genera `narracion.ass` con:

- **Abajo**: una palabra por evento, centrada, `WWord` amarillo (#FFFF00) por defecto,
  borde negro grueso (Outline 5), sombra, negrita, `Alignment 2` (bottom-center), `PlayRes 1080x1920`.
  Cada palabra dura desde su `start` hasta el siguiente `start` (mín 0.18s) → misma imagen cambia
  de subtítulo como en tus capturas (`no` → `corporations` → `borrow`...).
- **Arriba**: `TopHook` rojo (#FF2B2B) borde blanco, mayúsculas, `Alignment 8` (top-center),
  visible `hookDuration` segundos (default 3s). Texto = `parametros.subtitulos.hook` o,
  si es `null`, copia la primera frase de la narración (hook llamativo automático).

Configurable vía `guion.json`:

```json
"parametros": {
  "subtitulos": {
    "enabled": true,
    "color": "amarillo",
    "font": "Arial Black",
    "fontSize": 64,
    "outline": 5,
    "hook": "WHO REALLY RUNS THE WORLD?",
    "hookColor": "rojo",
    "hookDuration": 3.0
  }
}
```

Prioridad: flags CLI > `parametros.subtitulos` > default. El usuario puede pedir
"cambia a blanco", "haz el hook más corto", o adjuntar una captura como modelo y tú traduces
a estos parámetros. Si `enabled=false`, no se genera ni se quema.

### Paso 3c — Generar descripción TikTok (gancho + 5 hashtags)

```bash
python scripts/generar_descripcion.py --guion <sesión>/guion.json
# -> <sesión>/descripcion.txt  y  <sesión>/transcripcion/descripcion.txt
# Contenido ejemplo:
# This is the biggest lie about money 💰 • You need to know this.
#
# #money #finance #investing #economy #banking
```

Genera `descripcion.txt` con descripción corta (hook reformulado de la primera narración, máx 150 caracteres, con emoji) + 5 hashtags virales cortos en inglés, relacionados con el nicho/título. Por defecto autogenera; si `guion.json:parametros.descripcion_tiktok` o `hashtags` existen, los usa tal cual. Prioridad CLI > guion > auto. Este TXT es el que el usuario copia al publicar en TikTok. Se genera automáticamente en el pipeline (`descripcion` después de `subtitulos`) y queda como sidecar.

### Paso 3.5 — Revisar y aprobar los prompts de imagen (obligatorio)

Antes de generar imágenes, exporta el archivo de prompts **editable a mano**:

```bash
python scripts/generar_imagenes.py --guion <sesión>/guion.json --export-prompts
# -> <sesión>/prompts.txt
```

1. **Muestra** los prompts al usuario (o el path `<sesión>/prompts.txt`) y **pregúntale si está de
   acuerdo** con los prompts de generación de imágenes.
2. **Dile** al usuario que tiene **dos vías** para cambiarlos:
   - **Pedirte** que los ajustes tú (p. ej. "haz el prompt de la escena 3 más dramático").
   - **Editarlos a mano** en `<sesión>/prompts.txt` y avisarte.
3. Tras los cambios (tuyos o del usuario), el script usará **esos prompts** como input final (si el
   archivo existe, tiene prioridad sobre el guion). **Itera hasta que el usuario apruebe los
   prompts**; recién entonces genera las imágenes.

> El archivo se crea la primera vez que corres el paso de imágenes con su contenido del guion.
> `--export-prompts` lo (re)escribe; si ya existe y lo editaste a mano, el paso de imágenes lo
> respeta.

### Paso 4 — Generar imágenes por escena (proveedor intercambiable)

Soporta **dos proveedores** (elige con `--proveedor` o `IMAGEN_PROVEEDOR`):

| Proveedor | `--proveedor` | API key | Modelo por defecto | `--model` alternativo |
|---|---|---|---|---|
| Google (Nano Banana) | `gemini` | `GEMINI_API_KEY` | `gemini-3.1-flash-image-preview` | `gemini-2.5-flash-image` |
| Alibaba Cloud | `qwen` | `QWEN_API_KEY` | `qwen-image-2.0` | `qwen-image-3.0` / `qwen-image-3.0-pro` |

```bash
# Gemini:
python scripts/generar_imagenes.py --guion <sesión>/guion.json --proveedor gemini --model gemini-3.1-flash-image-preview

# Qwen (Alibaba DashScope; host en QWEN_API_HOST de .env):
python scripts/generar_imagenes.py --guion <sesión>/guion.json --proveedor qwen --model qwen-image-2.0
```

- Escribe `<sesión>/imagenes/MM_SS_*.png` por escena (si los prompts editados en `prompts.txt`
  existen, los usa).
- **Límite de peticiones:** el script **espacia** las peticiones según `QWEN_RPM` (por defecto
  **2/min** en `qwen-image-2.0`; 5/min en `qwen-image-3.0`). Con 5 escenas y 2/min tarda ~2 min;
  es normal. Si el usuario lo pide, ajustá `QWEN_RPM` en `.env`. Si pasas más de 3 referencias
  a Qwen, el script trunca automáticamente a 3 (máximo del modelo) con aviso.
- **Estilo consistente / imagen de referencia:** si el usuario quiere que las imágenes sigan un
  estilo de una o varias imágenes de referencia (pueden estar **fuera del proyecto**, p. ej. en
  `~/Desktop/...`), pásalas con `--referencia` (repetible o separadas por comas). Se envían al
  modelo junto con cada prompt:

  ```bash
  python scripts/generar_imagenes.py --guion <sesión>/guion.json \
    --proveedor qwen --referencia "C:/ruta/a/referencia_1.png" \
    --referencia "/Users/yo/Desktop/referencia_2.png" --overwrite
  ```

  También pueden ir en `parametros.imagen_referencia` del guion (string o lista). Las imágenes se
  **envían reales (base64) junto con el prompt en cada llamada API** — el anclaje visual directo
  es el mecanismo principal de consistencia; no se sustituyen por descripciones textuales.
- **Seed para consistencia (Qwen):** `qwen-image-2.0/3.0` soporta `parameters.seed` (0–2147483647).
  El script usa **una misma seed para todas las escenas del video**: `--seed 12345`, o `IMAGEN_SEED`
  en `.env`, o (default) **auto-derivada del título del guion** (crc32) — así la misma idea siempre
  usa la misma seed y otra idea usa otra. La seed estabiliza estilo/paleta; la consistencia del
  **personaje** depende además de repetir la misma "ficha de personaje" literal en cada prompt
  (lo hace la Fase 1) y de las imágenes de referencia. La seed queda registrada en
  `<sesión>/imagenes/reporte.json`. Gemini no soporta seed (se ignora con un aviso).
- **prompt_extend:** por defecto **False** (`QWEN_PROMPT_EXTEND=false` en `.env` o `--prompt-extend`
  para activarlo). La reescritura automática del prompt por parte del modelo añade varianza entre
  escenas; desactivada, respeta tu prompt literal → más consistencia.
- **Nombrado:** `MM_SS_<slug>.png`. Si una imagen falla, el script deja el detalle en
  `<sesión>/imagenes/reporte.json`.

### Paso 4.5 — Aprobar las imágenes con el usuario (obligatorio)

Tras generar, **no ensambles todavía**. El script genera un **contact sheet** con todas las escenas:

```bash
python scripts/generar_imagenes.py --guion <sesión>/guion.json --contact-sheet
# -> <sesión>/revision/contact_sheet.png
```

1. **Muestra** esa imagen (`<sesión>/revision/contact_sheet.png`) y **pregunta** si las imágenes
   están bien (estilo, colores, animación, fondos, consistencia).
2. **Si responde que sí** → continúa al Paso 5.
3. **Si responde que no** → pregunta su feedback y **regenera**:
   - Global → `--estilo "<feedback>"` (se suma a cada prompt) u **edita `prompts.txt`** y regenera.
   - Una escena → `--solo escena-XX --overwrite`.
   - Cambia también el prompt en el guion o en `prompts.txt` si el usuario pide otra escena concreta.
4. **Vuelve a generar el contact sheet** y **repregunta**. **Itera hasta el visto bueno**, y recién
   entonces continúa.

### Paso 5 — Ensamblar el video final (FFmpeg con subtítulos quemados)

```bash
python scripts/ensamblar_video.py --guion <sesión>/guion.json --formato vertical
# O sin subtítulos: --no-subtitulos
# -> <sesión>/video/final.mp4
```

Aplica **efectos de edición** (movimiento Ken Burns por escena + transiciones entre escenas +
fades globales + grading opcional), superpone la narración, **quema los subtítulos ASS**
(`transcripcion/narracion.ass` palabra-a-palabra, si existe; si no, `narracion.srt`) y exporta.
La duración de cada escena es la real de su audio y las transiciones se calculan sobre los tiempos
del guion — **el audio nunca se desincroniza**. Formato: `vertical` → 1080x1920 (9:16),
`horizontal` → 1920x1080 (16:9). MP4 H.264+AAC. Requiere `ffmpeg` con `libass` (`pip install imageio-ffmpeg`).

**Catálogo de efectos** (el script lo lista con `--list-efectos`):

| Tipo | Valores |
|---|---|
| Movimiento por escena (`zoompan`) | `static`, `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `kenburns`, `pop` (rebote), `slide_up` (entra desde abajo), `slide_down`, `shake` |
| Transición de salida (`xfade`) | `none` (corte seco), `fade`, `dissolve`, `wipeleft`, `slideup`, `slideleft`, `slideright`, `slidedown`, `circleopen` |
| Grading | `none`, `warm`, `cool` |
| Overlay intra-escena (nuevo) | `slideup` (sube desde abajo, como Tom en tus capturas), `slidedown`, `fade`, `pop`, `wipeup` — se declara en `efectos.overlays: [{"src":"path.png","entrada":"slideup","salida":"slidedown","inicio":0.5,"duracion":2.0,"escala":0.55}]` |
| Presets (`--preset`) | `suave` (default: Ken Burns lento 1.12x + fade 0.4s) · `dinamico` (movimientos 1.22x + transiciones variadas) · `off` (imagen fija, como la v1) |

**Cómo decide el agente los efectos (no son fijos):** Fase 1 (Director Creativo IA) analiza idea + narración + imagen y escribe `efectos` por escena según guía: `zoom_in` lento para revelación clave, `pan_left` cambio de lugar, `pop` para dato que impacta, `slide_up` overlay para personaje que entra desde abajo (tu ejemplo 45K$ y REAL ESTATE VS STOCKS), `grade warm` solo para cierre inspirador, `grade none` por defecto para no desteñir. Si `efectos` está vacío, cae a preset. Puedes pedir "más pop en escena 3" o adjuntar captura y el agente traduce a `overlays`.

**Prioridad:** `efectos` de la escena en el guion (escritos por la Fase 1, opcional) > `--preset` >
comportamiento clásico. Ejemplos:
- Simple: `"efectos": {"movimiento": "zoom_in", "intensidad": 1.15, "transicion": "dissolve", "grade": "none"}`
- Con overlay TikTok: `"efectos": {"movimiento": "static", "overlays": [{"src": "workspace/overlay_tom.png", "entrada": "slideup", "salida": "slidedown", "inicio": 0.4, "duracion": 2.2, "escala": 0.5}]}`

**Subtítulos (nuevo, por defecto ON):**
- Si `transcripcion/narracion.ass` existe (generado en Paso 3b), se quema con `subtitles=...` (libass).
- Si no, usa `narracion.srt` como fallback.
- Desactivar: `parametros.subtitulos.enabled=false` en `guion.json` o `--no-subtitulos` en CLI.
- Cambiar color/hook: `parametros.subtitulos.color`, `hook`, `hookColor`, `hookDuration`,
  o flags `--color`, `--hook` en `generar_subtitulos.py`.

**Flujo de decisión de efectos (agente + usuario):**
1. Si el guion trae `efectos` por escena, respétalos — son decisiones creativas de la Fase 1.
2. Antes de ensamblar, pregunta **una sola vez y de forma ligera**: «¿tienes algún efecto en mente
   para algún momento?» (ej. "zoom en la revelación", "transición más lenta"). Si no, usa el preset.
3. Elige el preset según el tono: `suave` para historias/misterio; `dinamico` para humor/gaming/
   motivación. Pásalo con `--preset`.
4. Los efectos aplicados quedan en `<sesión>/video/reporte_ensamblado.json`.
5. En la revisión post-producción, ajusta a pedido: "más zoom en la escena N" → edita `efectos`
   (o `--preset`) y re-ensambla (no regenera imágenes ni audio).

## Revisión post-producción

1. Confirma `<sesión>/video/final.mp4` y presenta (ruta + duración + resolución).
2. Pregunta si quiere ajustes:
   - **Corte / re-escena:** ajusta timestamps en `guion.json` y re-ensambla.
   - **Efectos:** "más zoom", "otra transición", "más lenta" → edita `efectos` de esa escena en
     `guion.json` o cambia `--preset`, y re-ensambla (usa `--salida final_v2.mp4` para comparar).
   - **Reemplazo de imagen:** regenera esa escena (`--solo <id>`) y re-ensambla.
   - **Cambio de duración:** ajusta `duracion_segundos` y narraciones, regenera audio → transcripción
     → subtítulos → prompts → imágenes → ensamblado.
   - **Cambio de voz:** repite el Paso 2 con otro `--voz`.
   - **Cambio de estilo:** cambia/añade `--referencia` (o edita `prompts.txt`) y regenera imágenes.
   - **Subtítulos:** "hazlos blancos", "quita el hook", "más grandes" → edita `parametros.subtitulos`
     en `guion.json` o regenera con `generar_subtitulos.py --color blanco --no-hook` y re-ensambla.
3. Iterar hasta que el usuario dé por bueno el video.

## Verificación final

- `<sesión>/guion.json`, `<sesión>/prompts.txt` y `<sesión>/descripcion.txt` existen.
- `<sesión>/audio/narracion.mp3` y `<sesión>/transcripcion/narracion.srt` existen;
  `<sesión>/transcripcion/palabras.json` y `narracion.ass` existen (subtítulos palabra-a-palabra);
  `<sesión>/transcripcion/descripcion.txt` es copia del TXT principal.
- `<sesión>/imagenes/` tiene una imagen por escena `MM_SS_*.png`.
- **El usuario aprobó los prompts** (Paso 3.5) y **las imágenes** (Paso 4.5).
- `<sesión>/video/final.mp4` existe, con subtítulos quemados por defecto y duración aproximada (el audio real manda).
- El usuario dio su aprobación final (si no, no cierres — ofrece ajustes).

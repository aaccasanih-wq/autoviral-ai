---
name: generacion-video
description: Ejecuta el pipeline técnico completo de producción de un video corto a partir de un guion ya confirmado — narración con motor TTS modular (edge-tts o Google Cloud TTS, con tono configurable por guion), transcripción a .srt (faster-whisper), imágenes por escena con proveedor intercambiable (Gemini Nano Banana 2 o Alibaba Qwen, con seed estable por video) y ensamblaje del video final (FFmpeg/Kinocut). Antes de generar imágenes pide al usuario que apruebe los prompts (y le ofrece editarlos), y después pide que apruebe las imágenes — si no está conforme, regenera con su feedback. Úsala solo en la Fase 2 — nunca crea ideas creativas nuevas.
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
        ├── audio/                 # mp3 por escena + narracion.mp3 + timings.json
        ├── transcripcion/         # narracion.srt + narracion.json
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
- **No preguntes si se queman los subtítulos**: con el ffmpeg actual no se puede (compilado sin
  libass, faltaría descargar otro ffmpeg). Genera siempre el `.srt` como sidecar y, en el
  ensamblado, el script lo omite automáticamente — no ofrezcas la opción ni lo menciones como
  pendiente.
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

Comprueba dependencias (`edge-tts`, `faster-whisper`, `google-genai`), `ffmpeg` y las herramientas
MCP. Si falta algo, informa al usuario qué instalar (ver `README.md` → Prerrequisitos).

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

### Paso 3 — Transcribir a `.srt` (faster-whisper)

```bash
python scripts/transcribir.py \
  --audio <sesión>/audio/narracion.mp3 --outdir <sesión>/transcripcion
```

Produce `narracion.srt` y `narracion.json` (duración real por frase). Los subtítulos NO se queman
sobre el video (ver Límites); quedan como sidecar.

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
  es normal. Si el usuario lo pide, ajustá `QWEN_RPM` en `.env`.
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

### Paso 5 — Ensamblar el video final (FFmpeg / Kinocut MCP)

```bash
python scripts/ensamblar_video.py --guion <sesión>/guion.json --formato vertical
# -> <sesión>/video/final.mp4
```

Concatena imágenes (cada una con la duración real de su escena), superpone la narración y exporta.
**No quema subtítulos** (ver Límites): deja el `.srt` como sidecar. Formato: `vertical` → 1080x1920
(9:16), `horizontal` → 1920x1080 (16:9). MP4 H.264+AAC.

## Revisión post-producción

1. Confirma `<sesión>/video/final.mp4` y presenta (ruta + duración + resolución).
2. Pregunta si quiere ajustes:
   - **Corte / re-escena:** ajusta timestamps en `guion.json` y re-ensambla.
   - **Reemplazo de imagen:** regenera esa escena (`--solo <id>`) y re-ensambla.
   - **Cambio de duración:** ajusta `duracion_segundos` y narraciones, regenera audio → transcripción
     → prompts → imágenes → ensamblado.
   - **Cambio de voz:** repite el Paso 2 con otro `--voz`.
   - **Cambio de estilo:** cambia/añade `--referencia` (o edita `prompts.txt`) y regenera imágenes.
3. Iterar hasta que el usuario dé por bueno el video.

## Verificación final

- `<sesión>/guion.json` y `<sesión>/prompts.txt` existen.
- `<sesión>/audio/narracion.mp3` y `<sesión>/transcripcion/narracion.srt` existen (srt sin quemar).
- `<sesión>/imagenes/` tiene una imagen por escena `MM_SS_*.png`.
- **El usuario aprobó los prompts** (Paso 3.5) y **las imágenes** (Paso 4.5).
- `<sesión>/video/final.mp4` existe, con la duración aproximada (el audio real manda).
- El usuario dio su aprobación final (si no, no cierres — ofrece ajustes).

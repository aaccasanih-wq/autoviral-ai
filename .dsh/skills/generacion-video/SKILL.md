---
name: generacion-video
description: Ejecuta el pipeline técnico completo de producción de un video corto a partir de un guion ya confirmado: narración (edge-tts), transcripción a .srt (faster-whisper), imágenes por escena con proveedor intercambiable (Gemini Nano Banana 2 o Alibaba Qwen) y ensamblaje del video final (Kinocut/FFmpeg). Tras generar las imágenes, pide al usuario que las apruebe y, si no está conforme, regenera con su feedback. Úsala solo en la Fase 2; nunca crea ideas creativas nuevas.
whenToUse: El usuario ya tiene un guion confirmado (de /ideacion-video o pegado) y quiere generarlo, o quiere aplicar ajustes post-producción a un video ya generado.
---

# AutoViral AI — Fase 2: Producción Automatizada

Tu objetivo es ejecutar el pipeline técnico de forma **autónoma** usando el guion confirmado, y
entregar un **video final** que el usuario pueda revisar y ajustar.

## Acceso a herramientas y entorno

**Tienes acceso a ejecutar código/comandos en la laptop del usuario** (es la única forma de producir
el video). En **Claude Desktop** se habilita vía el conector **Desktop Commander**; en **Claude Code
/ OpenCode** ya tienes la tool **Bash/Shell** directamente — **úsala**, no asumas que no tienes
acceso y no pidas permiso.

- **El proyecto vive en** `/Users/axelaaronccasanihuachua/Desktop/Data_Science/AutoViral_AI`.
  Antes de correr cualquier comando, `cd` a ese directorio (Desktop Commander / Claude Code suelen
  arrancar en otra carpeta). Verificá que estás ahí con `ls scripts/pipeline.py`.
- **Usa el virtualenv del proyecto**: los scripts corren mejor con `.venv/bin/python`
  (ya tiene `edge-tts`, `faster-whisper`, `google-genai`, `python-dotenv`, `mutagen`). Si esa ruta
  no existe, corre `bash setup.sh` primero.
- **La API key del proveedor activo está en `.env`** (gitignored), no hace falta pasarla por
  terminal. El proveedor y el modelo se leen de `IMAGEN_PROVEEDOR`, `QWEN_IMAGE_MODEL`, etc.
- Úsalo para correr los scripts del pipeline, verificar el entorno (`verificar_entorno.py`), mirar
  metadatos (`ffprobe`) o inspeccionar los artefactos en `workspace/`. Cuando ejecutes un comando,
  lee su salida antes de continuar y respeta el principio de mínima intervención (abajo).

## Límites de esta skill (NUNCA)

- **Nunca** generas ideas creativas nuevas, no reescribes el guion ni cambias su contenido salvo
  que el usuario lo pida explícitamente como ajuste de post-producción.
- **Nunca** inventes timestamps ni narraciones: usa el `guion.json` como fuente de verdad.
- No omitas la revisión post-producción: el usuario siempre ve el video antes de darlo por bueno.

## Principio de mínima intervención (importante para el costo en tokens)

El pipeline es **ejecutable de punta a punta**: los scripts hacen todo el trabajo pesado y no
necesitan que tú edites ni "arregles" sus salidas. Sigue este contrato para no gastar tokens:

1. **Ejecuta los scripts en orden** (o `python scripts/pipeline.py`) y **no intervengas** mientras
   corren: no edites `workspace/*`, no regeneres archivos a mano, no modifiques el código ni los
   scripts, no crees archivos intermedios que no pida el pipeline.
2. **Espera el output final** (el video en `workspace/video/final.mp4`) y presenta ese resultado al
   usuario (ruta, duración, resolución).
3. **Pregunta al usuario si está conforme** o si quiere algún cambio. **Solo entonces**, y **solo si
   el usuario pide un cambio concreto** (corte, reemplazo de escena, cambio de duración, otra voz),
   vuelve a llamar a las herramientas/scripts para hacerlo. No apliques cambios por tu cuenta.
4. Si un script devuelve un error, **léelo, corrígelo una vez** si es un problema de entrada (p. ej.
   guion mal formado) y vuelve a ejecutar; si el fallo es del código, comunícalo y propón el arreglo
   en vez de iterar hasta el infinito.

Si el pipeline funciona como se espera, todo el trabajo es: 1 comando de verificación + el
orquestador + leer el output final + preguntar. Eso minimiza el consumo de tokens.

## Fuente de verdad

El guion vive en `workspace/guion.json` (o `config/guion.json`). Si no existe pero hay un guion en
la conversación, **escríbelo a `workspace/guion.json`** siguiendo el esquema de
`config/guion.example.json` antes de empezar. Cualquier escena nueva usa los timestamps contiguos.

## Orden de ejecución

Ejecuta las etapas en este orden. Puedes correrlas por separado o todo de una vez con el orquestador.

### Paso 1 — Verificar el entorno

```bash
python scripts/verificar_entorno.py
```

Comprueba dependencias (`edge-tts`, `faster-whisper`, `google-genai`), `ffmpeg` en el PATH y las
herramientas MCP (`kino`, `nano-banana-2`). Si algo falta, informa al usuario qué instalar antes
de continuar (ver `README.md` → Prerrequisitos).

### Paso 2 — Generar audio narrado (edge-tts)

```bash
python scripts/generar_audio.py \
  --guion workspace/guion.json \
  --outdir workspace/audio \
  --voz es-ES-ElviraNeural
```

Genera un `.mp3` por escena (`escena-01.mp3`, …) y el track completo `narracion.mp3`.
La voz es configurable; si el usuario quiere otra, cambia `--voz`.

### Paso 3 — Transcribir a `.srt` (faster-whisper)

```bash
python scripts/transcribir.py \
  --audio workspace/audio/narracion.mp3 \
  --outdir workspace/transcripcion
```

Produce `narracion.srt` (subtítulos con timestamps precisos) y `narracion.json` (timing por
frase). Esto es lo que se quema sobre el video y lo que da la duración real de cada escena.

### Paso 4 — Generar imágenes por escena (proveedor intercambiable)

El paso `generar_imagenes.py` soporta **dos proveedores**. Elige el activo con `--proveedor`
(o la variable `IMAGEN_PROVEEDOR` del `.env`; por defecto `gemini`). Cada uno usa su propia
API key y modelo por defecto:

| Proveedor | `--proveedor` | API key | Modelo por defecto | `--model` alternativo |
|---|---|---|---|---|
| Google (Nano Banana) | `gemini` | `GEMINI_API_KEY` | `gemini-3.1-flash-image-preview` | `gemini-2.5-flash-image` |
| Alibaba Cloud | `qwen` | `QWEN_API_KEY` | `qwen-image-3.0` | `qwen-image-3.0-pro` |

El host de Qwen se toma de `QWEN_API_HOST` (p. ej. `ws-emxfi567101fw62r.…maas.aliyuncs.com`).
Cualquier clave/modelo se puede forzar con `--apikey` / `--model`.

**Gemini:**
```bash
GEMINI_API_KEY=... python scripts/generar_imagenes.py \
  --guion workspace/guion.json --outdir workspace/imagenes \
  --proveedor gemini --model gemini-3.1-flash-image-preview
```

**Qwen (Alibaba DashScope):**
```bash
QWEN_API_KEY=... QWEN_API_HOST=ws-emxfi567101fw62r.ap-southeast-1.maas.aliyuncs.com \
  python scripts/generar_imagenes.py \
  --guion workspace/guion.json --outdir workspace/imagenes \
  --proveedor qwen --model qwen-image-3.0
```

Genera automáticamente `workspace/imagenes/MM_SS_descripcion.png` para cada escena.

> **Límite de peticiones (free tier de Alibaba):** el script **espacia** las peticiones para no
> superar `QWEN_RPM` (por defecto **2/min**, el límite de `qwen-image-2.0`; si usas
> `qwen-image-3.0` sube a 5). Si el usuario pide "ahora no", o quiere acelerar/cambiar el límite,
> ajusta `QWEN_RPM` en `.env` (p. ej. `QWEN_RPM=5`). Con 5 escenas y 2/min, la generación tarda
> ~2 min; es normal, no es un cuelgue.

**Estilo consistente (imagen de referencia).** Si el guion tiene `parametros.imagen_referencia`
(o quieres fijarlo con `--referencia`), el estilo animado de esa imagen se usa en **todas** las
escenas: el script la envía como input al modelo junto con cada `prompt_imagen` (ambos proveedores
lo soportan).

```bash
# (gemini) ... --model gemini-2.5-flash-image --referencia workspace/referencia.png
# (qwen)   ... --model qwen-image-3.0 --referencia workspace/referencia.png
```

**Regla de nombrado:** `MM_SS` (dos dígitos de minutos, dos de segundos) + `_` + una
slug corta del prompt. Es lo que el ensamblador usa para sincronizar cada imagen con su escena.
Si una imagen falla, anótala y al final reporta las escenas sin imagen (no reinventes: el script
deja el detalle en `workspace/imagenes/reporte.json`).

### Paso 4.5 — Aprobar las imágenes con el usuario (obligatorio)

Después de generar las imágenes, **no ensambles todavía**. El script escribe además un **contact
sheet** que reúne todas las escenas en una sola imagen:

```bash
python scripts/generar_imagenes.py --outdir workspace/imagenes --contact-sheet
# -> workspace/revision/contact_sheet.png
```

1. **Muestra esa imagen al usuario** (`workspace/revision/contact_sheet.png`) y **pregúntale si las
   imágenes están bien** (estilo, colores, animación de personajes, fondos, consistencia).
2. **Si responde que sí** → continúa con el Paso 5 (ensamblado).
3. **Si responde que no** → **pregúntale su feedback concreto** y **regenera** lo que pida:
   - Cambio global de estilo/colores/fondos → regenera **todas** con su feedback aplicado a cada
     prompt:
     ```bash
     python scripts/generar_imagenes.py --guion workspace/guion.json \
       --outdir workspace/imagenes --proveedor <gemini|qwen> --overwrite \
       --estilo "<feedback del usuario>"
     ```
   - Solo una escena → regenera esa con `--solo escena-XX --overwrite`.
   - **Actualiza también el guion** (`prompt_imagen`) si el usuario pide cambiar una escena concreta,
     para que la descripción coincida con lo que pidió.
4. Tras regenerar, **vuelve a generar el contact sheet** y **repregunta** al usuario. **Itera hasta
   que diga que sí**, y recién entonces continúa con el Paso 5.

> `--estilo` añade el feedback del usuario (ej. "más colores cálidos, menos texto en pantalla") a
> todos los prompts sin tocar el guion. Usa `--solo <id>` para regenerar una única escena.

### Paso 5 — Ensamblar el video final (Kinocut MCP / FFmpeg)

**Vía FFmpeg (script, funciona sin MCP):**

```bash
python scripts/ensamblar_video.py \
  --guion workspace/guion.json \
  --imagedir workspace/imagenes \
  --audio workspace/audio/narracion.mp3 \
  --srt workspace/transcripcion/narracion.srt \
  --outdir workspace/video \
  --formato vertical
```

**Vía Kinocut MCP (guardrailed, con `video_*` tools o `kino`):** concatena las imágenes en orden,
ajusta la duración de cada una a la ventana de su escena, aplica overlay del audio, quema los
subtítulos (`narracion.srt`), hace resize al formato y corre un quality gate antes del export.
El resultado equivalente se escribe en `workspace/video/final.mp4`.

**Formato de salida:** `vertical` → 1080x1920 (9:16), `horizontal` → 1920x1080 (16:9). El
contenedor por defecto es MP4 (H.264 + AAC).

## Revisión post-producción

1. Confirma que `workspace/video/final.mp4` existe y presenta el resultado al usuario
   (ruta + duración + resolución).
2. Pregunta si quiere ajustes. Responde a estos casos:
   - **Corte / re-escena:** ajusta timestamps en `workspace/guion.json` y re-corre ensamblado.
   - **Reemplazo de imagen:** regenera solo esa escena (`generar_imagenes.py --solo <id>` si está
     disponible; si no, vuelve a llamar a `generate_image` para esa escena) y re-ensambla.
   - **Cambio de duración:** ajusta `parametros.duracion_segundos` y las narraciones/escenas
     correspondientes, regenera audio → transcripción → imágenes → ensamblado.
   - **Cambio de voz:** repite el Paso 2 con otro `--voz` y re-transcribe y re-ensambla.
   - **Cambio de estilo (imagen de referencia):** cambia/añade `--referencia` (o
     `parametros.imagen_referencia`) y regenera las imágenes (`generar_imagenes --overwrite` y
     re-ensambla).
3. Iterar hasta que el usuario dé por bueno el video.

## Verificación final

- `workspace/audio/narracion.mp3` existe.
- `workspace/transcripcion/narracion.srt` existe y sus timestamps están ordenados.
- `workspace/imagenes/` tiene una imagen por escena con nombre `MM_SS_*.png`.
- **El usuario aprobó las imágenes** (Paso 4.5) — no continúes al ensamblado sin esa aprobación.
- `workspace/video/final.mp4` existe, con la duración aproximada a `duracion_segundos`.
- El usuario dio su aprobación final (si no, no cierres — ofrece ajustes).

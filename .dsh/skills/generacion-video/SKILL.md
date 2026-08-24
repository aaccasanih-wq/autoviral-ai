---
name: generacion-video
description: Ejecuta el pipeline técnico completo de producción de un video corto a partir de un guion ya confirmado: narración (edge-tts), transcripción a .srt (faster-whisper), imágenes por escena (Gemini Nano Banana 2 vía MCP) y ensamblaje del video final (Kinocut/FFmpeg). Úsala solo en la Fase 2; nunca crea ideas creativas nuevas.
whenToUse: El usuario ya tiene un guion confirmado (de /ideacion-video o pegado) y quiere generarlo, o quiere aplicar ajustes post-producción a un video ya generado.
---

# AutoViral AI — Fase 2: Producción Automatizada

Tu objetivo es ejecutar el pipeline técnico de forma **autónoma** usando el guion confirmado, y
entregar un **video final** que el usuario pueda revisar y ajustar.

## Límites de esta skill (NUNCA)

- **Nunca** generas ideas creativas nuevas, no reescribes el guion ni cambias su contenido salvo
  que el usuario lo pida explícitamente como ajuste de post-producción.
- **Nunca** inventes timestamps ni narraciones: usa el `guion.json` como fuente de verdad.
- No omitas la revisión post-producción: el usuario siempre ve el video antes de darlo por bueno.

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

### Paso 4 — Generar imágenes por escena (Gemini Nano Banana 2)

Hay **dos vías**; usa la que tengas disponible:

**A) Vía MCP (recomendada).** Con el servidor `nano-banana-2` conectado, llama a la herramienta
`generate_image` por cada escena con su `prompt_imagen`, `aspectRatio` según el formato
(`"9:16"` vertical, `"16:9"` horizontal) y `returnInlineImage: false`. Guarda cada resultado en
`workspace/imagenes/` con el nombre **`MM_SS_descripcion.png`**, donde `MM_SS` es el
`inicio_segundos` de la escena formateado como `00:05` → `00_05`. Ej.: `00_05_gancho.png`.

**B) Vía script (CLI, requiere `GEMINI_API_KEY`).**

```bash
GEMINI_API_KEY=... python scripts/generar_imagenes.py \
  --guion workspace/guion.json \
  --outdir workspace/imagenes \
  --model gemini-3.1-flash-image-preview
```

Genera automáticamente `workspace/imagenes/MM_SS_descripcion.png` para cada escena.

**Regla de nombrado:** `MM_SS` (dos dígitos de minutos, dos de segundos) + `_` + una
slug corta del prompt. Es lo que el ensamblador usa para sincronizar cada imagen con su escena.
Si una imagen falla, reintenta hasta 1 vez con un prompt ligeramente simplificado y luego continúa
con la siguiente; al final reporta las escenas sin imagen.

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
3. Iterar hasta que el usuario dé por bueno el video.

## Verificación final

- `workspace/audio/narracion.mp3` existe.
- `workspace/transcripcion/narracion.srt` existe y sus timestamps están ordenados.
- `workspace/imagenes/` tiene una imagen por escena con nombre `MM_SS_*.png`.
- `workspace/video/final.mp4` existe, con la duración aproximada a `duracion_segundos`.
- El usuario dio su aprobación final (si no, no cierres — ofrece ajustes).

# AutoViral AI — Pipeline Automatizado de Generación de Videos con IA

> **Versión:** 1.0  
> **Autor:** [Tu nombre / alias]  
> **Licencia:** MIT (recomendada)  
> **Fecha de inicio:** 2026

---

## 1. Descripción del Proyecto

**AutoViral AI** es un pipeline automatizado y modular para la creación de videos cortos (YouTube Shorts, TikTok, Instagram Reels) impulsado por inteligencia artificial. El objetivo es que un usuario pueda, mediante lenguaje natural, describir una idea de video (o pedir sugerencias creativas) y que un agente de IA ejecute todo el flujo de producción de forma autónoma: desde la ideación y redacción del guion, pasando por la generación de audio narrado, la transcripción con timestamps, la creación de imágenes por escena, hasta el ensamblaje final del video editado.

El pipeline está diseñado para ser ejecutado desde un agente de código (Claude Code u OpenCode) que interpreta instrucciones en lenguaje natural, carga skills especializadas y orquesta cada etapa mediante herramientas locales y servidores MCP (Model Context Protocol).

---

## 2. Etapas del Pipeline

El proyecto se divide en **dos fases principales** que se ejecutan secuencialmente:

### Fase 1 — Ideación Creativa
- El usuario interactúa con el agente de IA en modo creativo.
- El agente actúa como Director Creativo Senior especializado en contenido viral.
- Se realiza un proceso de brainstorming, refinamiento y feedback hasta llegar a una idea de video final.
- Se define: duración total, formato (vertical u horizontal), idioma, estilo visual y público objetivo.
- Se redacta un **guion estructurado** con escenas, narración, prompts de imagen y timestamps estimados.
- El usuario debe confirmar el guion antes de pasar a la siguiente fase.

### Fase 2 — Producción Automatizada
- El agente de IA ejecuta el pipeline técnico de forma autónoma.
- **Generación de audio:** el texto del guion se convierte en voz narrada mediante texto-a-voz (TTS).
- **Transcripción con timestamps:** el audio narrado se transcribe a un archivo `.srt` con timestamps precisos para sincronizar cada frase con su momento exacto en el video.
- **Generación de imágenes:** para cada escena del guion se genera una imagen mediante IA, nombrada con el formato `MM_SS_descripcion.png` para facilitar la sincronización temporal.
- **Edición de video:** las imágenes se ensamblan en orden, se ajustan a la duración indicada por la transcripción, se superpone el audio de narración, se queman los subtítulos y se exporta el video final en el formato y resolución definidos.
- **Revisión post-producción:** el agente presenta el video final al usuario y permite solicitar ajustes (cortes, reemplazo de imágenes, cambio de duración, etc.).

---

## 3. Stack Tecnológico

| Componente | Rol en el pipeline | Tipo |
|---|---|---|
| **edge-tts** | Generación de audio narrado a partir del guion (texto-a-voz) | Herramienta local (Python) |
| **faster-whisper** | Transcripción del audio a formato `.srt` con timestamps precisos | Herramienta local (Python) |
| **Gemini Nano Banana 2** (vía MCP) | Generación de imágenes por escena a partir de los prompts del guion | Servidor MCP remoto (Google AI Studio) |
| **Kinocut** (vía MCP) | Edición de video: concatenación de clips, overlay de audio, subtítulos quemados, resize, quality gates | Servidor MCP local |
| **FFmpeg** | Motor subyacente de procesamiento multimedia (requerido por Kinocut) | Dependencia del sistema |
| **Claude Code / OpenCode** | Agente de IA que orquesta todo el pipeline mediante skills y herramientas MCP | Cliente de IA (CLI) |
| **Git + GitHub Desktop** | Control de versiones y publicación del proyecto | Herramienta de colaboración |

> **Nota sobre costos:** `edge-tts`, `faster-whisper` y `Kinocut` son completamente gratuitos y de código abierto. Gemini Nano Banana 2 opera bajo el free tier de Google AI Studio. No se requieren suscripciones de pago para ejecutar el pipeline completo.

---

## 4. Estructura de Skills

El proyecto se basa en **dos skills independientes** que el usuario carga según la fase en la que se encuentre. Cada skill es un archivo Markdown con instrucciones de sistema que definen el comportamiento, las reglas y el flujo de trabajo del agente de IA.

### Skill 1: `/ideacion-video`

- **Archivo:** `skills/ideacion-video.md`
- **Objetivo:** Guiar al usuario desde una idea vaga (o la ausencia de idea) hasta un guion de video final, estructurado y confirmado.
- **Qué hace:**
  - Actúa como Director Creativo Senior en contenido viral.
  - Si el usuario no tiene idea, genera propuestas creativas.
  - Si el usuario tiene una idea, la refina mediante feedback iterativo.
  - Define parámetros clave: duración, formato, idioma, estilo visual.
  - Redacta un guion estructurado con escenas, narración, prompts de imagen y timestamps estimados.
  - Muestra el guion completo al usuario y solicita confirmación explícita antes de finalizar.
- **Restricción:** NUNCA genera imágenes, audio o video. Es exclusivamente para ideación y redacción de guiones.
- **Cómo se carga:**
  - En **Claude Code (CLI):** el usuario escribe `/ideacion-video` en el terminal.
  - En **OpenCode:** el usuario escribe `/ideacion-video` en el chat.

### Skill 2: `/generacion-video`

- **Archivo:** `skills/generacion-video.md`
- **Objetivo:** Ejecutar el pipeline técnico completo de producción de video de forma autónoma, usando el guion confirmado de la fase anterior.
- **Qué hace:**
  - Extrae el guion (pegado directamente o inferido del historial de conversación).
  - Genera el audio narrado mediante `edge-tts`.
  - Transcribe el audio a `.srt` mediante `faster-whisper`.
  - Genera una imagen por escena usando Gemini Nano Banana 2 (MCP), nombrada con formato `MM_SS_descripcion.png`.
  - Ensambla el video final mediante Kinocut (MCP): concatenación de clips, overlay de audio, subtítulos quemados, resize y quality gate.
  - Presenta el video final al usuario y permite solicitar ajustes post-producción (cortes, reemplazo de escenas, cambio de duración, etc.).
- **Restricción:** NUNCA genera ideas creativas nuevas. Trabaja exclusivamente con el guion ya confirmado.
- **Cómo se carga:**
  - En **Claude Code (CLI):** el usuario escribe `/generacion-video` en el terminal.
  - En **OpenCode:** el usuario escribe `/generacion-video` en el chat.

### Rutas de los archivos de skill

Los archivos de skill deben ubicarse en la siguiente estructura dentro del repositorio para que puedan ser cargados correctamente:

```
autoviral-ai/
├── skills/
│   ├── ideacion-video.md
│   └── generacion-video.md
├── workspace/
│   ├── audio/
│   ├── transcripcion/
│   ├── imagenes/
│   └── video/
├── .gitignore
├── README.md
└── ...
```

> **Importante:** En Claude Code, las skills se cargan desde archivos `.md` ubicados en el directorio del proyecto. En OpenCode, el mecanismo es similar: se referencian mediante el prefijo `/` seguido del nombre del archivo sin extensión.

---

## 5. Publicación en GitHub y Workflow de Branches

### Creación del repositorio

1. Crear un **nuevo repositorio público** en GitHub con el nombre `autoviral-ai`.
2. Clonar el repositorio vacío localmente usando **GitHub Desktop** en la MacBook.
3. Inicializar el proyecto en la carpeta local clonada.

### Política de branches

**NUNCA se trabaja directamente en la rama `main`.** Cada etapa del proyecto se desarrolla en una branch independiente, lo que permite:
- Aislar cambios y experimentos.
- Revisar el progreso mediante Pull Requests.
- Mantener un historial limpio y profesional.

#### Flujo de trabajo recomendado

| Etapa | Nombre de la branch | Descripción |
|---|---|---|
| Estructura inicial | `setup/estructura-proyecto` | Crear carpetas, `.gitignore`, `README.md` y archivos base. |
| Skill de ideación | `feature/skill-ideacion-video` | Desarrollar y refinar `skills/ideacion-video.md`. |
| Skill de producción | `feature/skill-generacion-video` | Desarrollar y refinar `skills/generacion-video.md`. |
| Integración de TTS | `feature/integracion-edge-tts` | Configurar y probar la generación de audio. |
| Integración de transcripción | `feature/integracion-whisper` | Configurar y probar la transcripción a `.srt`. |
| Integración de imágenes | `feature/integracion-gemini-mcp` | Configurar el servidor MCP de Gemini Nano Banana 2. |
| Integración de edición | `feature/integracion-kinocut` | Configurar Kinocut MCP y probar el ensamblaje de video. |
| Pipeline end-to-end | `feature/pipeline-completo` | Integrar todas las etapas en un flujo unificado. |
| Documentación final | `docs/documentacion-final` | Completar `README.md`, guías de uso y ejemplos. |

#### Pasos por cada branch

1. **Crear la branch** desde `main` (o desde la branch anterior si hay dependencias).
2. **Desarrollar** los cambios correspondientes a esa etapa.
3. **Hacer commits** frecuentes con mensajes descriptivos en inglés (convención: `tipo: descripción breve`).
4. **Pushear (Push)** la branch a GitHub.
5. **Abrir un Pull Request** hacia `main` (opcional, pero recomendado para proyectos colaborativos).
6. **Mergear** la branch a `main` una vez aprobada.
7. **Crear una nueva branch** para la siguiente etapa y repetir el ciclo.

> **Ejemplo de ciclo:**
> ```bash
> git checkout -b feature/skill-ideacion-video
> # ... trabajar en los archivos ...
> git add .
> git commit -m "feat: add ideacion-video skill with creative workflow"
> git push origin feature/skill-ideacion-video
> # Mergear a main vía GitHub Desktop o CLI
> git checkout main
> git pull origin main
> git checkout -b feature/skill-generacion-video
> ```

---

## 6. Archivo .zip para Claude Desktop

Claude Desktop utiliza un formato específico para cargar skills mediante archivos `.zip`. Para que los skills de este proyecto puedan ser importados en Claude Desktop, se debe generar un archivo `.zip` que siga la estructura oficial de skill.

### Estructura del .zip

```
autoviral-ai-skills.zip
├── skill.json          # Metadatos de la skill (nombre, versión, descripción)
├── instructions.md     # Instrucciones del sistema (contenido del skill)
└── README.md           # Documentación breve de la skill
```

> **Nota:** Se debe crear un archivo `.zip` separado para cada skill (`ideacion-video` y `generacion-video`), o un único `.zip` que contenga ambas skills en subcarpetas, dependiendo de cómo Claude Desktop gestione la importación múltiple.

### Ubicación en el repositorio

Los archivos `.zip` de distribución para Claude Desktop deben guardarse en una carpeta dedicada:

```
autoviral-ai/
├── dist/
│   ├── ideacion-video-skill.zip
│   └── generacion-video-skill.zip
├── skills/
│   ├── ideacion-video.md
│   └── generacion-video.md
└── ...
```

---

## 7. Estructura Completa del Repositorio (objetivo final)

```
autoviral-ai/
├── .github/
│   └── workflows/              # (Futuro) CI/CD para automatizar tests del pipeline
├── dist/
│   ├── ideacion-video-skill.zip
│   └── generacion-video-skill.zip
├── skills/
│   ├── ideacion-video.md
│   └── generacion-video.md
├── workspace/
│   ├── audio/
│   ├── transcripcion/
│   ├── imagenes/
│   └── video/
├── .gitignore
├── LICENSE
├── README.md
└── PROJECT.md                # Este archivo
```

---

## 8. Próximos Pasos Inmediatos

1. Crear el repositorio `autoviral-ai` en GitHub.
2. Clonarlo localmente con GitHub Desktop.
3. Crear la branch `setup/estructura-proyecto`.
4. Generar la estructura de carpetas inicial (`skills/`, `workspace/`, `dist/`).
5. Crear el archivo `.gitignore` apropiado para un proyecto Python/MCP.
6. Hacer el primer commit y push.
7. Crear la siguiente branch para desarrollar el primer skill.

---

*Este documento es la hoja de ruta del proyecto. No contiene código ni scripts ejecutables; su propósito es definir la arquitectura, el flujo de trabajo y las convenciones del proyecto antes de comenzar el desarrollo.*

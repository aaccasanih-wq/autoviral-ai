# Catálogo de estilos de animación

Cada estilo = carpeta `estilos/<id>/` con:

- `estilo.json` — ficha `CHARACTER` + `STYLE` verbatim, `anti_drift`, `negativos`, `prompt_template`, `referencias`
- `tts.json` — `motor` default `gcp`, voces EN/ES, `rate/pitch`, `estilo_narracion`
- `referencias/` — imágenes que se envían reales (base64) al generador en cada escena
- `muestra-voz.mp3` + `descripcion-voz.txt` (opcional, al crear estilo nuevo)

El agente NUNCA hardcodea estilos: lee `estilos/catalogo.json` o corre
`python scripts/gestionar_estilos.py --listar`.

## Anti-drift Qwen (por qué no cambia el polo/gorra)

1. Protagonista con outfit ÚNICO y fijo (ej. palitos siempre polo amarillo `#FFD93D`, sin zapatos/gorra).
2. `character_ficha` + `style_ficha` verbatim al inicio de CADA prompt + `anti_drift` al final.
3. Misma `seed` por video, `prompt_extend=false`, referencia(s) en cada llamada (máx 3 en Qwen).
4. Secundarios con color fijo declarado, nunca el color del protagonista.
5. Contact sheet obligatorio para detectar drift antes de ensamblar.

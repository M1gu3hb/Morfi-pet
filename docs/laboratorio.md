# El laboratorio web: "Morfi en vivo"

La portada del sitio (https://morfi-pet.vercel.app, `web/index.html`). Es Morfi en three.js con todo lo que se
puede hacer con él: sus animaciones, expresiones, frases con su voz real, escenas completas con cámara de cine y
un panel de estilo. También es un personaje incrustable (API `window.morfi` y `postMessage`). El visor técnico
del modelo procedural anterior sigue aparte en `web/tecnico.html` (carga `models/morfi.glb`).

Código: `web/src/live/` (`main.ts` arma todo; `director.ts` mezcla clips; `face.ts` ojos y boca en GLSL;
`voice.ts` frases con voz; `scenes.ts` escenas; `tests.ts` la prueba de modelos (§10); `cinema.ts` cámara; `style.ts`, `outline.ts`, `fx_smear.ts`,
`fx_squash.ts`, `style_panel.ts` el estilo) y `web/src/dqskin.ts` (skinning). Estilos: `live.css` y
`style.css`. Qué hace el motor de animación y cómo se hornean los clips: [motor.md](motor.md).

## 1. Panel "Controles"

Panel lateral en pantallas anchas; hoja inferior en celular (≤ 720 px). Secciones en el orden de la pantalla:

| Sección | Qué hace |
|---|---|
| **Que diga algo** | Selector de voz y 12 frases (botones cortos; el texto completo va en el tooltip). Al tocar una, Morfi la dice con su voz real: boca sincronizada con el audio, expresión de la frase y un gesto del cuerpo. La voz elegida se recuerda (`localStorage` `morfi.voice`). Voz oficial: Super VM; hay 10 voces para comparar (las 4 nuevas, parecidas a Super VM —personaje de caricatura, amigable, ni femenina ni grave—, van después de «Mark»: Charlee, Hal, Synchro Sam y Max). |
| **Escenas** | 6 actuaciones completas con voz (presentación, calculadora, idea, ventas, susto, sueño). Duración en cada botón. Al empezar una, aparece el reproductor flotante. Interruptor **Cámara de cine** (activo por defecto; aparece cuando las escenas cargaron). |
| **Video completo** | Lista el video del punto de venta (`POS_Video`, "Tutorial del punto de venta", "Con su voz · mm:ss"). Se oculta si no hay videos. |
| **Prueba** | Sección plegable (empieza cerrada; no baja nada hasta que se abre): la misma actuación "Un día de ventas de Morfi" hecha por cada modelo de IA (§10). Cada tarjeta trae el botón de reproducir (mismo reproductor, voz y cámara de cine que las escenas), el modelo, los costos en USD ("Creación $x · Revisión $y · Publicación $z · Total $t") y "Cambios en la revisión: N" (— mientras no se sepan). Lo que aún no está publicado dice "En preparación". |
| **Animaciones** | Grupo `actions`: Reposo, Saludar, Hablar, Sí, No, Curioso, Presentar, ¡Feliz!, Caminar, Correr, Bailar. |
| **Emociones** | Grupo `emotions`: Reír, Sorpresa, Triste, Enojado, Miedo, Tranquilo, Festejar, No sé. |
| **Gestos y trabajo** | Grupo `work`: Tablet (tutorial), Calculadora, Contar 1-2-3, Señalar, Pulgar arriba, ¡Idea!, Pensar. |
| **Movimientos** | Grupo `moves` (14 clips: Giro con brinco, Saltitos, Baile con brazos, Reverencia, Bostezo y estirón, ¡Vamos!, Saludo a dos manos, Asomarse, Tiritar de frío, De puntitas, Cabeceo de sueño, Impaciente, ¡Ay, no!, Mandar un beso). Se oculta si el JSON no trae ninguno. |
| **Expresión de la cara** | 18 expresiones que se suman a cualquier animación; tocar otra vez la quita ("Neutral" también). |
| **Comportamiento** | "Me sigue con la mirada", "Modo pantalla" (acciones solas, para una pantalla de caja) y fondo claro/oscuro. |

Los botones de clips se arman con los datos: la etiqueta y el grupo vienen de `morfi_live_anims.json`
(`actions[nombre].label` / `.group`, que escribe `scripts/ia3d/anim/catalog.py`). `main.ts` solo guarda una
lista de respaldo (`GROUPS`, `MORE_LABELS`) y, en último caso, arma una etiqueta con el nombre del clip. Un clip
nuevo con entrada en `catalog.py` aparece solo; ningún botón muestra el nombre crudo (lo verifica `test:live`).

### Frases con voz

- Cada frase de `voice/phrases.json` trae `mood` (nombre de una expresión) y `gesture`. Mapa gesto → clip
  (`GESTURES` en `voice.ts`): `wave`→Wave, `present`→Present, `point`→Point_Side, `thumbs_up`→Thumbs_Up,
  `celebrate`→Celebrate, `idea`→Idea, `shrug`→Shrug, `cheeks`→Surprised, `fist`→Victory (si falta, Thumbs_Up),
  `laugh`→Laugh. Si el gesto termina antes que la voz, sigue con `Talk` y luego vuelve a Idle.
- La boca se lee de `audio.currentTime` (no de un temporizador): `lipTrack()` en `voice.ts` copia
  `Performance.speak()` de `anim/performance.py` (letras → forma, envolvente del audio → apertura). No porta los
  asentimientos ni las cejas de las palabras con acento (el JSON no trae esa información).
- Una frase nueva corta a la anterior; empezar una escena corta la frase y al revés (nunca dos audios).
- Si el navegador bloquea el audio (llamada por API o `postMessage` sin toque), aparece "Toca para activar el
  sonido"; el siguiente toque lo reproduce. Si el mp3 falla, la frase se dice en silencio con la boca por texto.
- Las voces no bloquean la carga: `voice/index.json` se pide aparte; si no existe, el campo de voz se oculta y
  el panel dice que las voces no están disponibles.

### Escenas

- Una escena es un clip `Scene_<Nombre>` de un GLB aparte, con sus curvas de cara en un JSON y su audio. El
  tiempo del cuerpo y de la cara **es el tiempo del audio**: pausa, búsqueda o red lenta nunca dejan la boca
  atrás (medido: mediana 11.6 ms, máximo 18.7 ms entre el cuerpo y el reloj del audio).
- Durante una escena no hay parpadeos al azar, ni seguimiento del cursor, ni modo pantalla, ni capa de expresión.
- Reproductor flotante: barra de avance (se arrastra para buscar), Pausa/Reanudar y Detener. Al terminar, vuelve
  a Idle con una transición de 0.8 s. En celular, empezar una escena baja la hoja de Controles.
- **Cámara de cine** (`cinema.ts`): sigue los cortes de cámara de la escena entre cuatro encuadres (`wide`,
  `medium`, `close`, `face`; en las escenas `solo` mira de lado). Si la persona orbita, pellizca o usa la rueda,
  suelta la cámara el resto de esa escena; al final regresa a donde estaba. Con "reducir movimiento" del sistema
  son cortes directos.
- Carga perezosa (ver §6).

### Toque y celular

- Todo objetivo táctil mide ≥ 44 px (lo verifica `test:live` en 390×844); los interruptores son `role="switch"`.
- Hoja inferior: arrastrar hacia abajo la cierra, hacia arriba la alarga, tocar el asa alterna alta/baja. Cruzar
  los 720 px (girar el celular) la abre o la contrae. Solo un panel abierto a la vez en celular (evento
  `morfi:panel-open`, que usan Controles y Estilo). Respeta las áreas seguras (`env(safe-area-inset-*)`).
- Tocar a Morfi (un dedo, < 250 ms y < 8 px) lo hace reaccionar, en ciclo: Jump_Happy, Nod_Yes, Wave, Laugh.
  No reacciona si está hablando o en una escena. Arrastrar orbita; dos dedos hacen zoom.
- Morfi se encuadra en la parte del escenario que los paneles dejan libre (desplazamiento de vista, no
  movimiento de cámara) y se aleja un poco para caber sobre la hoja del celular.

## 2. Panel "Estilo"

Botón propio en la barra, junto a "Controles"; panel a la izquierda en pantallas anchas, hoja inferior en
celular. Dos bloques, cada uno con su interruptor y sus controles, más "Restablecer":

| Bloque | Controles (rango, valor por omisión) |
|---|---|
| **Contorno** (`outline`) | Grosor 0.5–4 px (1.3) · Grosor en lentes 1–3× (1.8) · Intensidad 0–1 (0.9) · Se adelgaza a lo lejos 0–1 (0.5) |
| **Efectos de movimiento** (`fx`) | Barrido al moverse rápido 0–1 (0.5) · Estirar y aplastar 0–1 (0.6) · Sensibilidad 0–1 (0.5) |

- **Contorno** (`outline.ts`): casco invertido de grosor constante en píxeles, más fino a distancia; sigue al
  skinning, a los morph targets de la cara y al barrido. Las manos, los objetos y las teclas son mallas "al
  revés" (solo se ven bien por tener material de dos caras): se detectan y se voltean para el casco. Sin
  línea dentro de la cara; las calcomanías de ojos y boca y los lentes no llevan contorno; el armazón
  (`Glasses_Frame`) lleva el grosor de lentes.
- **Barrido (smear)** (`fx_smear.ts`): empuja la piel hacia atrás, hacia una pose "estela" suavizada (`dqskin.ts`, `TRAIL_TAU` 0.05 s, independiente de los Hz de la pantalla, tope blando `tanh` de 45 mm) y no hacia el cuadro anterior: sin saltos escalonados al 100 %; máscara por hueso (brazos y
  manos 1, hombros 0.6, piernas 0.7, cabeza y tronco 0.15). Calcomanías, lentes y objetos reciben el mismo empuje
  desde su propia estela para no despegarse.
- **Estirar y aplastar** (`fx_squash.ts`): resorte sobre la velocidad de la cadera, aplicado a todo el cuerpo
  (el grupo `Morfi_Squash` contiene al modelo). Medido con 0.6: Jump_Happy 0.943–1.066, Celebrate 0.929–1.072.
- Los ajustes se guardan en `localStorage` (`morfi.style.v1`). `?lowpower` arranca con barrido 0; "reducir
  movimiento" del sistema arranca con los efectos apagados.
- Costo medido en una GTX 1070: ~3.5 ms por cuadro con todo apagado, 3.9–4.3 ms con todo prendido (casi todo es
  el contorno).
- Las transiciones sin mezcla (empezar o buscar en una escena, un clip sin fundido) llaman `style.cut()` para
  que los efectos no corran a través del salto.

## 3. Parámetros de URL

| Parámetro | Efecto |
|---|---|
| `?kiosk=1` | Pantalla de punto de venta: sin paneles y con el modo pantalla activo |
| `?clean=1` | Sin paneles (solo Morfi) |
| `?bg=dark` | Fondo oscuro |
| `?anim=Wave` | Clip con el que empieza (si no existe, Idle) |
| `?expr=happy` | Expresión con la que empieza |
| `?lowpower=1` | Resolución 1×, sombra 1024, contacto 256 y barrido en 0 |
| `?outline=0` / `?fx=0` | Contorno / efectos apagados (con `1` o cualquier otro valor, prendidos) |
| `?model=<url>` | Otro GLB en lugar de `models/morfi_live.glb` |
| `?dqdebug` | Carga `fx_debug.ts` (herramientas de depuración del skinning; no para producción) |
| `?scenes=<json>[&scenesglb=<glb>]` | **Solo con el servidor de desarrollo** (`npm run dev`): escenas de prueba |

## 4. API `window.morfi` y `postMessage`

Funciona también dentro de un iframe.

```js
morfi.play('Calculator')            // cualquier clip de morfi.actions (ignora nombres que no existen)
morfi.expression('surprised')       // capa de cara; 'neutral' o '' la quita (lista: morfi.expressions)
morfi.speak('Toca aquí para cobrar')// SOLO texto (sin audio): boca por texto; devuelve la duración (s). Máx. 500 caracteres
morfi.say('hola')                   // frase de voice/index.json con la voz elegida; devuelve su duración (s), 0 si no existe
morfi.say('hola', 'mark')           // con otra voz (clave de morfi.voices)
await morfi.scene('presentacion')   // carga las escenas la primera vez; false si no existe esa escena
morfi.stop()                        // calla y vuelve a Idle
morfi.follow(false)                 // que no siga con la mirada
morfi.kiosk(true)                   // modo pantalla
```

Lectura: `morfi.actions` (nombres de clips), `morfi.expressions`, `morfi.voices` (`{key, name, official}`),
`morfi.phrases` (`{key, label, text, mood, gesture}`), `morfi.scenes` (`{key, title, group, dur}`; vacío hasta
que cargan) y `morfi.status` (`playing`, `saying`, `speaking`, `voice`, `audio`, `audioTime`, `scene`
`{key, title, t, dur, paused, waiting}` o `null`, `sceneTime`, `cinema`, `mouth`, `mouthTime`).

Mensajes (`window.postMessage(obj, '*')` o `iframe.contentWindow.postMessage(obj, '*')`):

| `type` | Campos | Equivale a |
|---|---|---|
| `play` | `name` | `morfi.play(name)` |
| `speak` | `text` | `morfi.speak(text)` |
| `say` | `key`, `voice?` | `morfi.say(key, voice)` |
| `expression` | `name` | `morfi.expression(name)` |
| `scene` | `name` | `morfi.scene(name)` |
| `stop` | — | `morfi.stop()` |

```js
iframe.contentWindow.postMessage({ type: 'say', key: 'gracias' }, '*');
iframe.contentWindow.postMessage({ type: 'scene', name: 'Scene_Idea' }, '*');
```

Los nombres de escena son las claves del JSON de escenas: `Scene_Presentacion`, `Scene_Calculadora`,
`Scene_Idea`, `Scene_Ventas`, `Scene_Susto`, `Scene_Sueno` y `POS_Video` (consúltalos en `morfi.scenes`). Un
`say` o `scene` que llega por `postMessage` sin que la persona haya tocado la página puede toparse con la
política de audio del navegador: sale el aviso "Toca para activar el sonido".

**`window.morfiStyle`** (el estilo): `outline(on)`, `fx(on)`, `set(nombre, valor)` (`width`, `glasses`, `ink`,
`thin`, `smear`, `squash`, `sensitivity`, `outline`, `fx`; los valores se limitan a su rango), `get()` (copia de
los ajustes), `open(on = true)` (abre o cierra el panel) y `cut()`. No tiene mensajes `postMessage`.

Ganchos de prueba: `window.__morfiReady` (true cuando cargó todo), `window.__morfiScene` (la escena three) y
`window.__morfiCamera`.

## 5. Archivos publicados (`web/public/`)

| Ruta | Qué es |
|---|---|
| `models/morfi_live.glb` | Morfi: cuerpo, manos, tablet y calculadora, los 40 clips horneados, `Glasses_Frame`, shape keys. Comprimido (resample + meshopt) por `sync-live` |
| `models/morfi_live_face.json` | Constantes del shader de ojos y boca |
| `models/morfi_live_anims.json` | Curvas de cara de cada clip, las 18 expresiones y `label`/`group` de cada clip |
| `models/morfi_live_scenes.glb` | Solo animación de las escenas (mismos nombres de hueso que `morfi_live.glb`) y `POS_Video` |
| `models/morfi_live_scenes.json` | `{fps, scenes: {<Clip>: {title, group: "scene"\|"video", frames, audio, solo, camera: [[t, shot]…], props: {18 curvas de cara}}}}` |
| `voice/index.json` | Voz por omisión, las 10 voces, las frases (texto, `mood`, `gesture`) y la duración de cada clip por voz |
| `voice/<voz>/<frase>.mp3` y `.json` | Audio y alineación por letra (`chars`, `t0`, `t1`) y envolvente por 1/30 s (`env`) |
| `voice/scenes/<escena>.mp3` y `.json` | Audio de cada escena (líneas + efectos) y su alineación unida; `pos_video.mp3` es el audio del video del POS |
| `models/tests/index.json` | `[{id, label}]` de la prueba de modelos (opus, sonnet, haiku1, haiku2, haiku3) |
| `models/tests/<id>.json` y `.glb` | Entrada de escena de una prueba (`{fps, id, action, title, group: "test", frames, audio, solo, camera, props, model, costs, changes}`) y su animación (solo huesos, comprimida) |
| `voice/tests/<id>.mp3` | Audio compuesto de la prueba |
| `models/morfi.glb`, `models/views.json`, `refs/`, `look/` | Del visor técnico |

Tamaños reales (18-oct-2026, medidos tras `sync-live`, modelo `look7`):

| Archivo | Tamaño |
|---|---|
| `models/morfi_live.glb` | 8.3 MB (8 341 328 B) |
| `models/morfi_live_scenes.glb` | 1.7 MB (1 686 484 B) |
| `models/morfi_live_scenes.json` | 358 KB (366 296 B) |
| `models/morfi_live_anims.json` | 359 KB (367 050 B) |
| `voice/scenes/*.mp3` | 139–172 KB cada una las 6 escenas (ventas 170, susto 139, sueño 156, presentación 140, idea 145, calculadora 172 KB; sin cambio); `pos_video.mp3` 720 KB (737 011 B) |

Lo que baja un visitante: ~8.3 MB al entrar; las escenas (1.7 MB + 358 KB + su mp3) solo al abrir «Escenas».

Los `.glb` de `models/` van como git normal (no LFS: `.gitattributes`), así Vercel sirve el archivo real. Los mp3
también son git normal. `/models/*` se sirve con `Cache-Control: max-age=300`: un modelo nuevo puede tardar 5
minutos en llegar a quien ya visitó el sitio.

## 6. Cómo cargan las escenas

El modelo principal no incluye las escenas (son minutos de animación que casi nadie reproduce). `ScenePlayer`
(`scenes.ts`) pide `models/morfi_live_scenes.json` y, solo si existe y es JSON, `morfi_live_scenes.glb`:

- cuando la sección "Escenas" entra a la vista con el panel abierto, o
- a los ~3 s de reposo (`requestIdleCallback`), o
- la primera vez que se llama `morfi.scene(...)`.

Si no hay JSON, la sección dice "Las escenas llegan pronto." y Vercel registra un 404 inofensivo. Las claves del
JSON deben ser iguales a los nombres de los clips del GLB; una escena sin clip se omite. Hay que publicar juntos
`morfi_live_scenes.json`, `.glb` y `voice/scenes/*.mp3`.

## 7. Agregar cosas

**Una frase.** (1) Agrégala a `voice/phrases.json` (`key`, `text` con etiquetas `[excited]`/`[laughs]`… de
`eleven_v3`, `mood` = una expresión de `EXPRESSIONS`, `gesture` = una clave de `GESTURES` en `voice.ts`).
(2) Genera la voz (la llave solo va en el comando):
`XI_KEY=<llave> python voice/gen.py phrases --voices supervm` (sin `--voices` genera las 10 voces; `--force`
regenera lo que ya existe). Reescribe `web/public/voice/index.json`. (3) Si el texto es largo, agrega su botón
corto en `LABELS` de `voice.ts` (si no, el botón muestra la primera oración). (4) Revisa la toma
([morfi-guia.md](morfi-guia.md) §3).

**Una voz.** Agrega su entrada a `voice/voices.json` (`key`, `name`, `id` de ElevenLabs, `pitch` en semitonos
—0 si no se baja; con otro valor se baja con `rubberband` de ffmpeg, formantes preservados—, `note`) y corre
`gen.py phrases --voices <key>`. Para que sea la oficial, cambia `default` en `voices.json` y corre
`python voice/gen.py index`; las escenas usan siempre `supervm` (`anim/scenes.py` `VOICE`).

**Un clip.** Escribe la función en `scripts/ia3d/anim/actions_moves.py` (o el archivo que corresponda) y
regístrala en su diccionario (`MOVES`); agrega su `(etiqueta, grupo)` a `anim/catalog.py` (sin esa entrada
`export_face_anims.py` falla a propósito). Hornéalo y reexporta con la cadena de [motor.md](motor.md) §1.
Si es un gesto de frase, agrégalo a `GESTURES`.

**Una escena.** Pasos completos en [motor.md](motor.md) §8: líneas en `voice/scenes.json`, voz con
`gen.py lines`, tiempos y cámara en `PLAN` de `anim/scenes.py`, coreografía en su función de `scenes.py`,
audio y bake con `make_scenes.py`, exportar con `export_scenes.py`.

## 8. Publicar

Cadena completa (desde la raíz del repo; `B=/d/tools/bl.sh`; archivos intermedios en `work/ia3d/`, ignorado por
git). Los pasos de Blender están en [motor.md](motor.md) §1 (`anim7 → build_look → look4 → fix_glasses → look5 →
fix_body → look6 → fix_brows → look7`; `export_web.py`, `export_scenes.py` con `--scenes work/ia3d/morfi_ia_scenes3.blend`
y `export_face_anims.py` se corren sobre `look7`); al final:

```bash
python scripts/ia3d/export_face_anims.py --out work/ia3d/web/morfi_live_anims.json
cd web
npm run sync-live       # copia JSON, comprime los GLB (resample + meshopt) hacia public/models
npm run build           # tsc --noEmit && vite build
npm run test:live       # prueba headless (puerto 4318); requiere el build previo
```

`sync-live` falla si falta algún insumo; las escenas solo se copian si existe `morfi_live_scenes.glb` (y exige su
JSON). **El push a `claude/compassionate-cori-xn0xjj` despliega a producción** (integración Git de Vercel,
nunca el CLI): no hay rama de prueba. Antes de un push: `build` y `test:live` limpios. Se agregan los archivos
uno por uno (nunca `git add -A`: en la raíz hay un PNG de Miguel sin rastrear), incluidos `voice/`,
`web/public/voice/` y los `models/morfi_live*` nuevos; los commits van a nombre de Miguel, sin coautores. No
subir el GLB crudo de `work/` (16 MB) ni el `_resampled`.

### Lista de verificación

- `npx tsc --noEmit` (dentro de `web/`) sin errores.
- `npm run test:live`: recorre todos los clips (exige ≥ 26 y que coincidan con los del JSON; la tablet solo se ve
  en su clip), las 18 expresiones (deben cambiar la cara), `speak`, `say('hola')` (la boca se mueve con el audio),
  la primera escena y el video (el tiempo de la escena sigue al del audio), el interruptor del contorno,
  `postMessage`, fondo oscuro y celular (hoja, objetivos ≥ 44 px). Falla con cualquier error de consola.
  Necesita `PLAYWRIGHT_BROWSERS_PATH` apuntando a las carpetas de Chromium; las capturas quedan en
  `work/ia3d/viewer_test/`. Como exige escenas cargadas, antes de correrlo hay que haber hecho `sync-live`
  con las escenas.
- A ojo, con el contorno prendido y apagado: manos y mangas, lentes, cara cerrando los ojos, un salto
  (estirar y aplastar), una escena completa con cámara de cine, en escritorio y en celular.
- Después del deploy, abrir https://morfi-pet.vercel.app, comprobar la versión bajo el título del panel
  de Controles ("versión <commit> · <fecha>") y esperar hasta 5 min por el caché de `/models`.

## 9. Limitaciones conocidas

- Los zigzags blancos alrededor de los ojos cerrados ya no existen: eran islas del atlas de color base bajo los
  lentes (restos del marco pintado viejo) que se asomaban al volverse transparente la calcomanía. `export_web.py`
  (`flat_skin_in_lens_openings`) apunta esas caras a un punto liso del atlas con el mismo color de piel. Se revisó en
  la escena «Cinco minutitos» (ojos cerrados, cámara cercana).
- La sombra proyectada ignora el barrido (smear). En movimientos muy rápidos el contacto entre dedos y objeto
  puede aflojarse un poco (el barrido depende de la normal del vértice).
- Las escenas se probaron en navegador de escritorio (Chromium) con tacto emulado; no se han probado en
  dispositivos reales (iOS Safari).
- El audio por `postMessage` o API sin un toque previo puede bloquearlo el navegador.
- La pose del GLB difiere de la de Blender antes del skinning (la mano izquierda de `POS_Video` ~1.4°, 11 mm):
  viene de la exportación o la compresión de la animación, no del skinning.
- Los toques
  a la cara caen en la mandíbula o debajo: de frente, `Facepalm` se lee como "la cabeza descansa en la mano".
- `check_feet.py` usa la velocidad esperada de `Walk` para `Run` y `Sneak`, así que sus cifras para esos dos son
  incorrectas.

## 10. Prueba de modelos

Experimento: 5 modelos (Opus, Sonnet, 3 × Haiku) actúan la misma toma "Un día de ventas de Morfi" (1.5-2 min) con las
mismas 16 líneas de voz (`voice/tests_day.json`, audio en `web/public/voice/supervm/td_01..td_16`), cada uno con su
propia coreografía sobre el motor ([motor.md](motor.md)). Las herramientas son las mismas para todos; el manual de
trabajo (comandos, interfaz del módulo) está en `D:/tmp/delegate/ctx/experiment_tools.md`.

```bash
# 1. audio: líneas + pausas -> mp3 al nivel de las escenas + alineación unida (Python + ffmpeg, sin Blender)
python scripts/ia3d/compose_audio.py --timeline <dir>/timeline.json          # {"voice": "supervm", "lines": [["td_01", 0.6], ...]}
# 2. módulo de actuación (<dir>/perf.py: META + build(tl)) y hornear con las pasadas de producción de las escenas
python scripts/ia3d/bake_perf.py check   --module <dir>/perf.py --action Test_Opus     # rápido, sin Blender
python scripts/ia3d/bake_perf.py bake    --module <dir>/perf.py --action Test_Opus --out <dir>/perf.blend [--fast]
python scripts/ia3d/bake_perf.py verify  --blend <dir>/perf.blend --action Test_Opus [--sleeves]
python scripts/ia3d/bake_perf.py preview --blend <dir>/perf.blend --action Test_Opus --out <dir>/prev [--view cues|hands|face|...]
# 3. publicar: GLB sin comprimir en work/ia3d/web/tests/, JSON y audio al sitio, GLB comprimido a public/models/tests/
python scripts/ia3d/export_test.py --perf <dir>/perf.blend --action Test_Opus --model "<modelo>"
python scripts/ia3d/test_costs.py --id opus --creation 1.20 --review 0.40 --publish 0.10 --changes 7   # costos (USD) y cambios
```

- **Un solo camino a la web.** `export_test.py` abre `look7` (solo lectura), agrega la acción del `.blend` de `bake_perf.py`
  y escribe `work/ia3d/web/tests/<id>.glb` (crudo), `web/public/models/tests/<id>.json` y `web/public/voice/tests/<id>.mp3`;
  después corre `node web/scripts/sync-tests.mjs <id>` (resample + meshopt, igual que `sync-live`), que deja el GLB
  comprimido en `web/public/models/tests/<id>.glb`. `npm run sync-live` también comprime todos los tests que encuentre.
  Publicar otra vez cambia la animación pero conserva `model`, `costs` y `changes` del JSON.
- **Pasadas del horneado** (`anim/bakeclip.py`, el mismo código de `make_scenes.py`): tope de alcance, manos fuera del
  cuerpo, toques resueltos y suavizados, reposo sobre la piel, brazos IK -> FK con estirón de volumen constante, objeto
  en la mano; más (por omisión en `bake_perf.py`, `--no-fk-passes` las quita) las pasadas FK de `make_actions.py`: giro de
  manga, refinar contactos y pasada de cuerpo. `make_scenes.py bake` conserva su comportamiento (agrega `--fk-passes`
  para probarlas en las escenas). Medido: la escena `susto` (346 cuadros, 2 toques a la cara) tarda 19.6 min (el 78 % es el
  solucionador de toques); planea 1-2.5 h para 2 minutos y usa `--fast` (sin solucionadores, segundos) para iterar poses.
- **En el visor** (`tests.ts`, `scenes.ts`): `<details id="tests-box">`; al abrirlo lee `models/tests/index.json` y el JSON de
  cada id (los que falten dicen "En preparación"); el GLB de una entrada baja la primera vez que se toca su botón
  (`ScenePlayer.playTest`: también "desbloquea" el audio dentro del toque para iOS). API: `morfi.tests` (tras abrir la
  sección) y `await morfi.test('opus')`. La cámara de cine no sigue el movimiento de `root`: las tomas caminan en el sitio.
- **Probar** con tu propio servidor: `cd web && npx vite --port <puerto> --strictPort` y, con él corriendo,
  `node scripts/prueba-test.mjs --url http://localhost:<puerto>/ --ready opus,sonnet` (qué ids deben estar listos; revisa
  carga perezosa, tarjetas, costos, objetivos de 44 px, reproducción y cero errores de consola).
- Limpiar una prueba: borrar `web/public/models/tests/<id>.{json,glb}`, `web/public/voice/tests/<id>.mp3` y
  `work/ia3d/web/tests/<id>.glb` (dejar `index.json`).
- `test_costs.py --note "<texto>"` pone una nota en la tarjeta (p. ej. una fase cortada); `export_test.py` la conserva.
- Varios trabajadores comparten la PC: `anim/launch.py` deja correr como máximo 4 Blender a la vez en toda la máquina
  (`MORFI_BLENDER_SLOTS`, candados en `D:/tmp/morfi/blender_slots`); el que llega de más espera su turno.

### Resultado (18-oct-2026)

Cada modelo corrió por la API en tres fases separadas (creación, revisión cuadro por cuadro, publicación). Los créditos de
la API se acabaron a media revisión, así que ninguna revisión terminó y ninguna publicación la hizo el modelo: el supervisor
(sin costo de API) horneó lo que quedó escrito, verificó y publicó; la nota de cada tarjeta dice qué hizo el modelo y qué el supervisor.

| Modelo | Creación | Revisión | Total (USD) | Cambios | Verificación del supervisor |
|---|---|---|---|---|---|
| Opus 5.5 | 26.11 | 2.27 (cortada) | 28.38 | 0 | la de su creación: contactos ok, 0 mangas |
| Sonnet 5.5 | 8.94 (cortada en el horneado final) | — | 8.94 | — | 2 toques despegados un instante, brazo a 1.175 |
| Haiku 5.5 (1) | 0.96 (cortada en el horneado final) | — | 0.96 | — | mano dentro de cabeza/torso 68.5-70.7 s |
| Haiku 5.5 (2) | 2.23 | 0.24 (cortada) | 2.47 | 5 | 0 problemas, 0 mangas |
| Haiku 5.5 (3) | 2.67 | 0.14 (cortada) | 2.81 | 5 | 3 cuadros sueltos, 0 mangas |

Total del experimento: 43.56 USD. Lo que más costó fue **esperar**: la caché dura 5 min y un trabajador que sondea su
horneado cada ~10 min reescribe todo su contexto en cada consulta (Opus: ~20 de sus 26 USD de creación). Haiku 1 sondeaba
cada ~5 min y gastó 0.96. Precios deducidos (por millón de tokens de entrada): Opus 4, Sonnet 2, Haiku 0.5 USD; escritura de
caché 1.25x, lectura 0.05x, salida 5x. Opus y Sonnet se reanudaron una vez (un error del delegador los dejó esperando al
usuario): su costo de creación incluye releer su contexto al reanudar.

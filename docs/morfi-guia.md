# Guía de Morfi: quién es, cómo habla, cómo se anima y cómo se renderiza

Documento base para cualquier sesión (o el skill futuro, todavía **no creado**) que vaya a hacer algo con
Morfi: una animación, una escena con voz, un video o una función del visor web. Junta lo que Miguel aprobó y lo
que se aprendió produciendo el video del punto de venta y el laboratorio web (oct-2026). Los detalles están en
tres documentos más: [motor.md](motor.md) (motor de animación, cadena de construcción, escenas),
[ia3d.md](ia3d.md) (el modelo y su rig) y [laboratorio.md](laboratorio.md) (el visor web "Morfi en vivo").

## 1. Reglas de trabajo con Miguel (no negociables)

- **Háblale en español** (México), directo y sin rodeos. Muchas veces escribe por dictado desde el teléfono.
- **Todo en el disco D:**. Nada en C:. Temporales en `D:\tmp\morfi` (`TEMP`/`TMP` apuntando ahí en cada comando
  que use Python, Blender, ffmpeg o node; `/d/tools/bl.sh` ya lo hace para Blender).
- **Commits a su nombre** (M1gu3hb, huertabautistamiguel62@gmail.com), sin coautores ni firmas de Claude.
  Nunca `git add -A`: se agregan los archivos uno por uno (en la raíz hay un PNG suyo sin rastrear que no se toca).
  Todo lo que se hace se documenta y se sube al repositorio (petición de Miguel, 17-oct-2026).
- **No subir sus imágenes ni sus modelos a ningún servicio externo** sin preguntarle. Publicar el GLB y el audio
  de Morfi en el visor de Vercel es parte de su propio sitio.
- La rama `claude/compassionate-cori-xn0xjj` **es producción**: cada push publica https://morfi-pet.vercel.app.
  Se despliega solo por la integración de Git de Vercel (nunca con el CLI de Vercel). No hay rama de prueba:
  `npm run build` y `npm run test:live` limpios antes de cada push.
- La llave de ElevenLabs solo vive en el comando (`XI_KEY=... python ...`), nunca en archivos, memoria ni docs.
- Herramientas de paga (generación de imágenes, música, 3D, voces): preguntar antes.

## 2. Quién es Morfi

La mascota 3D de **Morphiq** (Astral Morphiq Systems), la marca de Miguel: sitios, presencia digital y el punto de
venta MorphiqPOS para negocios chicos (cafeterías, panaderías, tiendas).

- **Cómo se ve**: un ayudante pequeño (1.14 m con los cubos) de cabeza enorme (60 cm de ancho) y brazos
  cortos (20 cm del hombro a la muñeca), sudadera azul con capucha, lentes azul marino, cubitos de pixel que
  flotan sobre la cabeza (el hueso `pixels`, los cuadritos del logo). Ojos y boca son calcomanías con shader
  propio (`build_face.py`; en la web, `face.ts`).
- **Personalidad**: alegre, curioso, cálido, servicial, un poquito torpe (se le olvida que trae la calculadora
  en la mano, se espanta con el timbre de la caja, se queda dormido) y orgulloso de ayudar. Nunca sarcástico ni
  grosero. Celebra los logros del negocio como suyos ("cobramos", "vendimos"). Le habla a la persona de tú.
- **Cómo habla**: frases cortas, exclamaciones, muletillas tiernas ("a ver, a ver…", "¡uy!", "ay, Morfi…",
  "¡soy un genio!"), risitas. Explica sin tecnicismos. A veces piensa en voz alta (habla solito) y luego
  voltea a la cámara. Ejemplos reales: `voice/phrases.json` (12 frases del laboratorio) y `voice/scenes.json`
  (las líneas de las 6 escenas).
- **Lo que no hace**: no dice "con IA" ni nada que suene a IA; no inventa clientes, cifras ni testimonios
  presentados como reales; no promete funciones del producto que no existen; no usa logos de otras marcas.
- **Dirección de Miguel para la animación** (sus palabras): "más expresivas, más caricaturescas, ya con los
  efectos de movimiento", "muy vistoso, muy movido", "se deforme tantito, pero a cierto punto que parezca
  normal", "nunca raro ni deforme", "si se va a tocar la cara… se le alarga un poquito el brazo… que no se vea
  deforme", "cuando brinque, que se estire un poquito", "cada animación, cada escena completa… hazla tal cual
  como si fuera ya un video", "en algunas escenas que hable solito".

## 3. La voz oficial

- **Super VM** de ElevenLabs (voice id `gQRS0Lnh5XQOAqujMqUX`), modelo `eleven_v3`, idioma `es`,
  `stability 0.5`, `similarity_boost 0.8`, sin cambio de tono (`pitch 0`). Miguel la eligió el 17-oct-2026 entre 6
  candidatas; `voice/voices.json` guarda las 6 (`default: "supervm"`) y el laboratorio las deja para comparar.
  Las escenas siempre usan Super VM.
- Historia: el video del POS usó **Thorthugo** (`WOY6pnQ1WCg0mrOZ54lM`); le gustó lo amigable y "chiquito",
  pero a veces sonaba a mujer (medición de esa sesión: F0 mediana ~280 Hz, 62 % del tiempo arriba de 260 Hz). En
  el laboratorio queda como "Thorthugo grave": la misma toma 4 semitonos abajo (228 Hz). **Diego** es la voz de
  los videos de Morphiq *sin* Morfi: nunca para Morfi.
- `eleven_v3` entiende etiquetas de audio: `[excited]`, `[laughs]`, `[gasps]`, `[whispers]`, `[yawns]`, `[sighs]`.
  (En `voice/phrases.json` y `voice/scenes.json` se usan `[excited]`, `[laughs]`, `[gasps]`, `[whispers]` y
  `[yawns]`; `anim/scenes.py` los convierte —`TAGS`— en gestos y sonidos de la cara.) `gen.py` no manda
  `previous_text`/`next_text`: con v3 no se pueden.
- Generar (todo queda en `web/public/voice/<voz>/`, con la alineación por letra y la envolvente por 1/30 s que
  mueven la boca; el audio sale normalizado a −16 LUFS y a 96 kbps):

  ```bash
  XI_KEY=<llave> python voice/gen.py phrases                       # las 12 frases de "Que diga algo" en las 6 voces
  XI_KEY=<llave> python voice/gen.py phrases --voices supervm      # solo una voz (--force regenera las que ya existen)
  XI_KEY=<llave> python voice/gen.py lines voice/scenes.json --voice supervm   # líneas de las escenas
  python voice/gen.py index                                        # solo reescribe web/public/voice/index.json
  python scripts/ia3d/make_scenes.py audio                         # el audio de cada escena (líneas + pausas + efectos)
  ```

- **QA de cada toma** (obligatorio, procedimiento de las sesiones del video): transcribir con Whisper
  (`faster-whisper` small, `HF_HOME=D:\DevCaches\huggingface`) y comparar con el texto. Con una risa (`[laughs]`)
  Whisper alucina "jajaja…": transcribir otra vez con `word_timestamps=True`, `condition_on_previous_text=False` y
  el texto como `initial_prompt` para confirmar las palabras. Además se mide la duración y el nivel
  (`make_scenes.py audio` imprime LUFS y pico de cada escena).
- La alineación de ElevenLabs es floja: la primera letra después de una pausa suele "tragarse" el silencio previo
  ("Tampoco" empieza 0.4 s antes del sonido). `anim/scenes.py` ajusta cada palabra a los cuadros con voz de su
  propio audio (`refine`, umbral de envolvente `VOICED` 0.10, hasta `SNAP` 0.14 s) antes de usarla, para que la
  boca nunca se mueva en un silencio.
- Si alguna vez hay que buscar otra voz: biblioteca de ElevenLabs (las voces de la biblioteca se usan por id),
  medir F0 (mediana y % arriba de 260 Hz para descartar las que suenan a mujer), dispersión y precisión con
  Whisper, y mandarle a Miguel las mejores 6 para que elija.

## 4. Cómo se anima (principios)

Lo que Miguel aprobó como "súper expresivo" (video del POS v2) y lo que pidió para el laboratorio:

1. **Todo el cuerpo actúa.** Un gesto que mueve "dos partecitas" se ve rígido. Cada frase lleva un cambio de
   peso de un pie al otro (cadera, pelvis, columna en contra, talón que se despega), las rodillas ceden en las
   palabras con acento, el pecho se inclina hacia quien escucha (`anim/acting.py`).
2. **Caricaturesco pero nunca deforme**: anticipación antes de cada movimiento, sobreimpulso y asentamiento al
   llegar, arcos, entrada rápida y salida lenta, superposición (la cabeza y los cubos llegan después). Squash &
   stretch "tantito, que parezca normal": medido en los clips, cabeza y cuello (`.sy`) entre 0.89 y 1.11;
   columna, pecho y cadera solo ±3 % (deforman los brazos porque todos los huesos heredan la escala).
3. **Los brazos son cortos**: para tocarse la cara el brazo se estira **un poquito** (hasta 1.13 a lo largo, con
   el volumen conservado y la mano contraescalada: nunca un brazo de chicle ni una mano alargada). La cabeza es
   más ancha que los hombros: una mano "junto a la cara" a la altura de la cara queda dentro de la cabeza; para
   contar con los dedos la mano va al lado (x ≈ ±0.30, z ≈ 0.46). Técnica completa: [motor.md](motor.md) §7.
4. **Los ojos guían**: la mirada llega antes que la cabeza; cejas y párpados actúan siempre. La cabeza no baja de
   ~7° al mirar un objeto (con su cabezota, más abajo la cara deja de verse de frente y la barbilla choca con las manos).
5. **Las manos dicen**: variedad de formas de mano (`HAND_SHAPES` en `anim/motor.py`), pero dos formas a menos de
   4 cuadros una de otra se ven como un chasquido.
6. **Objetos en la mano de verdad**: lo que sostiene va en su mano (`contacts.hold_prop`), los toques son
   exactos (`contacts`), y al final se suaviza en el tiempo para que nada tiemble (`smooth_ik`, `smooth_touches`).
7. **Nada se ajusta a mano en Blender**: todo es código que se hornea y se verifica (`check_props.py`,
   `check_clearance.py`, `check_feet.py`, vistas previas con `preview_anim.py`).
8. **Cada clip termina cerca del reposo**: el visor lo mezcla con `Idle` en 0.35 s y no debe notarse.
9. **Encima del modelo**, en el visor web (panel "Estilo"): contorno fino de tinta (más grueso en los lentes),
   barrido (smear) en los movimientos rápidos y estirar/aplastar del cuerpo al brincar. En los videos, detalles
   dibujados de personalidad (foco de idea, gota de sudor, líneas de sorpresa) están bien; partículas y destellos
   decorativos, no.

Cómo escribir una acción, los canales, los contactos y las actuaciones largas: [motor.md](motor.md).

## 5. Escenas con voz (actuaciones completas)

Una escena es una sola toma continua, como un video: varias líneas de voz con pausas de actuación, el cuerpo
completo actuando, la boca sincronizada con el audio real y la cámara de cine en el visor. Hay 6 (presentación,
calculadora, idea, ventas, susto, sueño; en cuatro habla solito) más el video del POS.

1. Escribir las líneas en `voice/scenes.json` (`sc_<escena>_<n>`) con la personalidad de §2; en las escenas
   "solito" piensa en voz alta y no le habla a la cámara.
2. Generar la voz con Super VM (§3) y revisarla con Whisper.
3. Dirigir la escena en `scripts/ia3d/anim/scenes.py`: `PLAN` (cuándo entra cada línea, silencio final, efectos de
   sonido, cortes de cámara `wide`/`medium`/`close`/`face`) y la función de la escena con `Performance` + `Acting`
   para el cuerpo, `speak()` para la boca, expresiones que siguen al texto y objetos solo si la historia los pide.
4. `make_scenes.py audio` → `bake` → `merge` → `verify` → `preview` (mp4 con audio) y revisar a ojo cada una antes de
   publicar. Los comandos exactos están en [motor.md](motor.md) §8; la exportación y el reproductor del visor, en
   [laboratorio.md](laboratorio.md).

## 6. Render

**Blender (videos)**: Blender 4.5 portátil (`/d/tools/bl.sh`), Eevee, 1080×1920 a 30 fps, película transparente,
24 muestras (`videos/morfi-pos/tools/scene.py`), la luz de estudio de `scripts/ia3d/studio.py` y gestión de color
**Standard** (AgX y Khronos PBR Neutral cambian el azul de marca: lavanda y violeta). El material original se
queda (look "v1"). En la composición se le da a Morfi una gradación ligera (`eq=saturation=1.08:contrast=1.04`
sobre su capa, con el alfa intacto, en `tools/compose.py`). El modelo para un video nuevo es `look5` (la cadena
está en [motor.md](motor.md) §1); el video del POS se renderizó con `look3`.

Cadena del video del POS (`videos/morfi-pos/`, fuera del repo): `tools/vo.py` (voz) → `tools/timing.py`
(tiempos y lip-sync) → `tools/choreo.py` (actuación y cámara) → `tools/scene.py bake` (bake + contactos) →
`tools/scene.py render` (RGBA; la pantalla de la tablet es holdout y la UI del POS se ve desde la capa HTML) →
HyperFrames para las capas de fondo y frente → `tools/compose.py` → `tools/finish.sh` (master + `-hq` para el
chat + `-ligero` para el celular).

**Web**: el visor "Morfi en vivo" (three.js) con skinning de cuaterniones duales que respeta la escala por hueso,
como el "Preserve Volume" de Blender; materiales PBR del GLB, el shader de ojos y boca portado a GLSL, sombra de
contacto suave, tone mapping Neutral, contorno por casco invertido y efectos de movimiento. Detalles, parámetros
y cómo publicar: [laboratorio.md](laboratorio.md).

## 7. Lecciones aprendidas

**Animación y contactos**
- Las manos se salían de la manga al doblar la muñeca: `fix_wrists.py` (piel de la muñeca con el antebrazo,
  puño de la manga con el antebrazo y límite de giro). Va en el rig **antes** de resolver contactos (por eso
  `face3` es la base de `make_actions.py`).
- La mano temblaba sobre la tablet: el solver corrige un cuadro a la vez; se arregla con la tablet en la mano
  (`hold_prop`) y un suavizado temporal (`smooth_ik`). `videos/morfi-pos/tools/diag_jitter.py` lo mide. Lo mismo
  con una mano apoyada en la cara durante segundos: `smooth_touches` ancho + `rest_on_skin`.
- El IK de Blender estira sin límite: el motor topa el alcance (`MAX_REACH` 1.08, hasta 1.12 por clip).
- El estirón de un clip se quedaba pegado al siguiente (hueso sin escala keyada): `rigmap.bake` ahora escribe
  escala 1 en todo hueso que el clip no escala.
- Convertir el brazo a FK con tope de muñeca abre los toques 2-5 mm: hay que cerrarlos otra vez
  (`refine_contacts_fk`) y la pasada de cuerpo (`resolve_body_fk`) cambia algunas poses, así que se revisa a ojo.
- `fcurve.keyframe_points.insert(options={"FAST","REPLACE"})` falló en silencio en Blender 4.5 (hallazgo de una
  sesión anterior): se usa `keyframe_points.add` + `foreach_set` (`rigmap._fcurves`).
- Los canales del clip se **suman**: llamar dos veces a un ayudante dobla el efecto; un `.sy` escrito como delta
  sin iniciar en 1 explota (`c.sy` ya arranca en unos).
- El bake completo de 40 clips tarda más de una hora: se parte en grupos con `--only` y se une con `--merge`.

**Modelo y web**
- Los lentes y el armazón tenían triángulos visibles por geometría (no por el shader): se reconstruyeron limpios
  (`fix_glasses.py`: `Glasses_Frame` rígido en la cabeza + lentes `Lens_L/R` nuevos). El armazón pintado estaba
  esculpido 15–46 mm sobre la piel; se mide en un mapa cilíndrico de la cabeza.
- La web no mostraba bien la escala no uniforme de los huesos (squash & stretch): el skinning de cuaterniones
  duales ahora separa la parte rígida y una matriz de escala por hueso (error medio contra Blender: de 37 mm a
  0.06 mm en la cabeza de `POS_Video` cuadro 1292).
- ANGLE/D3D11 compiló mal un `struct` de GLSL (el cuerpo salía ~1.8× más grande con el barrido prendido): se quitó.
- Las manos, los objetos y las teclas son mallas "al revés" (se ven bien solo porque su material es de dos
  caras): el contorno las detecta y las voltea.
- Los zigzags blancos alrededor de los ojos cerrados **no** eran textura nueva ni lente: eran islas en forma de
  estrella del atlas de color base bajo los lentes (restos del marco pintado viejo) que se veían al volverse
  transparente la calcomanía. Arreglado en `export_web.py` (`flat_skin_in_lens_openings`): esas caras usan un punto
  liso del atlas con el mismo color de piel. Ya no se ven en la web.
- Con lentes que cubren toda la abertura, el material blanco translúcido aclaraba las pupilas: el lente web es
  negro con mezcla aditiva y `renderOrder` 2 (`face.ts`); las pupilas deben seguir oscuras.
- El tiempo de una escena en la web es el del elemento de audio (no un temporizador): así pausa, búsqueda o red
  lenta nunca dejan la boca atrás.
- Archivos de prueba (escenas falsas, GLB de prueba) nunca se dejan en `web/public/`: se publica lo que haya ahí.

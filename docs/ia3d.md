# Morfi con la malla de la IA 3D (Meshy) · rig, cara viva, materiales y animación

Esta ronda deja de modelar a Morfi con primitivas y usa la malla que generó el usuario con **Meshy**
("Blue Byte"): una sola pieza de 102 458 triángulos con textura de color de 8K, normal de 4K y
rugosidad/metal de 4K. Encima se pone todo lo necesario para animarlo con naturalidad.
Los archivos de la IA viven en `work/ia3d/` (ignorado por git) y **no se suben a ningún servicio**.

## 1. Los archivos recibidos

| Archivo | Qué es |
|---|---|
| `MORFI ESQ.glb` = `MORFI ESQUELETO.glb` | La misma malla con el "SmartRig" de Meshy (41 huesos). Son idénticos (mismo MD5). |
| `MORFI GBL 1.glb` | La misma malla sin esqueleto, a otra escala (altura 1.9). |
| `MORFI OBJ 1.zip` | La misma malla en OBJ, con la textura en PNG y sin los mapas de rugosidad ni normal. |
| `SUDADERA.glb` | Una sudadera suelta de otra IA (656 656 triángulos, texturas de 2K): cierre, cordones y bolsillos detallados. |

Las tres mallas de Morfi son la misma: normalizadas al marco del proyecto (altura con cubos 1.143,
pies en z = 0, mirando a −Y) dan la misma caja y la misma silueta. Medida contra las referencias con las
cámaras calibradas (`scripts/ia3d/render_contact.py` + `make_contact_sheet.py`), la IoU de silueta es
0.83 de frente, 0.75 en perfil, 0.88 de espalda y 0.82 en 3/4. Ajustando solo encuadre y altura sube a
0.85, 0.77, 0.88 y 0.90. Los perfiles de las referencias tienen la cara girada a cámara (ver
`art-direction.md` §11); el modelo no, por eso el perfil queda más bajo.

Soldada en las costuras de UV, la malla es **cerrada y sin aristas no-manifold**: un cuerpo de
50 337 vértices más dos de los cubos sueltos (`scripts/ia3d/mesh_report.py`).

## 2. El esqueleto de Meshy no sirve para animar

Con poses de prueba (`scripts/ia3d/pose_test.py`):
- el hueso del brazo derecho mueve 23 mil vértices, incluida la cara: al levantar el brazo se inclina la cabeza;
- los huesos de la columna no dominan ni un vértice: el torso queda repartido entre los muslos y el cuello;
- al agacharse la cabeza se estira.

## 3. Rig nuevo (`scripts/ia3d/build_rig.py`)

- Huesos con los nombres del proyecto (`scripts/morfi/rig.py`), colocados en los puntos de referencia de la
  malla: cadera 0.205, columna, pecho, cuello, cabeza desde z 0.515 (la capucha termina en 0.53), cubos en
  `pixels`, capucha en `hood`, brazos, mano, dedos, pulgar, piernas, pie y punta.
- **IK en las piernas** (`foot_ik.L/R`, `knee_pole.L/R`): los pies se quedan plantados aunque la cadera se mueva.
- Pesos: calor de Blender y luego correcciones por zonas. El torso se reparte por altura en la columna
  (el calor se lo daba a muslos y hombros). La cabeza es rígida: cara, lentes y patillas. La capucha nunca
  sigue a la cabeza. Los tenis van rígidos en pie y punta, y los cubos van en su propio hueso. Al final se suaviza
  en el grafo de la malla, con un máximo de 4 influencias.

## 4. Cara viva (`measure_face.py`, `inpaint_face.py`, `build_face.py`)

Meshy pintó los ojos y la boca en la textura, sobre una sola capa de superficie (no hay globo ocular).
- Se midieron en una vista frontal plana (`face_ortho.py`): contorno del ojo como dos elipses inclinadas
  (interior y exterior), iris, pupila y brillo, con sus colores.
- Se **borraron de la textura de 8K** (relleno con el degradado de la piel de alrededor, calculado en la vista
  frontal y devuelto al atlas texel por texel).
- Cada ojo es una calcomanía a 0.8 mm de la superficie, rígida con la cabeza, con un shader procedural que
  redibuja el ojo pintado. El iris se mueve con la mirada (`gaze_x/y`), los párpados se cierran (`blink_L/R`)
  y el párpado inferior sube al sonreír (`squint`). Donde el párpado cubre el ojo, la calcomanía es
  transparente y se ve la piel real del modelo.
- La boca es otra calcomanía: abre, cierra y redondea (`mouth_open` −1…1, `mouth_round`, `smile`).
  Para cerrarla, un shape key rellena la cavidad esculpida (2 cm) en el cuerpo y en la calcomanía.
- Cejas: shape keys `Brow_L/R` (suben o bajan 1.6 cm) y `Brow_In_L/R` (inclinan: preocupado / enojado) que mueven
  la piel de la ceja sin mover el armazón.
- Ojos expresivos: párpado caído (`lid_drop`), inclinado (`lid_angle`: enojo o tristeza), tamaño de pupila (`pupil`),
  ojos cerrados tranquilos (`eye_calm`). Boca: triste (`smile` < 0), de lado (`mouth_side`) y dientes (`teeth`).
- Todo se maneja con propiedades del rig (`Morfi_Rig["blink_L"]`, etc.) por drivers; 18 expresiones listas en
  `anim/motor.py` (`EXPRESSIONS`).

## 5. Animación (`scripts/ia3d/anim/`, `make_actions.py`)

Curvas por cuadro (30 fps) con interpolación monótona, más capas procedurales: respiración, micro movimiento
de cabeza, parpadeos y resortes para cubos y capucha (`curves.spring/jiggle`). Principios: anticipación,
los ojos antes que la cabeza y la cabeza antes que el cuerpo, arcos, retraso en manos y cubos, y asentamiento
con un ligero rebote.

Acciones (40; la lista con etiquetas y grupos está en [`docs/motor.md`](motor.md) §5): `Idle` (bucle de 5 s), `Wave`,
`Walk` (bucle, en el sitio), `Jump_Happy`, `Look_Around`, `Talk`, `Present`, `Nod_Yes`, `Shake_No`, `Dance` (bucle),
`Run`, emociones (`Laugh`, `Surprised`, `Sad`, `Angry`, `Scared`, `Calm`, `Celebrate`, `Shrug`), gestos (`Count_123`,
`Thumbs_Up`, `Point_Side`, `Idea`, `Think`), objetos (`Tablet`, `Calculator`, con contacto real del dedo) y 14
movimientos (`Spin`, `Hop_Steps`, `Dance_2`, `Bow`, `Yawn_Stretch`, `Victory`, `Wave_Both`, `Peek`, `Shiver`,
`Sneak`, `Sleepy`, `Tap_Foot`, `Facepalm`, `Blow_Kiss`). Cada una arranca y termina en el reposo y
define todos los huesos, gestos y escalas, así se encadenan en el NLA sin saltos. Además, 6 escenas completas con
voz (`Scene_*`, motor.md §8).

**Motor** (manos de 4 dedos articuladas, IK de brazos con tope de alcance, objetos, contactos exactos, cuerpo
sólido y verificación): ver [`docs/motor.md`](motor.md).

**Brazos cortos y cabeza enorme.** Los brazos miden 23 cm y la cabeza 60 cm de ancho: una mano levantada
entra en la cabeza. `check_clearance.py` mide en cada cuadro la distancia con signo de cada mano a la cabeza
y al torso, y `search_wave.py` buscó la pose del saludo. El saludo lleva el codo a la altura del hombro, el
antebrazo en diagonal y la palma al frente, y queda a ≥ 0.9 cm de la cabeza. El salto y el baile también
están verificados.

## 6. Materiales y estudio (`build_look.py`, `studio.py`)

Cada cara del modelo recibe un material según su color de textura y su zona: piel de felpa (sheen), sudadera
de fleece, playera de algodón, metal en el cierre y las puntas de los cordones (solo lo gris rodeado de sudadera),
tenis, armazón de acetato brillante y cejas mate. Los lentes tienen una capa de vidrio real con reflejos.

**Lentes y armazón (`fix_glasses.py` + `glasses_geom.py`).** La malla de Meshy trae el armazón pintado y esculpido
15–46 mm sobre la piel (abanicos de triángulos y una orilla en dientes de sierra), y los lentes eran una copia
cuadriculada de la cara. Un paso posterior, sobre cualquier .blend de la cadena y idempotente (guarda los datos
originales en la malla), mide el armazón pintado en un mapa cilíndrico de la cabeza y lo reconstruye como una sola
malla de cuadriláteros, `Glasses_Frame` (aros, puente y patillas, bordes redondeados, ranura para el lente, rígida
en el hueso de la cabeza); hace lentes polares nuevos (`Lens_L`/`Lens_R`, una cúpula lisa sobre toda la abertura);
aplana el relieve viejo bajo el armazón; mantiene la piel ≥ 3 mm detrás de los lentes y 0.6 mm detrás de las
calcomanías de los ojos; y saca la zona de los lentes de las claves de mejillas, boca y mandíbula. Medido: la
holgura del lente a la piel pasó de −11.1/−6.3 mm (la atravesaba) a +4.7/+3.5 mm; 8 882 triángulos de armazón y
2 × 1 440 de lentes. Uso: `$B -b work/ia3d/morfi_ia_look4.blend --python scripts/ia3d/fix_glasses.py -- --out
work/ia3d/morfi_ia_look5.blend` (cadena completa en motor.md §1).
Estudio: fondo curvo, luces de área (principal, relleno, contra, cenital y de rebote) y el HDRI de estudio
de Blender para los reflejos. Vista de color **Standard**: con AgX el azul de marca se volvía lavanda y con
Khronos PBR Neutral, violeta.

## 7. Cómo reconstruir

```bash
B=/d/tools/bl.sh    # Blender 4.5.14 portátil en D:, temporales en D:
$B -b --factory-startup --python scripts/ia3d/dump_mesh.py -- --model work/ia3d/morfi_esqueleto.glb --out work/ia3d/mesh.npz
python scripts/ia3d/analyze_regions.py --mesh work/ia3d/mesh.npz --tex work/ia3d/tex/glb1_1_Image_0.jpg --out work/ia3d/regions
$B -b --factory-startup --python scripts/ia3d/build_rig.py -- --glb work/ia3d/morfi_esqueleto.glb --regions work/ia3d/regions/regions.npz --out work/ia3d/morfi_ia_rig.blend
$B -b work/ia3d/morfi_ia_rig.blend --python scripts/ia3d/face_ortho.py -- --out work/ia3d/face
python scripts/ia3d/measure_face.py --dir work/ia3d/face          # face_features.json + eye_outline.json
python scripts/ia3d/inpaint_face.py --mesh work/ia3d/mesh.npz --tex work/ia3d/tex/glb1_1_Image_0.jpg --face work/ia3d/face --out work/ia3d/tex/base_color_clean.jpg
# manos, controles, cara, muñecas, acciones, materiales y lentes: ver docs/motor.md §1 (morfi_ia_rig_nohands -> morfi_ia_look5)
$B -b work/ia3d/morfi_ia_look.blend --python scripts/ia3d/render_showcase.py -- --out work/ia3d/showcase
```

## 8. Morfi en vivo (visor web, portada: `web/index.html`)

Es la portada del sitio (https://morfi-pet.vercel.app). El visor técnico del modelo procedural anterior
sigue igual en `web/tecnico.html`, enlazado desde ambas páginas.
Todo el detalle del laboratorio (paneles, parámetros de URL, API, archivos publicados, cómo publicar y verificar)
está en [`docs/laboratorio.md`](laboratorio.md). Lo que depende del modelo:
- `scripts/ia3d/export_web.py` se corre sobre el **look final** (`morfi_ia_look5.blend`: anim5 → look4 → lentes) y
  exporta `work/ia3d/web/morfi_live.glb`. Lleva el cuerpo, las manos articuladas, la tablet y la calculadora, los
  40 clips horneados cuadro por cuadro (IK de piernas y brazos ya aplicados), los shape keys de cejas y del
  relleno de la boca, `Glasses_Frame` (nodo y malla propios, rígido en el hueso de la cabeza, material
  `Glasses_Frame`) y materiales glTF (textura 4K, normal 2K, sheen y clearcoat). Los lentes `Lens_L`/`Lens_R`
  llevan un material marcador (`MorfiLens`) que el visor reemplaza. Escribe también `morfi_live_face.json` con las
  medidas de los ojos y la boca. Falla con `KeyError` si el .blend no trae los 40 clips de `ACTIONS`.
- `scripts/ia3d/export_face_anims.py` escribe `morfi_live_anims.json`: las curvas de la cara de cada acción
  (parpadeo, mirada, boca, cejas…), su etiqueta y grupo (`anim/catalog.py`) y las 18 expresiones, porque glTF no
  transporta las propiedades del rig.
- `scripts/ia3d/export_scenes.py` exporta las escenas aparte (`morfi_live_scenes.glb` solo con animación y su
  JSON), ver motor.md §1 y §8.
- `npm run sync-live` copia todo a `web/public/models/`, quita las claves de animación redundantes (`resample`) y
  comprime con meshopt. El usuario autorizó publicarlo (16-oct-2026): el GLB se versiona y Vercel lo sirve.
- `web/src/live/face.ts` porta a GLSL los shaders de ojos y boca de Blender. `director.ts` mezcla las acciones
  con transiciones de 0.35 s y vuelve al reposo al acabar cada una; encima, parpadeos al azar, ojos y cabeza que
  siguen al cursor o a la cámara, frases con la voz real y "modo pantalla".
- API para el chatbot (también dentro de un iframe): `window.morfi` (`play`, `speak`, `say`, `expression`, `scene`,
  `stop`, `follow`, `kiosk`, `status`…) y `postMessage` de tipo `play`, `speak`, `say`, `expression`, `scene`,
  `stop`; el estilo en `window.morfiStyle`. Ejemplos en laboratorio.md §4.
- Prueba: `cd web && npm run build && npm run test:live` (falla ante cualquier error de consola; capturas en
  `work/ia3d/viewer_test/`).

## 9. Pendiente

- La boca ya sigue el audio real en las frases y las escenas del laboratorio; el chatbot (`morfi.speak`) todavía
  mueve la boca solo con el texto.
- La sudadera suelta (`SUDADERA.glb`) no se usó: la sudadera de la malla principal se deforma bien con el rig
  y separarla dejaría un hueco sin cuerpo debajo. Sirve para un primer plano o para simular tela más adelante.

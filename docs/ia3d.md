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
- Cejas: shape keys `Brow_L/R` que suben o bajan la piel de la ceja sin mover el armazón.
- Todo se maneja con propiedades del rig (`Morfi_Rig["blink_L"]`, etc.) por drivers.

## 5. Animación (`scripts/ia3d/anim/`, `make_actions.py`)

Curvas por cuadro (30 fps) con interpolación monótona, más capas procedurales: respiración, micro movimiento
de cabeza, parpadeos y resortes para cubos y capucha (`curves.spring/jiggle`). Principios: anticipación,
los ojos antes que la cabeza y la cabeza antes que el cuerpo, arcos, retraso en manos y cubos, y asentamiento
con un ligero rebote.

Acciones: `Idle` (bucle de 5 s), `Wave`, `Walk` (bucle, en el sitio), `Jump_Happy`, `Look_Around`, `Talk`, `Present`,
`Nod_Yes`, `Shake_No`, `Dance` (bucle). Cada una arranca y termina en el reposo y define todos los huesos y
gestos, así se encadenan en el NLA sin saltos.

**Brazos cortos y cabeza enorme.** Los brazos miden 23 cm y la cabeza 60 cm de ancho: una mano levantada
entra en la cabeza. `check_clearance.py` mide en cada cuadro la distancia con signo de cada mano a la cabeza
y al torso, y `search_wave.py` buscó la pose del saludo. El saludo lleva el codo a la altura del hombro, el
antebrazo en diagonal y la palma al frente, y queda a ≥ 0.9 cm de la cabeza. El salto y el baile también
están verificados.

## 6. Materiales y estudio (`build_look.py`, `studio.py`)

Cada cara del modelo recibe un material según su color de textura y su zona: piel de felpa (sheen), sudadera
de fleece, playera de algodón, metal en el cierre y las puntas de los cordones (solo lo gris rodeado de sudadera),
tenis, armazón de acetato brillante y cejas mate. Los lentes tienen una capa de vidrio real con reflejos.
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
$B -b work/ia3d/morfi_ia_rig.blend --python scripts/ia3d/build_face.py -- --features work/ia3d/face/face_features.json --out work/ia3d/morfi_ia_face.blend
$B -b work/ia3d/morfi_ia_face.blend --python scripts/ia3d/make_actions.py -- --out work/ia3d/morfi_ia_anim.blend
$B -b work/ia3d/morfi_ia_anim.blend --python scripts/ia3d/build_look.py -- --regions work/ia3d/regions/regions.npz --face work/ia3d/face --out work/ia3d/morfi_ia_look.blend
$B -b work/ia3d/morfi_ia_look.blend --python scripts/ia3d/render_showcase.py -- --out work/ia3d/showcase
```

## 8. Morfi en vivo (visor web, `web/live.html`)

Página nueva, aparte del visor técnico del modelo procedural (`index.html`, que no cambia).
- `scripts/ia3d/export_web.py` exporta `work/ia3d/web/morfi_live.glb`. Lleva el cuerpo con 32 huesos, las 10 acciones
  horneadas cuadro por cuadro (el IK de las piernas y el pivote de los pies ya aplicados), los shape keys de cejas
  y del relleno de la boca, y materiales glTF (textura 4K, normal 2K, sheen y clearcoat). Escribe también
  `morfi_live_face.json` con las medidas de los ojos y la boca.
- `scripts/ia3d/export_face_anims.py` escribe `morfi_live_anims.json`: las curvas de la cara de cada acción
  (parpadeo, mirada, boca, cejas…), porque glTF no transporta las propiedades del rig.
- `npm run sync-live` copia todo a `web/public/models/` y comprime la geometría con meshopt (8.8 → 4.8 MB).
  **El GLB está en `.gitignore`**: es el modelo del usuario y no se publica sin su permiso.
- `web/src/live/face.ts` porta a GLSL los shaders de ojos y boca de Blender. `director.ts` mezcla las acciones
  con transiciones de 0.35 s y vuelve al reposo al acabar cada una. Encima añade parpadeos al azar, ojos y
  cabeza que siguen al cursor o a la cámara, habla a partir de un texto y, en "modo pantalla", pequeñas
  acciones solas.
- Clic sobre Morfi: reacciona (salto, sí, saludo). Parámetros de URL: `?kiosk=1` (pantalla de punto de venta,
  sin panel), `?clean=1`, `?bg=dark`, `?anim=Wave`, `?lowpower=1`.
- **API para el chatbot** (también funciona dentro de un iframe):
  ```js
  morfi.play('Wave')                      // Idle, Wave, Talk, Nod_Yes, Shake_No, Look_Around, Present, Jump_Happy, Walk, Dance
  morfi.speak('¡Hola! ¿En qué te ayudo?') // mueve la boca con el texto; devuelve la duración en s
  iframe.contentWindow.postMessage({ type: 'speak', text: 'Claro, te explico…' }, '*')
  iframe.contentWindow.postMessage({ type: 'play', name: 'Nod_Yes' }, '*')
  ```
- Prueba: `npm run build && npm run test:live`. Recorre las 10 animaciones, el habla, `postMessage`, el fondo
  oscuro y el celular, y falla ante cualquier error de consola (capturas en `work/ia3d/viewer_test/`).

## 9. Pendiente

- Publicar en Vercel requiere subir el GLB (el modelo del usuario): pedir permiso antes.
- Labios sincronizados con audio real (hoy la boca sigue el texto); con una voz TTS se puede mover con la amplitud.
- La sudadera suelta (`SUDADERA.glb`) no se usó: la sudadera de la malla principal se deforma bien con el rig
  y separarla dejaría un hueco sin cuerpo debajo. Sirve para un primer plano o para simular tela más adelante.

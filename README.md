# Morfi 3D · Astral Morphiq Systems

Modelo 3D completo de **Morfi**, la mascota de Astral Morphiq Systems, reconstruido a partir de las 15 imágenes de `references/`. Todo el personaje (geometría, texturas, materiales, esqueleto, animaciones, cámaras de estudio, renders, GLB y visor web) se **genera desde cero con scripts reproducibles**; nada está esculpido a mano ni depende de archivos externos.

| | |
|---|---|
| Fuente editable | `source/morfi_master.blend` (Blender 4.5 LTS, con rig y 6 acciones) |
| GLB master | `exports/morfi_master.glb` (alta resolución, texturas 2K–4K) |
| GLB web | `exports/morfi_web.glb` (ligero, texturas JPEG ≤2K) |
| Piezas sueltas | `exports/parts/morfi_*.glb` (sudadera, playera, tenis, lentes, cubos, laptop, cuerpo base, cabeza) |
| Renders | `renders/` (6 vistas, hero, hero con wordmark, transparentes, piezas, comparativas, giro 360° `morfi_turntable.mp4`, vista previa de animaciones) |
| Visor | `web/` (Three.js + TypeScript + Vite) |
| Documentación | `docs/art-direction.md` (decisiones y medidas), `docs/validation.md` (resultados de validación) |

> **Nueva línea de trabajo (oct-2026):** el personaje animado sale ahora de la malla de la IA 3D (Meshy), con
> rig nuevo, ojos y boca animables, materiales realistas y 10 animaciones. Ver `docs/ia3d.md`. Lo de abajo
> describe el modelo procedural anterior (rondas 1–11). En Vercel, la portada es **Morfi en vivo** (`web/index.html`) y el
> visor técnico del modelo procedural está en `web/tecnico.html`.

Los binarios (`*.blend`, `*.glb`, `*.mp4`) se versionan con **Git LFS** (`.gitattributes`). Tras clonar: `git lfs install && git lfs pull`.

## Qué incluye el personaje

- **Cabeza** paramétrica (superelipse ajustada a los contornos de las referencias) con atlas de color/rugosidad horneado: zona celeste facial **calcada de las referencias** por proyección desde sus cámaras calibradas (lámina 14 de frente; perfiles 03/05 y 3/4 06 para los lados), cuña de "nariz", boca con cavidad real y lengua, línea de párpado.
- **Ojos** esféricos reales con iris y pupila, córnea transparente y brillo puntual; miran a cámara en las vistas frontales (se puede desactivar con `--no-eyes-follow`).
- **Lentes** de montura negra cuadrada-redondeada, cristales delgados, bisagras y patillas.
- **Tres cubos** en la cabeza (grande izquierda, mediano arriba-derecha, pequeño abajo-derecha).
- **Cuerpo base** de una pieza: piernas, brazos y manos con **pulgar + 3 dedos**.
- **Playera** gris jaspeada con la **M** azul en relieve (solo en la playera).
- **Sudadera abierta** negra con capucha (colgando en la espalda con volumen, como en 04/05/07; para la foto de producto 08 hay un segundo estado con la capucha levantada, `Hoodie_Product`), bolsillos, cierre metálico de dos hileras, jalador, cordones con puntas metálicas, puños y dobladillo acanalados; tela con grosor real y holgura respecto al cuerpo.
- **Tenis** blancos izquierdo/derecho con suela, puntera, lengüeta, dos correas con ojales y talón azul.
- **Laptop** cerrada con **dos cuadrados azules**; aparece en la pose Hero, sujeta por la mano derecha.
- **Textura fina** tipo laberinto (la que se ve en piel, sudadera y playera de las referencias) como mapas de color + normal tileables, idénticos en Cycles y en glTF.
- **Esqueleto** (cadera, columna, cuello, cabeza, ojos, cubos, brazos, manos, dedos, pulgar, piernas, pies) con pesos calculados; la ropa se deforma con el cuerpo.
- **Acciones**: `Pose_Neutral`, `Pose_Hero`, `Idle`, `Walk`, `Run`, `Wave`, más una pose por toma de referencia (`Ref_front`, `Ref_back`, …).

## Requisitos (versiones probadas)

| Herramienta | Versión |
|---|---|
| Blender | 4.5.14 LTS (headless funciona) |
| Python de Blender | 3.11 + `numpy 1.26.4`, `scikit-image 0.26`, `scipy 1.17`, `pillow 12.3` |
| Python del sistema (comparativas y calibración) | 3.x + `numpy`, `scipy`, `pillow`, `rembg` (BiRefNet) |
| Node.js / npm | 22.x / 10.x |
| ffmpeg | 6.x (solo para el MP4 del giro 360°) |
| Git LFS | 3.x |

Instalar los módulos dentro del Python de Blender:

```bash
BPY=$(dirname $(readlink -f $(which blender)))/4.5/python/bin/python3.11
$BPY -m ensurepip && $BPY -m pip install numpy==1.26.4 scikit-image==0.26.0 scipy pillow
```

## Reconstruir todo desde cero

```bash
# 1. geometría + texturas + materiales + estudio (≈6 min)
blender -b --python scripts/build_model.py -- --out work/final/final.blend --quality final
# 2. esqueleto, pesos y animaciones -> fuente editable
blender -b work/final/final.blend --python scripts/rig_model.py -- --out source/morfi_master.blend

# 3. renders (Cycles)
B=source/morfi_master.blend
blender -b $B --python scripts/render_views.py  -- --out renders/views --samples 128 --hide Laptop
blender -b $B --python scripts/render_views.py  -- --out renders/transparent --samples 64 --transparent --hide Laptop
blender -b $B --python scripts/render_hero.py   -- --out renders --samples 160
blender -b $B --python scripts/render_parts.py  -- --out renders/parts --samples 64
blender -b $B --python scripts/render_turntable.py -- --frames 144 --fps 24 --res 600x720 --samples 10 --out work/turntable
ffmpeg -y -framerate 24 -i work/turntable/f_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart renders/morfi_turntable.mp4

# 4. exportar GLB (master, web, piezas) y comprobarlos
blender -b $B --python scripts/export_assets.py
blender -b --factory-startup --python scripts/validate_assets.py -- --glb exports/morfi_web.glb
(cd web && npm ci && npm run validate)        # Khronos glTF-Validator -> docs/gltf-validation.json

# 5. comparativas con las referencias (lado a lado + IoU de silueta)
python3 scripts/make_comparisons.py           # -> renders/comparisons/, docs/metrics.json
```

### Calce con las referencias (cámara y pose por toma)

Cada imagen de referencia se "fotografía" con su propia cámara y pose, calibradas contra su silueta (ver `docs/art-direction.md` §7):

```bash
pip install "rembg[cpu]" scipy pillow numpy          # Python del sistema
python3 scripts/ref_masks.py                          # siluetas exactas -> references_masks/
blender -b source/morfi_master.blend --python scripts/dump_points.py -- --pose neutral --out work/calib/points_neutral.npz
blender -b source/morfi_master.blend --python scripts/dump_points.py -- --pose hero --out work/calib/points_hero.npz
python3 scripts/fit_cameras.py                        # camera_views en config/morfi.json
blender -b source/morfi_master.blend --python scripts/dump_skin.py -- --out work/calib/skin.npz
python3 scripts/fit_view_poses.py                     # view_poses (+ retoque de cámara, giro de los cubos)
# después: rig_model.py crea las acciones Ref_<vista> y render_views.py las usa
blender -b source/morfi_master.blend --python scripts/fit_gaze.py   # view_gaze: mirada por toma (pupilas; también la lámina 14)
python3 scripts/hero_landmarks.py references/00_Morfi_master_wordmark.png renders/hero_wordmark.png   # lentes y cabeza de la toma hero
blender -b source/morfi_master.blend --python scripts/fit_gaze.py -- --views hero   # mirada hero, una vez calzada la pose de la cabeza
blender -b source/morfi_master.blend --python scripts/dump_points.py -- --pose neutral --keep-laptop --out work/calib/points_parts.npz
python3 scripts/fit_part_cameras.py                   # part_cameras: cámara de cada lámina 08–14
python3 scripts/eval_silhouettes.py work/calib/points_neutral.npz   # IoU rápido sin renderizar
python3 scripts/residuals.py --overlays               # qué pieza causa cada píxel de diferencia, por vista
python3 scripts/face_landmarks.py references/02_Morfi_frente.png renders/views/front.png   # rasgos de la cara
scripts/iterate_shapes.sh prueba [config.json]        # ciclo rápido de formas: borrador -> IoU de las 6 vistas
scripts/iterate_face.sh prueba [config.json]          # ciclo rápido de cara: borrador -> rig -> frente -> medidas
```

En los perfiles (03, 05) la cara está dibujada girada hacia la cámara sobre una cabeza de perfil puro; `render_views.py` reproduce esa trampa de cámara con `scripts/morfi/facecheat.py` (config `face_cheat`: grados por toma y relieve conservado), solo en el render de esa toma: el `.blend` maestro no cambia, y el GLB web la lleva como morph `Shot_<vista>` que el visor activa cuando la cámara está alineada con esa foto (`docs/art-direction.md` §11–12).

`fit_view_poses.py` compara contorno y zonas de color (azul / negro / blanco-gris) con un z-buffer del modelo; `--outline-only` usa solo el contorno. Las vistas se renderizan con el set de luces girado con la cámara de cada toma (como en las fotos de producto de referencia); `--world-lights` lo desactiva.

`--quality draft` genera una versión rápida (≈1–2 min) para iterar. Todos los parámetros (medidas, colores, cámara, luces) están en `config/morfi.json`.

## Visor web

Publicado en Vercel: **https://morfi-pet.vercel.app** (proyecto `morfi-pet`, carpeta `web/`, se redespliega con cada push a la rama). El panel muestra la ronda y el commit de lo que se ve.

```bash
cd web
npm ci
npm run sync-assets  # copia exports/*.glb a web/public/models, comprime morfi.glb (meshopt) y escribe views.json
npm run dev          # Vite en local
npm run build        # build estático en web/dist (base relativa, se puede servir en cualquier ruta)
npm run test:e2e     # prueba de humo con Chromium headless -> renders/viewer/*.png
```

Funciones:
- **Cámara y vistas**: órbita, zoom y táctil. Seis vistas predefinidas con la cámara (lente y giro) y la pose calibradas de cada referencia. Mientras la cámara está alineada con una foto, la cara toma la forma de esa toma: ojos hacia la cámara con la mirada ajustada y, en los perfiles, la trampa de cámara (morphs `Shot_<vista>` del GLB). Al mover la cámara la cara vuelve a la normal.
- **Shader "Fiel a la foto"** (por defecto). Las referencias son fotos de producto con la luz fija respecto de la cámara, así que el sombreado de cada material depende solo de la normal vista desde la cámara. `npm run capture-look` renderiza el propio GLB del visor con la cámara y la pose de cada toma (pasadas de albedo, normal y material), divide la foto por el albedo píxel a píxel y acumula la razón por material en una MatCap de 64×64. `scripts/build_look.py` la ajusta con armónicos esféricos de banda 3 más el residuo medido y la guarda en `web/public/look/`. En el visor cada material se pinta como albedo × MatCap(normal) × sombra de la luz principal, con un segundo MatCap para el celeste de la cara y una sombra de contacto suave en el piso. "Físico (PBR)" usa los materiales glTF con luz de estudio.
- **Comparar con la foto**: superponer, cortina, diferencia y lado a lado, con la foto de esa vista al mismo encuadre.
- **Sonido** sintetizado con WebAudio, sin archivos: transición de cámara, pasos sincronizados con caminar y correr, saludo, campanita de la pose hero, "boop" al tocar a Morfi (rebota) y música ambiental opcional.
- **Ropa y accesorios** (mostrar/ocultar, preset "cuerpo base"), fondo claro/oscuro/transparente, modos arcilla y alambre, animaciones (Neutral, Hero, Idle, Caminar, Correr, Saludar), captura PNG al tamaño de las referencias (1145×1374, mismo encuadre) y descarga del GLB.
- **Parámetros de URL**: `?model=…` para otro GLB, `?shading=pbr`, `?lowpower=1` para equipos sin GPU, `?clean=1` para ocultar el panel.

La piel se deforma con cuaterniones duales (`web/src/dqskin.ts`), como el "Preserve Volume" de Blender con el que se pesó el rig; `?dq=0` usa la mezcla lineal de three.js.

Medir el shader contra las fotos: `npm run look-eval` (renderiza las 6 tomas en `work/look/eval/`) y `python3 scripts/eval_look.py` (ΔE por vista). Revisar poses y animaciones como las deforma el visor: `node scripts/pose-shots.mjs <carpeta> '[["Wave", 1.0, 0, 5, 1.6, "saludo"]]'` (animación, segundo, acimut, elevación, distancia, nombre).

## Uso en otras herramientas

- **Blender**: abrir `source/morfi_master.blend`; las acciones están en el *Action Editor* del objeto `Morfi_Rig`. La cámara `Cam_hero` reproduce el encuadre principal.
- **Three.js / Babylon / Unity / Unreal / Godot**: importar `exports/morfi_web.glb` (o el master). Usa `KHR_materials_sheen`, `KHR_materials_transmission`, `KHR_materials_clearcoat`, `KHR_materials_specular`, `KHR_materials_ior` y `KHR_materials_emissive_strength` (brillo de los ojos); las 6 animaciones van incluidas como clips separados, más las 6 poses por toma `Ref_<vista>` (una pose estática por referencia).
- Convención de ejes y unidades: ver `docs/art-direction.md` §1 (altura sin cubos = 1.0).

## Limitaciones conocidas

Ver `docs/validation.md` → *Diferencias pendientes*. En resumen: las referencias son renders de IA independientes y no son geométricamente consistentes entre sí (cámara, posición de manos y pies, tamaño de los cubos en perfil), así que ningún modelo 3D único puede coincidir píxel a píxel con las 6 vistas a la vez; el modelo resuelve esas contradicciones con la prioridad del encargo (master `00` → vistas `02–07` → láminas de piezas) y las comparativas muestran dónde quedan diferencias.

## Estructura

```
config/morfi.json        parámetros del personaje
scripts/morfi/           módulos: sdf, head, face, body, clothes, shoes, accessories, laptop, materials, textures, rig, scene
scripts/*.py             construcción, rig, renders, exportación y validación
references/              15 imágenes originales (sin modificar)
docs/                    dirección de arte, validación, kit original
source/ exports/ renders/ textures/   resultados (binarios en LFS)
web/                     visor Three.js
```

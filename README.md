# Morfi 3D · Astral Morphiq Systems

Modelo 3D completo de **Morfi**, la mascota de Astral Morphiq Systems, reconstruido a partir de las 15 imágenes de `references/`. Todo el personaje (geometría, texturas, materiales, esqueleto, animaciones, cámaras de estudio, renders, GLB y visor web) se **genera desde cero con scripts reproducibles**; nada está esculpido a mano ni depende de archivos externos.

| | |
|---|---|
| Fuente editable | `source/morfi_master.blend` (Blender 4.5 LTS, con rig y 6 acciones) |
| GLB master | `exports/morfi_master.glb` (alta resolución, texturas 2K–4K) |
| GLB web | `exports/morfi_web.glb` (ligero, texturas JPEG ≤2K) |
| Piezas sueltas | `exports/parts/morfi_*.glb` (sudadera, playera, tenis, lentes, cubos, laptop, cuerpo base, cabeza) |
| Renders | `renders/` (6 vistas, hero, hero con wordmark, transparentes, piezas, comparativas, giro 360°) |
| Visor | `web/` (Three.js + TypeScript + Vite) |
| Documentación | `docs/art-direction.md` (decisiones y medidas), `docs/validation.md` (resultados de validación) |

Los binarios (`*.blend`, `*.glb`, `*.mp4`) se versionan con **Git LFS** (`.gitattributes`). Tras clonar: `git lfs install && git lfs pull`.

## Qué incluye el personaje

- **Cabeza** paramétrica (superelipse ajustada a los contornos de las referencias) con atlas de color/rugosidad horneado: zona celeste facial (no máscara blanca), cuña de "nariz", boca con cavidad real y lengua, línea de párpado.
- **Ojos** esféricos reales con iris y pupila, córnea transparente y brillo puntual; miran a cámara en las vistas frontales (se puede desactivar con `--no-eyes-follow`).
- **Lentes** de montura negra cuadrada-redondeada, cristales delgados, bisagras y patillas.
- **Tres cubos** en la cabeza (grande izquierda, mediano arriba-derecha, pequeño abajo-derecha).
- **Cuerpo base** de una pieza: piernas, brazos y manos con **pulgar + 3 dedos**.
- **Playera** gris jaspeada con la **M** azul en relieve (solo en la playera).
- **Sudadera abierta** negra con capucha, bolsillos, cierre metálico de dos hileras, jalador, cordones con puntas metálicas, puños y dobladillo acanalados; tela con grosor real y holgura respecto al cuerpo.
- **Tenis** blancos izquierdo/derecho con suela, puntera, lengüeta, dos correas con ojales y talón azul.
- **Laptop** cerrada con **dos cuadrados azules**; aparece en la pose Hero, sujeta por la mano derecha.
- **Textura fina** tipo laberinto (la que se ve en piel, sudadera y playera de las referencias) como mapas de color + normal tileables, idénticos en Cycles y en glTF.
- **Esqueleto** (cadera, columna, cuello, cabeza, ojos, cubos, brazos, manos, dedos, pulgar, piernas, pies) con pesos calculados; la ropa se deforma con el cuerpo.
- **Acciones**: `Pose_Neutral`, `Pose_Hero`, `Idle`, `Walk`, `Run`, `Wave`.

## Requisitos (versiones probadas)

| Herramienta | Versión |
|---|---|
| Blender | 4.5.14 LTS (headless funciona) |
| Python de Blender | 3.11 + `numpy 1.26.4`, `scikit-image 0.26`, `scipy 1.17`, `pillow 12.3` |
| Python del sistema (comparativas) | 3.x + `numpy`, `scipy`, `pillow` |
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

`--quality draft` genera una versión rápida (≈1–2 min) para iterar. Todos los parámetros (medidas, colores, cámara, luces) están en `config/morfi.json`.

## Visor web

```bash
cd web
npm ci
npm run dev          # copia exports/*.glb a web/public/models y abre Vite
npm run build        # build estático en web/dist (base relativa, se puede servir en cualquier ruta)
npm run test:e2e     # prueba de humo con Chromium headless -> renders/viewer/*.png
```

Funciones: órbita / zoom / táctil, 6 vistas predefinidas (mismos ángulos que las referencias), mostrar/ocultar sudadera, playera, tenis, lentes, cubos y laptop, preset "cuerpo base", fondo claro/oscuro/transparente, modos arcilla y alambre, animaciones (Neutral, Hero, Idle, Caminar, Correr, Saludar), captura PNG y descarga del GLB. Parámetros de URL: `?model=morfi_master.glb` para cargar el master, `?lowpower=1` para equipos sin GPU.

## Uso en otras herramientas

- **Blender**: abrir `source/morfi_master.blend`; las acciones están en el *Action Editor* del objeto `Morfi_Rig`. La cámara `Cam_hero` reproduce el encuadre principal.
- **Three.js / Babylon / Unity / Unreal / Godot**: importar `exports/morfi_web.glb` (o el master). Usa `KHR_materials_sheen`, `KHR_materials_transmission`, `KHR_materials_clearcoat`, `KHR_materials_specular` y `KHR_materials_ior`; las 6 animaciones van incluidas como clips separados.
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

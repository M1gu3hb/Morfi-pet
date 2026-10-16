# Traspaso de sesión · Morfi 3D (estado al 15-oct-2026)

Este documento es para que una sesión nueva de Claude Code (por ejemplo una sesión
local en la computadora del usuario) continúe el trabajo **exactamente donde se quedó**
la sesión en la nube. Léelo completo antes de hacer nada. El README y
`docs/art-direction.md` / `docs/validation.md` tienen el detalle técnico de cada ronda.

---

## 1. Quién, qué y cómo hablarle

- El usuario es el dueño de la marca **Morphiq** (Astral Morphiq Systems). Morfi es su mascota.
- Habla **español** (México), muchas veces por dictado de voz, desde el teléfono. Respóndele en español,
  claro y sin rodeos. Reporta resultados con honestidad (si algo no quedó, dilo).
- Su objetivo: un 3D **100% fiel a las 15 referencias** de `references/` (amigable, suave, buenas texturas,
  natural) para después hacer **muchas animaciones y renders "súper naturales, súper reales"** con efectos.
- Antes de gastar dinero del usuario o **subir sus imágenes a servicios de terceros**, pide permiso explícito.

## 2. Convenciones del repo (obligatorias)

- Rama de trabajo: **`claude/compassionate-cori-xn0xjj`**. Commit y push solo ahí (`git push -u origin claude/compassionate-cori-xn0xjj`). No abrir PR salvo que lo pida.
- Esa rama es la **rama de producción en Vercel**: cada push despliega https://morfi-pet.vercel.app
  (proyecto `morfi-pet`, equipo `mh-astral-systems`, rootDirectory `web`). No empujes un visor roto.
- Los mensajes de commit terminan con:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  ```
  (más la línea `Claude-Session:` de la sesión actual si el entorno la da). No pongas identificadores de modelo en nada que se suba al repo.
- Binarios (`*.blend`, `*.glb`, `*.mp4`) van por **Git LFS** (`.gitattributes`); tras clonar: `git lfs install && git lfs pull`.
  GitHub rechaza archivos > 100 MB aun con LFS en algunos planes: no subas los GLB crudos de la IA, solo los procesados.
- `work/` está en `.gitignore`: ahí van pruebas, renders intermedios y **los archivos crudos de la IA 3D** (ver §5).

## 3. Dónde quedó el pipeline procedural (rondas 1–11)

Todo el personaje se genera con scripts (Blender 4.5 headless + SDF/marching cubes), con cámaras
calibradas por referencia, poses por toma, "face cheat" para los perfiles, shader de visor capturado
de las fotos, esqueleto y 6 acciones (`Pose_Neutral`, `Pose_Hero`, `Idle`, `Walk`, `Run`, `Wave`) más
`Ref_<vista>`. Último commit de esa línea: `f19af19` (ronda 11).

Métricas finales r11 (render vs referencia): IoU de silueta frente 0.936, perfil izq. 0.929, espalda 0.944,
perfil der. 0.912, 3/4 frente 0.906, 3/4 espalda 0.895; piezas: sudadera 0.870, playera 0.938, lentes 0.747.
ΔE color en el visor 4.5–9.2.

Piezas reutilizables y buenas del pipeline actual (en `source/morfi_master.blend` y `exports/`):
- Objetos: `Body_Base`, `Head`, `Eye_R/L` + `Cornea_R/L` + `EyeHighlight_R/L` (ojos reales que miran y parpadean),
  `Brow_R/L`, `Tshirt`, `Tshirt_Collar`, `Tshirt_Logo`, `Hoodie`, `Hoodie_Hem`, `Hoodie_Cuff_R/L`, `Hoodie_Zipper`,
  `Hoodie_Drawstrings`, `Shoe_R/L`, `Glasses_Frame`, `Glasses_Lens_R/L`, `Pixel_01..03` (cubos), `Laptop`, `Laptop_Logo`.
- Esqueleto y acciones: `scripts/rig_model.py`, `scripts/morfi/rig.py`.
- Cámaras calibradas por referencia: `docs/camera_fit.json`, `docs/part_camera_fit.json`, poses `docs/pose_fit.json`,
  mirada `docs/gaze_fit.json`. Máscaras de las referencias: `references_masks/`.
- Medición contra referencias: `scripts/render_views.py`, `scripts/make_comparisons.py`, `scripts/eval_silhouettes.py`
  (IoU de silueta), `docs/metrics.json`.
- Visor web (`web/`, Three.js + TS + Vite): skinning por cuaterniones duales (`web/src/dqskin.ts`), shader de
  "look" capturado de las referencias (`web/src/look.ts`, `web/scripts/capture-look.mjs`, `scripts/build_look.py`),
  ojos que siguen a la cámara con tope de 28°, morphs por toma, SFX, panel con versión.
- Prueba de que la mano no choca con la cabeza en el saludo: `scripts/check_hand_head.py`.

## 4. Por qué cambiamos de enfoque

Después de la ronda 11 el usuario dijo: la **mano sigue chueca**, el **saludo se ve rarísimo**, cualquier
movimiento se ve anormal y el muñeco **todavía no se parece** a las referencias. Conclusión honesta: el
modelado por primitivas SDF + animación hecha a mano tiene un techo; puliendo se mejora pero difícilmente
llega a "natural".

Decisión: usar una **malla generada por una IA de imagen→3D** (la forma orgánica "esculpida") y aplicar
encima todo lo que sí funciona del pipeline (ojos reales, lentes, medición con cámaras calibradas, rig,
visor, renders).

- Se investigó Higgsfield (Tripo H3.1 multivista, Hunyuan3D v3, Meshy multi-imagen, auto-rig con biblioteca
  de 678 animaciones). **El usuario NO usó Higgsfield**: usó **otra IA de 3D**, pagó el plan y generó varios
  modelos que, según él, "quedaron perfecto".
- Defectos que el usuario ya vio en esa IA (primeras capturas): **ojos pintados** (no son esferas reales),
  la **cremallera salió repetida** (dos cierres), la sudadera y la forma general muy bien. Puede no traer color
  en algunas versiones.
- Los archivos pesan demasiado para mandarlos por el chat de la sesión en la nube; por eso se abre la sesión local.

## 5. Siguiente paso: recibir y procesar los modelos de la IA

1. **Recibir.** El usuario copia los archivos descargados (GLB/FBX/OBJ + texturas) a **`work/ia3d/`**
   (carpeta ignorada por git). Pregúntale qué herramienta fue (Meshy, Tripo, Hunyuan, Rodin…) y qué opciones
   eligió (con/sin textura, PBR, polycount, A-pose/T-pose, rig).
2. **Inspeccionar cada archivo** (Blender headless o `gltf-transform inspect`): polycount, número de objetos
   (¿todo fusionado?), texturas y resolución, escala/unidades, eje arriba, pose, si trae esqueleto.
   Haz una hoja de contacto (render frente/perfil/espalda/3/4 de cada modelo) y enséñasela al usuario.
3. **Elegir el mejor con números**, no a ojo: alinear al marco del proyecto (misma altura y origen que
   `Body_Base`/master), renderizar con las cámaras de `docs/camera_fit.json` y medir IoU de silueta contra
   `references_masks/` (adaptar `render_views.py` + `eval_silhouettes.py`/`make_comparisons.py`).
4. **Limpieza en Blender** (respetando lo que ya quedó bien de la IA):
   - Quitar los ojos pintados y poner los **ojos reales** del master (`Eye_*`, `Cornea_*`, `EyeHighlight_*`) con
     su mirada y parpadeo; repintar la zona en la textura.
   - **Cremallera**: dejar una sola (corregir textura y/o geometría; se puede reusar `Hoodie_Zipper`).
   - **Lentes**: si vienen fusionados a la cara, separarlos o sustituirlos por `Glasses_*` del master
     (montura, cristales y patillas gruesas como en r11).
   - Revisar cubos (`Pixel_*`), manos (pulgar + 3 dedos), logo M de la playera, tenis.
   - Si la textura trae luz/sombra horneada, des-iluminarla (o recapturar color con el método de `build_look.py`).
5. **Topología para animar**: remesh/retopo (quads, ~30–80k triángulos para web; master más denso),
   UVs limpias, rebake de color/normal desde la malla de la IA. Separar ropa del cuerpo si se puede
   (sudadera abierta, playera) para que deforme bien.
6. **Rig y animación natural**: transferir/ajustar el esqueleto existente a la malla nueva, pesos con
   transferencia + retoque (el visor ya usa cuaterniones duales). Para movimiento natural usar
   **captura de movimiento** (biblioteca de mocap; si implica subir el modelo a un servicio, pedir permiso)
   y ajustarla a las proporciones chibi: cabeza grande → revisar que la mano no atraviese la cabeza
   (`scripts/check_hand_head.py`), brazos cortos, sin estirar la sudadera.
7. **Exportar y visor**: GLB master + web (`scripts/export_assets.py`, `fix_glb_tangents.py`,
   `web/scripts/sync-assets.mjs`), recapturar el look del visor para los materiales nuevos, smoke test
   (`web/scripts/smoke-test.mjs`), subir `ROUND` en `web/src/main.ts` (está en 10, debería ir en 12) y push.
8. **Renders con efectos** (Cycles): vistas, hero, giro 360°, animaciones; comparar contra referencias.

Reporta al usuario en cada paso importante con imágenes (hoja de contacto, comparativas) antes de seguir.

## 5b. Hecho en la sesión local (15-oct-2026)

Detalle completo en `docs/ia3d.md`. En resumen:
- Los modelos son de **Meshy**. `MORFI ESQ.glb`, `MORFI ESQUELETO.glb`, `MORFI GBL 1.glb` y el OBJ son la
  **misma malla**. `SUDADERA.glb` es una sudadera suelta (no se usó). Copias en `work/ia3d/`.
- El rig de Meshy se descartó (pesos inservibles). Hay un rig nuevo con IK de piernas
  (`scripts/ia3d/build_rig.py`).
- Ojos y boca animables con calcomanías procedurales sobre la textura limpia, más cejas y cierre de boca
  con shape keys (`build_face.py`). Los controla el rig (`blink_L/R`, `gaze_x/y`, `squint`, `mouth_open`,
  `mouth_round`, `smile`, `brow_L/R`).
- 10 acciones en `scripts/ia3d/anim/` y materiales realistas más estudio (`build_look.py`, `studio.py`).
  El video de muestra sale de `render_showcase.py` + `encode_showcase.py`.
- **Reglas nuevas del usuario**:
  1. Todo se instala en **D:** (Blender 4.5.14 portátil en `D:\tools\blender-4.5`; usar `D:\tools\bl.sh`,
     que manda los temporales a `D:\tmp\morfi`).
  2. Los commits van **a su nombre, sin `Co-Authored-By` de Claude** (esto reemplaza lo dicho en §2).
  3. No se suben sus modelos ni imágenes sin preguntar.
- Pendiente: llevar la cara procedural al visor web (GLSL) y exportar el GLB nuevo.

## 6. Entorno local

Requisitos (ver README): Blender 4.5 LTS (con numpy/scipy/scikit-image/pillow en su Python), Python 3
(numpy, scipy, pillow, rembg), Node 22 + npm, ffmpeg, Git LFS. En Windows, los comandos del README son de
bash: usa Git Bash o WSL. Verifica qué hay instalado antes de empezar y dile al usuario qué falta.

`work/` no viaja con git (6 GB de intermedios). Lo que se necesita se regenera:
- `work/calib/points_*.npz`, `work/calib/skin.npz` → `scripts/dump_points.py`, `scripts/dump_skin.py`.
- `work/look/raw.json` → `web/scripts/capture-look.mjs`.

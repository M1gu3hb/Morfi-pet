# Morfi · validación

Este documento recoge **cómo se comprobó** el modelo y **qué diferencias quedan** respecto a las referencias. Todo se puede repetir con los comandos del README; los números de abajo salen de los archivos generados (`docs/metrics.json`, `docs/gltf-validation.json`, `docs/reimport_report.json`, `exports/export_report.json`).

## 1. Comparación visual con las referencias

Cada vista se renderiza como si fuera **la misma foto que la referencia**: la cámara de cada toma está calibrada contra su silueta (`camera_views`), el personaje tiene la pose de esa toma (`Ref_<vista>`, ajustada por contorno y por zonas de color), los ojos miran donde miran en la foto (`view_gaze`) y el set de luces gira con la cámara, como en las fotos de producto de referencia. Fondo `#FDFDF9`, piso con menos velo gris (junto a la figura 250–252; la foto 02: 246–250). En `renders/comparisons/` hay, por vista, una lámina con la referencia, el render y la superposición de siluetas (gris = coinciden, rojo = solo en la referencia, verde = solo en el 3D), y `before_after_*` con la referencia, la versión publicada anterior (ronda 9) y la actual; `ronda10_*` junta lo mismo para la axila, el cuello de la playera, la sudadera de frente, espalda y 3/4, las caras de los perfiles y la playera sola, y `ronda9_*` / `ronda8_*` lo de las rondas anteriores.

| Vista | Referencia | IoU silueta antes (ronda 9) | IoU silueta ahora (ronda 10) | ΔE mediana antes | ΔE mediana ahora | IoU por zonas de color |
|---|---|---|---|---|---|---|
| Frente | `02_Morfi_frente.png` | 0.945 | **0.944** | 10.7 | **10.8** | 0.691 |
| Perfil izquierdo | `03_Morfi_perfil_izquierdo.png` | 0.920 | **0.923** | 17.6 | **17.8** | 0.643 |
| Espalda | `04_Morfi_espalda.png` | 0.943 | **0.939** | 7.5 | **7.3** | 0.761 |
| Perfil derecho | `05_Morfi_perfil_derecho.png` | 0.908 | **0.907** | 12.0 | **11.9** | 0.650 |
| 3/4 frontal | `06_Morfi_tres_cuartos_frontal.png` | 0.909 | **0.912** | 12.0 | **11.8** | 0.671 |
| 3/4 posterior | `07_Morfi_tres_cuartos_posterior.png` | 0.897 | **0.892** | 7.7 | **7.9** | 0.700 |

Los cambios de la ronda 10 son casi todos interiores a la silueta (pliegue de la axila, escote redondo, bolsillos): el contorno y el color medio apenas se mueven (±0.005 de IoU, ±0.2 de ΔE). Lo que mejora se ve en las láminas `ronda10_*`, no en estos números. La sudadera se estrecha en el pecho y se abre al dobladillo, y por eso la espalda y la 3/4 posterior pierden unas milésimas de IoU.

**Shader del visor web.** El visor no usa Cycles: pinta cada material con el sombreado medido en las fotos (`art-direction.md` §12.6). Visto con la cámara y la pose de cada toma, el ΔE mediano contra la foto es (`npm run look-eval` + `scripts/eval_look.py`, `renders/comparisons/look_eval.png`):

| Vista | Visor "fiel a la foto" | Visor PBR | Cycles (tabla de arriba) |
|---|---|---|---|
| Frente | **8.2** | 15.1 | 10.8 |
| 3/4 frontal | **9.2** | 15.3 | 11.8 |
| Perfil izquierdo | **8.6** | 13.7 | 17.8 |
| Perfil derecho | **7.9** | 12.5 | 11.9 |
| Espalda | **5.5** | 8.8 | 7.3 |
| 3/4 posterior | **4.6** | 10.9 | 7.9 |

En la ronda 9 la IoU de los perfiles bajó (0.932 → 0.920 y 0.928 → 0.908) porque dos cosas se fijan a ojo para que se parezcan al dibujo, y el contorno no las premia: los cubos van de frente a la cámara y el brazo cercano cuelga junto al cuerpo (`art-direction.md` §11).

Láminas de piezas (cada pieza fotografiada con la cámara calibrada de su lámina; los cristales de los lentes cuentan como parte de la silueta):

| Pieza | Lámina | IoU silueta | ΔE mediana |
|---|---|---|---|
| Sudadera | `08_Morfi_sudadera.png` | 0.857 | 6.4 |
| Playera | `09_Morfi_playera.png` | 0.939 | 7.3 |
| Tenis | `10_Morfi_tenis.png` | 0.867 | 11.4 |
| Lentes | `11_Morfi_lentes.png` | 0.757 | 3.2 |
| Cubos | `12_Morfi_tres_cubos.png` | 0.923 | 12.7 |
| Laptop | `13_Morfi_laptop.png` | 0.937 | 24.7 |
| Cuerpo base | `14_Morfi_cuerpo_base.png` | 0.940 | 15.5 |

- **IoU de silueta**: intersección / unión entre el canal alfa del render y la silueta de la referencia segmentada con BiRefNet (`references_masks/`, `scripts/ref_masks.py`). La columna "antes" es la versión publicada anteriormente (ronda 9), medida igual.
- **ΔE**: diferencia de color CIELAB (1976) píxel a píxel dentro de la silueta común, a ¼ de resolución con un desenfoque leve. Es una medida exigente: un desplazamiento de pocos píxeles de un borde de alto contraste (montura, pupila, cremallera) cuenta como diferencia de color. Como referencia, ΔE ≈ 2 es apenas perceptible y la mediana de la ronda 2 estaba entre 11 y 17.
- **IoU por zonas de color**: media de la coincidencia de las zonas azul (piel), negra (sudadera, montura) y blanca/gris (playera, tenis, ojos) entre la referencia y el modelo posado (`docs/pose_fit.json`).

Además:

- `cmp_hero_master.png`: render hero con wordmark junto a la imagen maestra `00`.
- `cmp_part_*.png`: cada pieza junto a su lámina `08–14`, fotografiada con la cámara calibrada de esa lámina (`part_cameras`) y, para piezas sueltas, su colocación (tenis escalonados, cubos separados).
- `posefit_*`, `semfit_*`, `camfit_*`, `partfit_*`: diagnósticos de los ajustes (silueta, zonas de color, cámara y piezas).

Las técnicas usadas en cada ronda, con sus números, están en `art-direction.md` §7–§12.

## 2. Validación de los GLB (Khronos glTF-Validator)

`cd web && npm run validate` → `docs/gltf-validation.json`

| Archivo | Errores | Avisos | Triángulos | Materiales | Animaciones | Tamaño |
|---|---|---|---|---|---|---|
| `exports/morfi_master.glb` | 0 | 0 | 921 785 | 21 | 12 | 60 MB |
| `exports/morfi_web.glb` (con los morphs `Shot_<vista>`) | 0 | 0 | 215 837 | 21 | 12 | 14.5 MB |
| `parts/morfi_head.glb` | 0 | 0 | 218 592 | 5 | – | 16.6 MB |
| `parts/morfi_hoodie.glb` | 0 | 0 | 113 068 | 5 | – | 10.2 MB |
| `parts/morfi_shoes.glb` | 0 | 0 | 56 000 | 4 | – | 6.5 MB |
| `parts/morfi_body_base.glb` | 0 | 0 | 40 000 | 1 | – | 4.4 MB |
| `parts/morfi_tshirt.glb` (playera sola, con mangas y su escote) | 0 | 0 | 19 000 | 2 | – | 4.2 MB |
| `parts/morfi_pixels.glb` | 0 | 0 | 20 736 | 1 | – | 3.7 MB |
| `parts/morfi_glasses.glb` | 0 | 0 | 25 280 | 2 | – | 0.99 MB |
| `parts/morfi_laptop.glb` | 0 | 0 | 14 400 | 2 | – | 0.50 MB |

El visor publicado carga `web/public/models/morfi.glb`, la misma malla web con la geometría comprimida con meshopt (`gltf-transform meshopt`, 14.5 → 6.5 MB).

Extensiones usadas: `KHR_materials_clearcoat`, `KHR_materials_emissive_strength`, `KHR_materials_ior`, `KHR_materials_sheen`, `KHR_materials_specular`, `KHR_materials_transmission`. Todas las mallas llevan UV, normales y tangentes válidas (se reparan tangentes nulas tras la exportación con `scripts/fix_glb_tangents.py`); las mallas con piel son nodos raíz, como recomienda la especificación.

## 3. Reimportación

`scripts/validate_assets.py` abre cada GLB en una escena **vacía** de Blender (sin el `.blend` original), comprueba geometría, texturas, esqueleto y acciones y hace un render (`renders/comparisons/reimport_*.png`):

| | web | master |
|---|---|---|
| Mallas | 29 | 29 |
| Esqueletos | 1 | 1 |
| Texturas faltantes | 0 | 0 |
| Acciones | Idle, Pose_Hero, Pose_Neutral, Run, Walk, Wave + Ref_front, Ref_profile_left, Ref_back, Ref_profile_right, Ref_three_quarter_front, Ref_three_quarter_back | ídem |
| Caja (m) | x ±0.373, y −0.278…0.319, z −0.007…1.143 | ídem |

Las acciones `Ref_<vista>` son las poses por toma (una pose estática por referencia); el visor no las muestra en el desplegable de animaciones, sino al pulsar el botón de cada vista.

La altura sin cubos es 1.0 (convención del proyecto) y 1.143 con los cubos.

## 4. Visor web

Publicado en **https://morfi-pet.vercel.app** (Vercel, proyecto `morfi-pet`, carpeta `web/`; cada push a la rama lo vuelve a desplegar y el panel muestra la ronda y el commit).

`cd web && npm run build && npm run test:e2e` abre el visor en Chromium headless (SwiftShader, sin GPU) con el GLB real y recorre:
- las vistas, con la cámara y la pose calibradas de cada referencia, y la espalda con y sin "Luz sigue a la cámara";
- la pose hero, la animación de caminar y el preset cuerpo base;
- los modos gris y alambre, y el fondo oscuro;
- el shader PBR y el "fiel a la foto";
- los cuatro modos de comparación con la foto (superponer, cortina, diferencia, lado a lado), en el perfil, que usa el morph de la toma;
- la música, un toque sobre Morfi y la captura PNG;
- una ventana de móvil (390×844).

La prueba falla ante cualquier error de consola. Resultado: **SMOKE TEST PASSED** — 215 839 triángulos · 36 mallas · 21 materiales · 12 animaciones. Capturas en `renders/viewer/`.

Errores reales encontrados en esta ronda al medir el visor contra las fotos:
- **Ojos blancos en la 3/4.** La córnea con transmisión del glTF se dibujaba en el navegador como vidrio esmerilado: desenfocaba el iris y, en ángulos rasantes, mostraba el fondo blanco. Córneas y lentes se dibujan ahora como capas transparentes casi invisibles.
- **Reflejos de colores en el blanco del ojo.** La primera captura del sombreado del ojo daba un MatCap manchado. El ojo conserva solo la parte suave y en gris.
- **Perfiles sin cara.** En el visor faltaba la trampa de cámara de los perfiles, que solo existía en el render de Blender. Ahora va en el GLB como morph por toma.

## 5. Animaciones y giro 360°

- `renders/animations/animaciones_preview_workbench.png`: fotogramas de Idle, Caminar, Correr y Saludar (sombreado rápido de Workbench, sin texturas ni cristales) para revisar la deformación.
- Al revisarlas se detectó que el dobladillo de la sudadera se despegaba al saludar y correr (recibía influencia de los huesos del brazo porque las manos cuelgan a su altura). Se corrigió en `rig.compute_weights`: los brazos solo influyen fuera de la columna del cuerpo o por encima del codo.
- También se detectó que girar los huesos de los ojos hacia la cámara se perdía al renderizar (la acción activa vuelve a aplicar sus claves) y la córnea quedaba desalineada en 3/4; ahora se giran los objetos del ojo respecto a su hueso.
- `renders/morfi_turntable.mp4`: giro completo de 6 s (144 fotogramas, 24 fps, 600×720, Cycles) con los ojos siguiendo al espectador mientras la cara es visible; las luces giran con la cámara, como en las referencias.

## 6. Invariantes del encargo

| Invariante | Estado |
|---|---|
| 3 cubos en la cabeza (grande izq., mediano arriba der., pequeño abajo der.) | ✔ objetos `Pixel_01..03` |
| 2 cuadrados azules en la laptop | ✔ |
| Zona facial celeste (no máscara blanca) | ✔ albedo `#89BAF9` (calibrado contra las referencias) horneado en el atlas |
| Ojos: pupila negra con un brillo blanco nítido | ✔ pupila `#000000`, brillo `EyeHighlight_L/R` |
| Lentes cuadrados redondeados | ✔ |
| Sudadera abierta, M solo en la playera gris | ✔ |
| Textura suave y fina | ✔ laberinto fino + terciopelo, sin alterar la silueta |
| Manos con pulgar + 3 dedos | ✔ |
| Ropa separada, con grosor y holgura reales | ✔ cada prenda es un objeto propio y se puede ocultar |

## 7. Diferencias pendientes (honestas)

Las 15 imágenes de referencia son renders de IA generados por separado. Analizándolas solo entre sí (ronda 9), en casi todo coinciden: las espaldas y los frentes espejados calzan, las cabezas de las 3/4 caben en el casco visual de las demás, y manos y pies tienen el mismo tamaño. Las diferencias reales son pocas y puntuales:

- En los perfiles 03 y 05 la cara está dibujada girada hacia la cámara sobre una cabeza de perfil puro.
- En esos mismos perfiles los cubos están dibujados de frente a la cámara: 05 espejado no coincide con 03, mientras que 02 y 04 espejado sí coinciden.
- Pose, encuadre y luz cambian de una toma a otra.

Las dos primeras se reproducen con trampas de cámara por toma (`art-direction.md` §11). Las demás se resuelven dando a cada toma su cámara, su pose, su mirada y su luz (§1). Lo que queda, y por qué:

1. **Cara en los perfiles (03 y 05).** Resuelta con la trampa de cámara de la ronda 9: la cara se desliza 26° (03) y 20° (05) hacia la cámara sobre la cabeza, sin cambiar el contorno, y el lente mide ancho/alto 0.48 y 0.39 como en las referencias. Quedan tres diferencias:
   - El lente salía un 10 % más alto que en esas dos fotos (en el frente mide lo mismo que en 02: es una diferencia entre las propias referencias). Desde la ronda 10 los lentes de los perfiles se escalan ×0.91 en altura (`face_cheat.glasses_z`).
   - La mejilla celeste de 03/05 llega un poco más atrás del lente que en el modelo, que la toma sobre todo de la lámina 14.
   - En 03 la boca asoma algo más.
2. **Brazos en perfil.** El brazo cercano ya no apunta a la cámara: se acerca 28° al cuerpo, se adelanta y dobla el codo, y la manga se ve de lado con la mano bajo el puño. En 03/05, sin embargo, la mano queda a la altura del dobladillo. El brazo del modelo, colgando, llega más abajo: el brazo dibujado en esos perfiles es más corto.
3. **Cubos en perfil.** El grupo se gira de frente a la cámara en 03/05 (trampa de cámara en `Ref_<vista>`), como están dibujados. La separación entre cubos es algo distinta.
4. **Sudadera.** La caída ya es en triángulo (ronda 9): mangas raglán desde el cuello, cuerpo más angosto, borde de capucha ceñido al cuello, puños anchos y rib alto. Lo que sigue distinto:
   - En 02 las mangas se separan del cuerpo desde la axila. Desde la ronda 10 la manga solo se funde con el cuerpo por encima de la axila: debajo queda un pliegue y la manga se lee como pieza aparte. Pero en 02 el brazo además se abre un poco y deja un hueco blanco entre manga y costado, y en el modelo, con el brazo colgando más pegado, ese hueco no aparece. Abrir el brazo en la pose ponía la manga horizontal (probado, IoU de la sudadera 0.77).
   - No hay simulación de tela: los pliegues son procedurales.
   - En la lámina 08 la capucha levantada es más alta que en la foto.
   - Los bolsillos ya son más grandes y altos, con la boca curva y un labio (ronda 10), pero siguen siendo un relieve sobre la tela, sin la bolsa abierta de 02.

5. **Tenis.** Tienen las piezas de la lámina 10, pero la puntera es más cuadrada y las correas más planas.
6. **Toma hero.** La cabeza ya está calzada con la imagen maestra (lentes a < 9 px, contorno a < 7 px, misma inclinación) y la mirada ajustada; en la maestra los lentes están un 6 % más separados de lo que da el modelo, y la laptop y la mano derecha no son un calco.
7. **Cuerpo base (lámina 14).** Cara calcada y mirada de la lámina; brazos más gruesos y pies más grandes que antes, pero el torso de la lámina es más ancho de cadera y el cuello no se ve (en el modelo asoma un poco), y los brazos siguen algo más delgados porque deben caber en las mangas.
8. **Color residual (ΔE 7–19).** Las zonas planas (piel, sudadera, blancos) quedan a pocos ΔE; lo que pesa en la mediana son bordes de alto contraste desplazados unos píxeles (montura, pupilas, cremallera, cubos), la cara de los perfiles y diferencias de luz propias de cada referencia.
9. **Suelo.** Las referencias tienen fondo blanco uniforme (253–254). Desde la ronda 10 el compositor quita parte del velo gris del suelo de los renders (`studio.floor_veil`). Medido en el frente, junto a la figura el suelo pasa de 244–246 a 250–252 (la foto 02: 246–250); las esquinas quedan en 253, como en la foto. Se conserva la sombra de contacto bajo los pies.
10. **Playera suelta (lámina 09).** Es un segundo estado de la prenda (`Tshirt_Product`, con mangas, y `Tshirt_Product_Collar`). Puesta bajo la sudadera la playera va sin mangas, porque nunca se ven. Desde la ronda 10 el escote es redondo con su rib, y la parte de atrás baja hasta justo encima de los hombros, como en 09. El escote de adelante baja algo más que en la foto.
11. **Visor web vs. Cycles.** Con el shader "fiel a la foto" el visor queda más cerca de las fotos que los renders de Cycles (ΔE 4.6–9.2 frente a 7.3–17.8, §1). Pero es un sombreado medido para las 6 cámaras de las referencias: desde ángulos muy distintos es una extrapolación suave, y el relieve fino (fieltro, pliegues) depende de la resolución de las texturas web (2K). Los renders finales de alta calidad siguen siendo los de `renders/`.

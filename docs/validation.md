# Morfi · validación

Este documento recoge **cómo se comprobó** el modelo y **qué diferencias quedan** respecto a las referencias. Todo se puede repetir con los comandos del README; los números de abajo salen de los archivos generados (`docs/metrics.json`, `docs/gltf-validation.json`, `docs/reimport_report.json`, `exports/export_report.json`).

## 1. Comparación visual con las referencias

Cada vista se renderiza con la **misma cámara estimada** de las referencias (lente 65.2 mm, distancia 2.5, altura 0.756; ver `art-direction.md` §2) y el mismo fondo `#FDFDF9`. En `renders/comparisons/` hay, por vista, una lámina con la referencia, el render y la superposición de siluetas (gris = coinciden, rojo = solo en la referencia, verde = solo en el 3D).

| Vista | Referencia | IoU de silueta |
|---|---|---|
| Frente | `02_Morfi_frente.png` | 0.848 |
| Perfil izquierdo | `03_Morfi_perfil_izquierdo.png` | 0.850 |
| Espalda | `04_Morfi_espalda.png` | 0.885 |
| Perfil derecho | `05_Morfi_perfil_derecho.png` | 0.821 |
| 3/4 frontal | `06_Morfi_tres_cuartos_frontal.png` | 0.786 |
| 3/4 posterior | `07_Morfi_tres_cuartos_posterior.png` | 0.796 |

El IoU (intersección / unión de las siluetas) se calcula con la silueta exacta del render (canal alfa) contra una segmentación automática de la referencia; la sombra del piso y los tenis blancos sobre fondo blanco añaden algo de error a la medida, así que es un indicador de proporciones, no una nota de parecido. En las vistas 3/4 la referencia está encuadrada algo más a la izquierda y un poco más grande que con la cámara común (la superposición muestra la franja roja a un lado y la verde al otro), lo que baja su IoU aunque las formas coincidan. La segunda ronda cambió sobre todo formas *dentro* de la silueta (piernas separadas, manos, tenis, cuello, ojos, colores), por eso el IoU apenas varía respecto a la primera versión y las láminas `before_after_*` muestran mejor el avance.

Además:

- `cmp_hero_master.png`: render hero con wordmark junto a la imagen maestra `00`.
- `cmp_part_*.png`: cada pieza (sudadera, playera, tenis, lentes, cubos, laptop, cuerpo base) junto a su lámina `08–14`.
- `before_after_*.png`: primera versión completa (izquierda) frente a la final (derecha), para ver el efecto de la segunda ronda de ajustes.

### Qué se midió y corrigió en la segunda ronda

| Medida (vista frontal, filas de la imagen proyectadas al plano del cuerpo) | Antes | Después | Referencia |
|---|---|---|---|
| Ancho de hombros a z≈0.44 | ±0.28 | ±0.265 | ±0.25 |
| Ancho del dobladillo | ±0.19 | ±0.22 | ±0.22 |
| Piernas: separación interior / ancho | unidas hasta z≈0.15 / 0.12 | separadas desde el dobladillo / 0.13 | separadas desde el dobladillo / 0.137 |
| Color medio playera (sRGB, 0–255) | 182–192 | 223–228 | 211–226 |
| Color medio sudadera, panel en sombra | 44–49 | 40–45 | 29–43 |
| Azul de la pierna iluminada (canal G/B) | 75 / 226 | 78 / 230 | 115 / 252 |

Las dos últimas filas muestran diferencias que siguen abiertas: la sudadera de la referencia tiene sombras algo más profundas y las piernas están más iluminadas (luz de estudio distinta, no un color distinto del material).

## 2. Validación de los GLB (Khronos glTF-Validator)

`cd web && npm run validate` → `docs/gltf-validation.json`

| Archivo | Errores | Avisos | Triángulos | Materiales | Animaciones | Tamaño |
|---|---|---|---|---|---|---|
| `exports/morfi_master.glb` | 0 | 0 | 924 816 | 20 | 6 | 57 MB |
| `exports/morfi_web.glb` | 0 | 0 | 215 796 | 20 | 6 | 11 MB |
| `parts/morfi_head.glb` | 0 | 0 | 218 544 | 4 | – | 17 MB |
| `parts/morfi_hoodie.glb` | 0 | 0 | 113 496 | 5 | – | 9.3 MB |
| `parts/morfi_shoes.glb` | 0 | 0 | 56 000 | 4 | – | 6.2 MB |
| `parts/morfi_body_base.glb` | 0 | 0 | 40 000 | 1 | – | 4.4 MB |
| `parts/morfi_tshirt.glb` | 0 | 0 | 19 000 | 2 | – | 4.0 MB |
| `parts/morfi_pixels.glb` | 0 | 0 | 20 736 | 1 | – | 3.7 MB |
| `parts/morfi_glasses.glb` | 0 | 0 | 25 280 | 2 | – | 0.97 MB |
| `parts/morfi_laptop.glb` | 0 | 0 | 14 400 | 2 | – | 0.48 MB |

Extensiones usadas: `KHR_materials_sheen`, `KHR_materials_transmission`, `KHR_materials_clearcoat`, `KHR_materials_specular`, `KHR_materials_ior`. Todas las mallas llevan UV, normales y tangentes válidas (se reparan tangentes nulas tras la exportación con `scripts/fix_glb_tangents.py`); las mallas con piel son nodos raíz, como recomienda la especificación.

## 3. Reimportación

`scripts/validate_assets.py` abre cada GLB en una escena **vacía** de Blender (sin el `.blend` original), comprueba geometría, texturas, esqueleto y acciones y hace un render (`renders/comparisons/reimport_*.png`):

| | web | master |
|---|---|---|
| Mallas | 27 | 27 |
| Esqueletos | 1 | 1 |
| Texturas faltantes | 0 | 0 |
| Acciones | Idle, Pose_Hero, Pose_Neutral, Run, Walk, Wave | ídem |
| Caja (m) | x ±0.408, y −0.277…0.319, z −0.003…1.143 | ídem |

La altura sin cubos es 1.0 (convención del proyecto) y 1.143 con los cubos.

## 4. Visor web

`cd web && npm run build && npm run test:e2e`: Chromium headless (SwiftShader, sin GPU) carga el GLB real, recorre las vistas, la pose hero, la animación de caminar, el preset cuerpo base, los modos gris/alambre, el fondo oscuro, la captura PNG y una ventana de móvil (390×844). Falla ante cualquier error de consola. Resultado: **SMOKE TEST PASSED** — 215 796 triángulos · 34 mallas · 20 materiales · 6 animaciones. Capturas en `renders/viewer/`.

## 5. Animaciones y giro 360°

- `renders/animations/animaciones_preview_workbench.png`: fotogramas de Idle, Caminar, Correr y Saludar (sombreado rápido de Workbench, sin texturas ni cristales) para revisar la deformación.
- Al revisarlas se detectó que el dobladillo de la sudadera se despegaba al saludar y correr (recibía influencia de los huesos del brazo porque las manos cuelgan a su altura). Se corrigió en `rig.compute_weights`: los brazos solo influyen fuera de la columna del cuerpo o por encima del codo.
- También se detectó que girar los huesos de los ojos hacia la cámara se perdía al renderizar (la acción activa vuelve a aplicar sus claves) y la córnea quedaba desalineada en 3/4; ahora se giran los objetos del ojo respecto a su hueso.
- `renders/morfi_turntable.mp4`: giro completo de 6 s (144 fotogramas, 24 fps, 600×720, Cycles) con los ojos siguiendo al espectador mientras la cara es visible.

## 6. Invariantes del encargo

| Invariante | Estado |
|---|---|
| 3 cubos en la cabeza (grande izq., mediano arriba der., pequeño abajo der.) | ✔ objetos `Pixel_01..03` |
| 2 cuadrados azules en la laptop | ✔ |
| Zona facial celeste (no máscara blanca) | ✔ `#8EC4FB` horneado en el atlas |
| Lentes cuadrados redondeados | ✔ |
| Sudadera abierta, M solo en la playera gris | ✔ |
| Textura suave y fina | ✔ laberinto fino + terciopelo, sin alterar la silueta |
| Manos con pulgar + 3 dedos | ✔ |
| Ropa separada, con grosor y holgura reales | ✔ cada prenda es un objeto propio y se puede ocultar |

## 7. Diferencias pendientes (honestas)

Las 15 imágenes de referencia son renders de IA generados por separado; **no son vistas de un mismo objeto 3D** y se contradicen entre sí. Un modelo físico único no puede reproducirlas todas píxel a píxel. Las diferencias que quedan, y por qué:

1. **Perfil (03 y 05).** En los perfiles de referencia la cara, el ojo y el aro de los lentes se ven casi de frente, como si la cara "envolviera" el costado de la cabeza; en el frente (02) los mismos lentes son planos y frontales. El modelo sigue el frente y la imagen maestra: en perfil el ojo queda casi oculto tras la montura (los ojos giran 35 % hacia la cámara para acercarse).
2. **Cubos en perfil.** Los perfiles de referencia muestran los tres cubos "de frente"; con la disposición del frente y la espalda (que coinciden entre sí) en perfil se ven superpuestos. Se respetó el orden del encargo.
3. **Perspectiva de manos y pies en perfil.** En los perfiles de referencia la mano cercana aparece más alta y el pie lejano no asoma; eso implica una cámara distinta a la de las vistas frontal y trasera. Se usa una sola cámara para todas las vistas (la que ajusta la cabeza con error medio ≈3 px), así que en perfil la mano cercana se ve algo más baja y grande.
4. **Pose hero.** Reproduce la composición del master (cabeza hacia cámara e inclinada, laptop bajo el brazo derecho, puño izquierdo al frente, wordmark), pero no es un calco: la mano derecha queda detrás de la laptop y los pies se apoyan de forma ligeramente distinta.
5. **Detalle fino de tela.** Arrugas y pliegues están modelados de forma procedural (pliegues de manga, fruncido sobre el dobladillo, acanalados); no hay simulación de tela, por lo que la caída es más limpia que en las referencias.
6. **Tenis.** Tienen las piezas de la lámina 10 (suela con muescas, puntera, lengüeta, cuello acolchado, dos correas con ojales, talón azul), pero la puntera es algo más ancha y redonda y las correas más bajas que en la lámina; en primer plano (`cmp_part_tenis.png`) se nota más que en las vistas completas.
7. **Textura laberinto en primer plano.** Su escala está ajustada a las vistas completas; en los renders de piezas cercanos (cubos, playera) se ve más marcada que en las láminas de producto, que muestran un tejido más liso.
8. **Visor web vs. Cycles.** El visor usa iluminación en tiempo real (Three.js); los colores y sombras son cercanos pero no idénticos a los renders de Cycles (por ejemplo, el iris se ve más oscuro). Los renders finales son los de `renders/`.

# Morfi · validación

Este documento recoge **cómo se comprobó** el modelo y **qué diferencias quedan** respecto a las referencias. Todo se puede repetir con los comandos del README; los números de abajo salen de los archivos generados (`docs/metrics.json`, `docs/gltf-validation.json`, `docs/reimport_report.json`, `exports/export_report.json`).

## 1. Comparación visual con las referencias

Cada vista se renderiza como si fuera **la misma foto que la referencia**: la cámara de cada toma está calibrada contra su silueta (`camera_views`), el personaje tiene la pose de esa toma (`Ref_<vista>`, ajustada por contorno y por zonas de color), los ojos miran donde miran en la foto (`view_gaze`) y el set de luces gira con la cámara, como en las fotos de producto de referencia. Fondo `#FDFDF9`. En `renders/comparisons/` hay, por vista, una lámina con la referencia, el render y la superposición de siluetas (gris = coinciden, rojo = solo en la referencia, verde = solo en el 3D), y `before_after_*` con la referencia, la versión publicada anterior (ronda 6) y la actual; `ronda8_*` junta lo mismo para la cara, la sudadera, la espalda, el perfil y la toma hero.

| Vista | Referencia | IoU silueta antes (ronda 6) | IoU silueta ahora (ronda 8) | ΔE mediana antes | ΔE mediana ahora | IoU por zonas de color |
|---|---|---|---|---|---|---|
| Frente | `02_Morfi_frente.png` | 0.944 | **0.943** | 11.4 | **11.1** | 0.663 |
| Perfil izquierdo | `03_Morfi_perfil_izquierdo.png` | 0.942 | **0.932** | 15.2 | **18.6** | 0.670 |
| Espalda | `04_Morfi_espalda.png` | 0.946 | **0.944** | 7.7 | **7.6** | 0.754 |
| Perfil derecho | `05_Morfi_perfil_derecho.png` | 0.915 | **0.928** | 13.1 | **12.1** | 0.680 |
| 3/4 frontal | `06_Morfi_tres_cuartos_frontal.png` | 0.903 | **0.902** | 12.1 | **11.6** | 0.642 |
| 3/4 posterior | `07_Morfi_tres_cuartos_posterior.png` | 0.903 | **0.902** | 8.3 | **7.4** | 0.726 |

Láminas de piezas (cada pieza fotografiada con la cámara calibrada de su lámina; los cristales de los lentes cuentan como parte de la silueta):

| Pieza | Lámina | IoU silueta | ΔE mediana |
|---|---|---|---|
| Sudadera | `08_Morfi_sudadera.png` | 0.859 | 6.1 |
| Playera | `09_Morfi_playera.png` | 0.881 | 8.3 |
| Tenis | `10_Morfi_tenis.png` | 0.867 | 11.4 |
| Lentes | `11_Morfi_lentes.png` | 0.757 | 3.2 |
| Cubos | `12_Morfi_tres_cubos.png` | 0.923 | 12.7 |
| Laptop | `13_Morfi_laptop.png` | 0.937 | 24.7 |
| Cuerpo base | `14_Morfi_cuerpo_base.png` | 0.932 | 15.7 |

- **IoU de silueta**: intersección / unión entre el canal alfa del render y la silueta de la referencia segmentada con BiRefNet (`references_masks/`, `scripts/ref_masks.py`). La columna "antes" es la versión publicada anteriormente (ronda 6), medida igual.
- **ΔE**: diferencia de color CIELAB (1976) píxel a píxel dentro de la silueta común, a ¼ de resolución con un desenfoque leve. Es una medida exigente: un desplazamiento de pocos píxeles de un borde de alto contraste (montura, pupila, cremallera) cuenta como diferencia de color. Como referencia, ΔE ≈ 2 es apenas perceptible y la mediana de la ronda 2 estaba entre 11 y 17.
- **IoU por zonas de color**: media de la coincidencia de las zonas azul (piel), negra (sudadera, montura) y blanca/gris (playera, tenis, ojos) entre la referencia y el modelo posado (`docs/pose_fit.json`).

Además:

- `cmp_hero_master.png`: render hero con wordmark junto a la imagen maestra `00`.
- `cmp_part_*.png`: cada pieza junto a su lámina `08–14`, fotografiada con la cámara calibrada de esa lámina (`part_cameras`) y, para piezas sueltas, su colocación (tenis escalonados, cubos separados).
- `posefit_*`, `semfit_*`, `camfit_*`, `partfit_*`: diagnósticos de los ajustes (silueta, zonas de color, cámara y piezas).

Las técnicas usadas en cada ronda, con sus números, están en `art-direction.md` §7–§10.

## 2. Validación de los GLB (Khronos glTF-Validator)

`cd web && npm run validate` → `docs/gltf-validation.json`

| Archivo | Errores | Avisos | Triángulos | Materiales | Animaciones | Tamaño |
|---|---|---|---|---|---|---|
| `exports/morfi_master.glb` | 0 | 0 | 924 858 | 21 | 12 | 60 MB |
| `exports/morfi_web.glb` | 0 | 0 | 215 842 | 21 | 12 | 11.8 MB |
| `parts/morfi_head.glb` | 0 | 0 | 218 592 | 5 | – | 16.6 MB |
| `parts/morfi_hoodie.glb` | 0 | 0 | 113 494 | 5 | – | 10.0 MB |
| `parts/morfi_shoes.glb` | 0 | 0 | 56 000 | 4 | – | 6.5 MB |
| `parts/morfi_body_base.glb` | 0 | 0 | 40 000 | 1 | – | 4.4 MB |
| `parts/morfi_tshirt.glb` | 0 | 0 | 19 000 | 2 | – | 4.2 MB |
| `parts/morfi_pixels.glb` | 0 | 0 | 20 736 | 1 | – | 3.7 MB |
| `parts/morfi_glasses.glb` | 0 | 0 | 25 280 | 2 | – | 0.99 MB |
| `parts/morfi_laptop.glb` | 0 | 0 | 14 400 | 2 | – | 0.50 MB |

Extensiones usadas: `KHR_materials_clearcoat`, `KHR_materials_emissive_strength`, `KHR_materials_ior`, `KHR_materials_sheen`, `KHR_materials_specular`, `KHR_materials_transmission`. Todas las mallas llevan UV, normales y tangentes válidas (se reparan tangentes nulas tras la exportación con `scripts/fix_glb_tangents.py`); las mallas con piel son nodos raíz, como recomienda la especificación.

## 3. Reimportación

`scripts/validate_assets.py` abre cada GLB en una escena **vacía** de Blender (sin el `.blend` original), comprueba geometría, texturas, esqueleto y acciones y hace un render (`renders/comparisons/reimport_*.png`):

| | web | master |
|---|---|---|
| Mallas | 29 | 29 |
| Esqueletos | 1 | 1 |
| Texturas faltantes | 0 | 0 |
| Acciones | Idle, Pose_Hero, Pose_Neutral, Run, Walk, Wave + Ref_front, Ref_profile_left, Ref_back, Ref_profile_right, Ref_three_quarter_front, Ref_three_quarter_back | ídem |
| Caja (m) | x ±0.386, y −0.278…0.319, z −0.007…1.143 | ídem |

Las acciones `Ref_<vista>` son las poses por toma (una pose estática por referencia); el visor no las muestra en el desplegable de animaciones, sino al pulsar el botón de cada vista.

La altura sin cubos es 1.0 (convención del proyecto) y 1.143 con los cubos.

## 4. Visor web

`cd web && npm run build && npm run test:e2e`: Chromium headless (SwiftShader, sin GPU) carga el GLB real, recorre las vistas (cámara y pose calibradas de cada referencia), la espalda con y sin "Luz sigue a la cámara", la pose hero, la animación de caminar, el preset cuerpo base, los modos gris/alambre, el fondo oscuro, la captura PNG y una ventana de móvil (390×844). Falla ante cualquier error de consola. Resultado: **SMOKE TEST PASSED** — 215 842 triángulos · 36 mallas · 21 materiales · 12 animaciones. Capturas en `renders/viewer/`.

Al repetirlo en esta ronda apareció un error real que las comprobaciones anteriores no habían cubierto: el visor llamaba a `invalidate()` (desde la vista inicial) antes de declarar su contador de fotogramas, y la página no terminaba de cargar. Se corrigió declarando el contador al principio.

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

Las 15 imágenes de referencia son renders de IA generados por separado; **no son vistas de un mismo objeto 3D** y se contradicen entre sí (encuadre, pose, altura del piso, tamaño de manos y pies, disposición de los cubos). Por eso cada toma tiene su cámara, su pose, su mirada y su luz (§1), y aun así un único modelo físico no puede coincidir píxel a píxel con todas. Lo que queda, y por qué:

1. **Cara en los perfiles (03 y 05).** En los perfiles de referencia el ojo, el aro del lente y la boca se ven casi de frente, como si la cara "envolviera" el costado de la cabeza; en el frente (02), en la 3/4 (06) y en la lámina 14 los mismos lentes son planos y frontales. El modelo sigue el frente, la 3/4 y la imagen maestra, así que en perfil el ojo queda casi oculto tras la montura. Además, en la ronda 8 la mejilla celeste que en 03 envuelve la esquina inferior de la cara quedó azul en el costado (el calcado de la lámina 14 se corta en el borde de su silueta): por eso el perfil izquierdo subió de ΔE 15.2 a 18.6. Es lo primero que queda por corregir.
2. **Brazos en perfil.** El brazo cercano ya no apunta a la cámara (se acerca 18° al cuerpo), pero en 03/05 la manga se ve de costado con la mano justo bajo el puño, a la altura del dobladillo; en el modelo la mano cuelga más abajo. Doblar el codo para subirla empeoraba la silueta medida y se descartó.
3. **Cubos en perfil.** Se resuelven con un giro del grupo por toma (trampa de cámara en `Ref_<vista>`); la disposición de 03 no es exactamente la del modelo.
4. **Sudadera.** Capucha con volumen en la espalda (ronda 8) y capucha levantada para la lámina 08 (IoU de la lámina 0.83 → 0.86). Sigue sin simulación de tela: los pliegues son procedurales y la caída es más limpia que en las referencias; en la lámina 08 la capucha levantada es más alta y el arco de la abertura más estrecho que en la foto, y los bolsillos son parches rectos en vez de bolsas curvas.
5. **Tenis.** Tienen las piezas de la lámina 10, pero la puntera es más cuadrada y las correas más planas.
6. **Toma hero.** La cabeza ya está calzada con la imagen maestra (lentes a < 9 px, contorno a < 7 px, misma inclinación) y la mirada ajustada; en la maestra los lentes están un 6 % más separados de lo que da el modelo, y la laptop y la mano derecha no son un calco.
7. **Cuerpo base (lámina 14).** Cara calcada y mirada de la lámina; brazos más gruesos y pies más grandes que antes, pero el torso de la lámina es más ancho de cadera y el cuello no se ve (en el modelo asoma un poco), y los brazos siguen algo más delgados porque deben caber en las mangas.
8. **Color residual (ΔE 7–19).** Las zonas planas (piel, sudadera, blancos) quedan a pocos ΔE; lo que pesa en la mediana son bordes de alto contraste desplazados unos píxeles (montura, pupilas, cremallera, cubos), la cara de los perfiles y diferencias de luz propias de cada referencia.
9. **Suelo.** Las referencias tienen fondo blanco uniforme (254); el suelo del render queda en 246–248, con la sombra de contacto bajo los pies.
10. **Playera suelta (lámina 09).** Está modelada para ir puesta: sola muestra las mangas cortas casi fundidas con el cuerpo y el cuello abierto por dentro.
11. **Visor web vs. Cycles.** El visor usa iluminación en tiempo real (Three.js, con la misma idea de luz que sigue a la cámara); colores y sombras son cercanos pero no idénticos a los renders de Cycles. Los renders finales son los de `renders/`.

# Morfi · validación

Este documento recoge **cómo se comprobó** el modelo y **qué diferencias quedan** respecto a las referencias. Todo se puede repetir con los comandos del README; los números de abajo salen de los archivos generados (`docs/metrics.json`, `docs/gltf-validation.json`, `docs/reimport_report.json`, `exports/export_report.json`).

## 1. Comparación visual con las referencias

Cada vista se renderiza como si fuera **la misma foto que la referencia**: la cámara de cada toma está calibrada contra su silueta (`camera_views`), el personaje tiene la pose de esa toma (`Ref_<vista>`, ajustada por contorno y por zonas de color), los ojos miran donde miran en la foto (`view_gaze`) y el set de luces gira con la cámara, como en las fotos de producto de referencia. Fondo `#FDFDF9`. En `renders/comparisons/` hay, por vista, una lámina con la referencia, el render y la superposición de siluetas (gris = coinciden, rojo = solo en la referencia, verde = solo en el 3D), y `before_after_*` con la referencia, la versión anterior (ronda 2) y la actual.

| Vista | Referencia | IoU silueta ronda 2 | IoU silueta ahora | ΔE mediana ronda 2 | ΔE mediana ahora | IoU por zonas de color |
|---|---|---|---|---|---|---|
| Frente | `02_Morfi_frente.png` | 0.914 | **0.944** | 11.8 | **11.4** | 0.676 |
| Perfil izquierdo | `03_Morfi_perfil_izquierdo.png` | 0.910 | **0.942** | 16.2 | **15.2** | 0.670 |
| Espalda | `04_Morfi_espalda.png` | 0.925 | **0.946** | 10.9 | **7.7** | 0.755 |
| Perfil derecho | `05_Morfi_perfil_derecho.png` | 0.879 | **0.915** | 17.3 | **13.1** | 0.632 |
| 3/4 frontal | `06_Morfi_tres_cuartos_frontal.png` | 0.835 | **0.903** | 18.4 | **12.1** | 0.631 |
| 3/4 posterior | `07_Morfi_tres_cuartos_posterior.png` | 0.840 | **0.903** | 13.9 | **8.3** | 0.727 |

- **IoU de silueta**: intersección / unión entre el canal alfa del render y la silueta de la referencia segmentada con BiRefNet (`references_masks/`, `scripts/ref_masks.py`). La segmentación por umbral de color que se usaba antes no veía los tenis blancos y sí las sombras del piso, y subestimaba el parecido; la columna "ronda 2" está remedida con las máscaras nuevas para que la comparación sea justa.
- **ΔE**: diferencia de color CIELAB (1976) píxel a píxel dentro de la silueta común, a ¼ de resolución con un desenfoque leve. Es una medida exigente: un desplazamiento de pocos píxeles de un borde de alto contraste (montura, pupila, cremallera) cuenta como diferencia de color. Como referencia, ΔE ≈ 2 es apenas perceptible y la mediana de la ronda 2 estaba entre 11 y 17.
- **IoU por zonas de color**: media de la coincidencia de las zonas azul (piel), negra (sudadera, montura) y blanca/gris (playera, tenis, ojos) entre la referencia y el modelo posado (`docs/pose_fit.json`).

Además:

- `cmp_hero_master.png`: render hero con wordmark junto a la imagen maestra `00`.
- `cmp_part_*.png`: cada pieza junto a su lámina `08–14`, fotografiada con la cámara calibrada de esa lámina (`part_cameras`) y, para piezas sueltas, su colocación (tenis escalonados, cubos separados).
- `posefit_*`, `semfit_*`, `camfit_*`, `partfit_*`: diagnósticos de los ajustes (silueta, zonas de color, cámara y piezas).

Las técnicas usadas en cada ronda, con sus números, están en `art-direction.md` §7 y §8.

## 2. Validación de los GLB (Khronos glTF-Validator)

`cd web && npm run validate` → `docs/gltf-validation.json`

| Archivo | Errores | Avisos | Triángulos | Materiales | Animaciones | Tamaño |
|---|---|---|---|---|---|---|
| `exports/morfi_master.glb` | 0 | 0 | 924 864 | 21 | 12 | 62 MB |
| `exports/morfi_web.glb` | 0 | 0 | 215 844 | 21 | 12 | 12 MB |
| `parts/morfi_head.glb` | 0 | 0 | 218 592 | 5 | – | 19 MB |
| `parts/morfi_hoodie.glb` | 0 | 0 | 113 496 | 5 | – | 10.0 MB |
| `parts/morfi_shoes.glb` | 0 | 0 | 56 000 | 4 | – | 6.5 MB |
| `parts/morfi_body_base.glb` | 0 | 0 | 40 000 | 1 | – | 4.8 MB |
| `parts/morfi_tshirt.glb` | 0 | 0 | 19 000 | 2 | – | 4.2 MB |
| `parts/morfi_pixels.glb` | 0 | 0 | 20 736 | 1 | – | 4.1 MB |
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
| Caja (m) | x ±0.386, y −0.278…0.319, z −0.003…1.143 | ídem |

Las acciones `Ref_<vista>` son las poses por toma (una pose estática por referencia); el visor no las muestra en el desplegable de animaciones, sino al pulsar el botón de cada vista.

La altura sin cubos es 1.0 (convención del proyecto) y 1.143 con los cubos.

## 4. Visor web

`cd web && npm run build && npm run test:e2e`: Chromium headless (SwiftShader, sin GPU) carga el GLB real, recorre las vistas (cámara y pose calibradas de cada referencia), la espalda con y sin "Luz sigue a la cámara", la pose hero, la animación de caminar, el preset cuerpo base, los modos gris/alambre, el fondo oscuro, la captura PNG y una ventana de móvil (390×844). Falla ante cualquier error de consola. Resultado: **SMOKE TEST PASSED** — 215 844 triángulos · 36 mallas · 21 materiales · 12 animaciones. Capturas en `renders/viewer/`.

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

1. **Cara en los perfiles (03 y 05).** En los perfiles de referencia el ojo, el aro del lente y la boca se ven casi de frente, como si la cara "envolviera" el costado de la cabeza; en el frente (02) los mismos lentes son planos y frontales. El modelo sigue el frente y la imagen maestra, así que en perfil el ojo queda casi oculto tras la montura. Es la mayor diferencia que queda en esas dos vistas (ΔE mediana 13–15, sobre todo en la cabeza).
2. **Cubos y mano en perfil.** Los cubos se resuelven con un giro del grupo por toma (trampa de cámara en `Ref_<vista>`); la mano cercana de los perfiles de referencia cuelga más abajo y es más grande que en el frente, y el modelo no la puede igualar sin deformarse.
3. **Sudadera.** En las referencias la sudadera es más mullida: más volumen de capucha junto al cuello y elástico de la cintura más recogido. El modelo se acercó (dobladillo 0.222 → 0.210, rollo de capucha más ancho), pero el bajo sigue algo más abierto. En la lámina 08 la capucha está levantada porque no hay cabeza dentro; en el modelo descansa sobre la espalda. No hay simulación de tela: los pliegues son procedurales y la caída es más limpia.
4. **Tenis.** Tienen las piezas de la lámina 10, pero la puntera es más cuadrada y las correas más planas; en las vistas completas de la referencia se ven cordones/correas más marcados.
5. **Toma hero.** La inclinación de la cabeza ya coincide (lentes a ≈10–11° como en la maestra), pero en la maestra los ojos están ~10 % más juntos de lo que permite el modelo en ese encuadre, y la laptop y la mano derecha no son un calco.
6. **Color residual (ΔE 7–15).** Las zonas planas (piel, sudadera, blancos) quedan a pocos ΔE; lo que pesa en la mediana son bordes de alto contraste desplazados unos píxeles (montura, pupilas, cremallera, cubos) y diferencias de luz propias de cada referencia.
7. **Suelo.** Las referencias tienen fondo blanco uniforme (254); el suelo del render queda en 246–248, con la sombra de contacto bajo los pies.
8. **Prendas sueltas (láminas 08 y 09).** La playera y la sudadera están modeladas para ir puestas: en las fotos de pieza, con su cámara calibrada, la playera muestra las mangas cortas casi fundidas con el cuerpo y la abertura del cuello por dentro, y la capucha de la sudadera queda tumbada en vez de levantada. En el personaje completo no se ve, pero esas dos láminas son las menos parecidas.
9. **Textura laberinto en primer plano.** Su escala está ajustada a las vistas completas; en los renders de piezas cercanos se ve más marcada que en las láminas de producto.
10. **Visor web vs. Cycles.** El visor usa iluminación en tiempo real (Three.js, con la misma idea de luz que sigue a la cámara); colores y sombras son cercanos pero no idénticos a los renders de Cycles. Los renders finales son los de `renders/`.

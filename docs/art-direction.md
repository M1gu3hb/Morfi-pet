# Morfi · dirección de arte y decisiones canónicas

Este documento registra **cómo** se tradujeron las 15 imágenes de `references/` a un único modelo 3D coherente, con qué medidas y por qué. Todo valor citado vive en `config/morfi.json` o en los módulos de `scripts/morfi/`, y el modelo se regenera desde cero con los scripts (ver README).

## 1. Convenciones

| Concepto | Valor |
|---|---|
| Unidad | 1.0 Blender unit = de la planta del tenis a la parte superior de la cabeza **sin cubos** (H = 1). Se puede leer como 1 m. |
| Ejes (Blender) | Z arriba, Morfi mira hacia **−Y**, su izquierda es **+X**. |
| Ejes (glTF) | Y arriba, Morfi mira hacia **+Z** (conversión estándar del exportador: X→X, Z→Y, −Y→Z). |
| Pivote raíz | `Morfi_Root` en el suelo, entre los pies (0, 0, 0). |
| Gestión de color | Cycles, transformada de vista **Standard** (sin AgX/Filmic para no desaturar el azul de marca), exposición 0. |
| Fondo de estudio | `#FDFDF9` medido en las referencias; piso *shadow catcher* + composición. |

## 2. Cámara de las referencias (estimada)

> Desde la ronda 3 cada referencia tiene además **su propia cámara calibrada** (sección 7); la cámara común de abajo sigue siendo la del giro 360° y la del visor cuando no hay calibración.

Las referencias son renders generados individualmente, no fotos calibradas. Se estimó una cámara común comparando la altura aparente frente/espalda (diferencia de perspectiva ≈3.4 %) y el encuadre:

| Parámetro | Valor |
|---|---|
| Lente | 65.2 mm sobre sensor vertical de 36 mm (FOV vertical ≈30.9°) |
| Distancia horizontal | 2.5 |
| Altura de cámara | 0.756 (mira hacia z = 0.52, inclinación ≈5.4°) |
| Azimuts | frente 0°, perfil izq. +90°, espalda 180°, perfil der. −90°, 3/4 frontal +33°, 3/4 posterior −150° |
| Hero (master) | −33°, lente 55 mm, distancia 2.3, altura 0.86, mira a z = 0.465 |

Con esa cámara se ajustó la forma de la cabeza por mínimos cuadrados contra los contornos reales de la vista trasera y el perfil (error medio ≈3 px a 1145×1374).

## 3. Proporciones

| Medida | Valor (H = 1) | Fuente |
|---|---|---|
| Ancho de cabeza | 0.654 | ajuste de contorno (espalda) |
| Alto de cabeza | 0.480 | ajuste de contorno (espalda + perfil) |
| Fondo de cabeza | 0.578 (0.282 frente + 0.296 nuca) | perfil |
| Centro de cabeza | z = 0.7565 | ajuste |
| Exponentes superelipse | arriba 2.94 / abajo 4.66 (sección frontal); perfil arriba 2.57, abajo 2.63 (nuca) / 3.6 (barbilla); planta 3.2 | ajuste + revisión visual |
| Cubos (extensión vertical) | 1.0 → 1.139 (0.139) | frente y espalda (coinciden entre sí) |
| Sudadera, ancho en dobladillo | ±0.222 | frente (silueta medida fila a fila) |
| Sudadera, fondo | −0.186 (cierre) … +0.17 (espalda) | perfil |
| Dobladillo acanalado | z 0.203 → 0.246, inclinado ±0.010 (más alto atrás) | frente (borde inferior ≈0.19) y espalda (≈0.21) |
| Puños | 0.068 de largo, r ≈ 0.053 | espalda |
| Piernas | radio 0.066 → 0.050, centros x = ±0.106–0.122, casi verticales; entrepierna oculta bajo el dobladillo | frente y espalda (ancho medido 0.13) |
| Tenis | largo ≈0.30, ancho ≈0.21 con suela, centros x = ±0.152, punta 5° hacia fuera, suela 0.04, cuello del talón 0.122 | perfil + frente + lámina 10 |
| Manos (centro) | x ≈ ±0.35, z ≈ 0.23, pronadas 55° (nudillos al frente, pulgar adelante-adentro) | frente/perfil |

## 4. Decisiones por elemento

**Cabeza.** Superficie paramétrica (cube-sphere) proyectada radialmente a una superelipse con exponentes que dependen de la dirección: más cuadrada abajo, más redonda arriba y en perfil, como se mide en las vistas. La UV es un atlas de 6 caras (la frontal ocupa 2048² del atlas de 4096²), de modo que la máscara celeste, la boca y la línea de párpado se **hornean desde funciones 3D** y coinciden exactamente con el relieve.

**Cara.**
- Zona celeste (`#89BAF9`, albedo calibrado; el encargo partía de `#8BCBFF`): parches alrededor de los ojos unidos a un hocico celeste que envuelve las mejillas; el límite lateral depende de la orientación de la superficie (más envolvente abajo), compromiso entre el frente (02) y el master (00).
- "Nariz": cuña azul intermedia entre los parches, con relieve muy sutil (4.5 mm).
- Ojos: globos reales (R = 0.125) con iris/pupila en textura, apuntando a un punto a 0.85 delante de la cara (convergencia amable, como en las referencias). La piel alrededor de la apertura se ajusta a una cáscara concéntrica (párpado de 3.5 mm), así el blanco visible tiene exactamente la forma de la apertura y no hay paredes de cuenca visibles en 3/4.
- Córnea separada (tapa transparente sobre el iris). Un *catch-light* pequeño enlazado solo a la córnea (light linking) produce el punto de brillo nítido de las referencias sin agrisar la pupila.
- **Mirada**: en todas las referencias de frente y 3/4 Morfi mira al espectador. Los huesos `eye.L/eye.R` giran juntos hacia cada cámara al renderizar (100 % en frente, 3/4 y hero; 35 % en perfil; 0 % de espaldas), conservando la convergencia modelada. El visor web hace lo mismo en tiempo real (casilla "Ojos a cámara").
- Cejas: tubos curvos proyectados sobre la superficie (no pintados) → leen volumen en perfil.
- Boca: cavidad real por desplazamiento + textura (interior `#3A1512`, lengua `#9A4038`).

**Lentes.** Montura SDF con esquinas muy redondeadas (radio 0.092 sobre medio ancho 0.125), puente recto, bisagras y patillas que corren hacia atrás sin atravesar la cabeza. El plano de la montura se calcula para no tocar mejillas ni globos oculares. Cristal "delgado": en Cycles transparente + reflejo Fresnel suave (sin refracción ni sombras grises); en glTF `KHR_materials_transmission` (IOR 1.45).

**Tres cubos.** Tres superelipsoides independientes (`Pixel_01..03`) en el plano frontal: grande a la izquierda del espectador, mediano arriba a la derecha, pequeño abajo a la derecha apoyado en la cabeza. Posiciones medidas en frente **y** espalda (coinciden en espejo). En perfil se ocultan por oclusión: es intencional (las referencias de perfil los muestran "de frente a cámara", lo que contradice el resto; el encargo pide no reordenarlos).

**Cuerpo base.** SDF suave de una sola piel: torso en pera, cuello ancho (visible entre la cabeza y el cuello redondo de la playera, como en la referencia), brazos cortos y gruesos, manos en puño suelto con **pulgar + 3 dedos** (decisión consistente) giradas para mostrar los nudillos, piernas gruesas y rectas separadas desde el dobladillo, pies redondeados que caben dentro del tenis.

**Playera.** Cascarón de 5 mm sobre el torso, cuello redondo con ribete, mangas cortas, dobladillo a z = 0.232. "M" azul de trazo grueso y extremos redondeados como capa de 1.3 mm conformada a la tela (efecto *puff print*).

**Sudadera abierta.** Cascarón de tela de 11 mm separado de la playera (holgura ≈2.5 cm): cuerpo tipo caja acolchada, mangas gruesas con pliegues suaves cerca del puño, capucha en la espalda con caída en "V" y costura central, rollo de capucha alrededor del cuello, bolsillos de parche, abertura frontal real. Puños y dobladillo acanalados como objetos propios (UV cilíndricas para que el acanalado siga la banda). Cierre metálico de dos hileras de dientes, topes, cursor y jalador; dos cordones con ojales y puntas metálicas. **Sin M en la sudadera.**

**Tenis.** Izquierdo y derecho independientes (espejados): suela gruesa visible como banda con ranura, empeine bajo que desciende hacia la puntera, costura de puntera, panel lateral, lengüeta acolchada que asoma por encima de las correas, cuello acolchado (tubo blando que sigue el borde de la abertura), dos correas gruesas y redondeadas sobre la lengüeta que entran en ojales grandes, muescas verticales en el costado de la suela, talón cuadrado con **contrafuerte azul** de borde curvo (sube desde la suela y queda vertical atrás) y cuello blanco por encima, hueco interior real; la pierna entra por el lado interior del tenis como en las vistas de frente y espalda.

**Laptop.** Objeto independiente cerrado (≈0.20 × 0.15, tamaño medido en la imagen maestra): base + tapa con ranura de cierre, bisagra, muesca frontal, dos puertos y **dos cuadrados azules en diagonal** (no tres) como objeto hijo `Laptop_Logo`, para que la simplificación de la malla nunca los borre. En la pose neutra no se muestra; en la pose Hero va bajo el brazo derecho (hueso `hand.R`), inclinada ≈50° en su plano como en el master.

**Pose hero.** Cabeza girada 22° hacia la cámara e inclinada 8°, laptop bajo el brazo derecho, puño izquierdo apoyado al frente de la sudadera, pie izquierdo abierto. Los ojos miran a la cámara.

## 5. Materiales

| Material | Color base (sRGB) | Notas |
|---|---|---|
| Piel / cubos | `#014EF0` (calibrado desde `#0757F5`, §8) | rugosidad 0.78, *sheen* azul 0.32, color + normal tileables con el laberinto fino (≈7 mm entre líneas) |
| Celeste facial | `#89BAF9` (§8) | en el atlas de la cabeza |
| Sudadera | `#1C1D21` | felpa + laberinto en relieve (líneas apenas más claras), sheen 0.18 |
| Acanalados | `#1C1D21` | normal de rib con UV cilíndricas |
| Playera | jaspeado ≈ `#E6E3E3` | color + normal tileables: jaspeado + laberinto gris más oscuro |
| Logo M | `#1F6BFF` | satinado con capa de barniz leve |
| Montura | `#070E20` | acetato satinado |
| Tenis | `#F0F0ED` / suela `#F4F4F1` / azul `#0B5CF2` | grano fino |
| Metal | `#C9CDD3` | metálico, rugosidad 0.22 |
| Laptop | `#B9BDC5` | metálico satinado |

Las texturas tileables (`textures/master/tile_*.png`) se generan con ruido periódico y Voronoi toroidal, son las mismas en Cycles y en glTF. El relieve se mantiene fino: no cambia la silueta.

**Textura "laberinto".** Las referencias muestran en piel, sudadera y playera un dibujo fino de líneas serpenteantes. Se reproduce con el conjunto de ceros de un ruido periódico de banda estrecha (`textures.squiggle`): líneas de grosor constante que nunca se cortan, con ≈7 mm de separación en la piel y ≈10 mm en las telas. En la cabeza se hornea en el atlas de color con la misma proyección de caja que su mapa normal, para que color y relieve coincidan.

**Luz.** Medición de color por zonas: en las referencias la luz principal es frontal y baja (piernas muy iluminadas, coronilla algo más oscura). La key light está a ≈18° de elevación desde el frente-izquierda, con relleno a la derecha, contraluz y una cenital débil.

## 6. Esqueleto y animación

Huesos: `root, hips, spine, chest, neck, head, pixels, eye.L/R, shoulder/upper_arm/forearm/hand/fingers/thumb .L/.R, thigh/shin/foot/toe .L/.R`. Los pesos se calculan con las mismas partes SDF del cuerpo (torso, brazo, mano, pierna) para cuerpo **y** ropa, así la ropa se deforma igual que la piel. Cabeza (con cara, lentes y cubos) y tenis siguen a su hueso de forma rígida.

Acciones incluidas en el `.blend` y en los GLB: `Pose_Neutral`, `Pose_Hero`, `Idle`, `Walk`, `Run`, `Wave`.

## 7. Calce con las referencias (ronda 3)

Las 15 imágenes son renders de IA independientes: cada una tiene su encuadre y, entre tomas, el personaje cambia ligeramente de pose. Para que una captura del 3D coincida con cada imagen se usan técnicas de *matchmove* / fotogrametría inversa, todas reproducibles con scripts:

1. **Siluetas exactas de las referencias** (`scripts/ref_masks.py` → `references_masks/`). Una red de segmentación (BiRefNet vía `rembg`) separa a Morfi del fondo; el umbral de color anterior no veía los tenis blancos y sí las sombras del piso.
2. **Cámara por toma** (`scripts/fit_cameras.py` → `camera_views` en `config/morfi.json`). La superficie del modelo se exporta como nube densa de puntos (`dump_points.py`) y, para cada referencia, se optimiza acimut, altura, distancia, lente, encuadre y giro para maximizar la coincidencia de siluetas (Powell, primero a ¼ y luego a ½ resolución). La cámara frontal calibrada coincide con la estimada a mano (altura 0.757); la 3/4 frontal resulta estar a ~21° y no 33°, y el master está tomado desde abajo (altura 0.34).
3. **Pose por toma** (`scripts/dump_skin.py` + `scripts/fit_view_poses.py` → `view_poses`). Con los pesos reales del esqueleto se aplica *linear blend skinning* en numpy y se ajustan cabeza (3 giros), brazos (2 + 1 por lado) y un retoque de cámara, con regularización para mantener poses naturales. En la referencia 3/4 frontal la cabeza está girada ~15° hacia la cámara respecto al cuerpo. `rig_model.py` convierte cada pose en una acción `Ref_<vista>`; los renders de vistas y el visor web la usan automáticamente (en el visor, el botón de cada vista aplica cámara y pose).
4. **Correcciones de forma guiadas por residuos**: mapas rojo/verde de silueta por vista (`scripts/eval_silhouettes.py`) y medidas fila a fila en unidades del modelo → mangas menos abiertas, cuello de la capucha más ancho y capucha más larga atrás, pecho menos abultado, manos más arriba/adentro, tenis más anchos y bajos, tobillos más finos, entrepierna más alta.
5. **Textura medida**: en parches planos de 02 se midió la micro-textura (paso alto de luminancia: separación de líneas y contraste). En la piel las líneas son crestas **más claras** y densas (≈7 mm), en la playera finas y suaves, en la sudadera más visibles; los parámetros están en `config/morfi.json → textures` y la desviación del relieve quedó a la de la referencia (playera 4.5 vs 4.6, piel 5.3 vs 7.2 niveles).
6. **Color por zonas en CIELAB**: comparando solo píxeles donde ambas imágenes son del mismo material, la piel, celeste, sudadera y blancos quedan a pocos ΔE; el especular blanco de la piel la desaturaba (sRGB R 21 frente a 3 en la referencia), por eso la piel es ahora terciopelo sin especular blanco con brillo *sheen* azul.

## 8. Calce con las referencias (rondas 4 y 5)

Medido sobre los renders finales de la ronda 3 con las cámaras y poses calibradas:

1. **Iluminación de producto.** En las referencias de espalda y perfil los blancos (≈240) y el azul (≈250) son tan claros como en el frente; con un set de luces fijo en el mundo esas vistas salían más oscuras (blancos ≈200). Las referencias se iluminaron con las luces fijas respecto a la cámara, así que `render_views.py` gira el set completo con el acimut de la cámara de cada toma (`scene.turn_lights`); lo mismo hacen las fotos de piezas, el giro 360° y el visor web ("Luz sigue a la cámara"). Espalda: blancos 200 → 238 (ref. 241), sudadera 28 → 35 (ref. 37). El fondo de las referencias es blanco uniforme también en el suelo (254, 253, 250), con sombra solo bajo los pies; la luz de contorno, que queda detrás del eje de la cámara, proyectaba una sombra larga hacia delante que oscurecía todo el suelo (226–232). Ya no proyecta sombra (`rim_shadow`), y el suelo queda en 246–248.
2. **Albedo calibrado por material.** Con píxeles del mismo material en referencia y render se midió la razón de color en espacio lineal. El azul de la piel de la referencia no tiene rojo (sRGB ≈ 0, 88–99, 250) y es algo menos verde: piel `#0757F5` → `#014EF0`, piel oscura `#0647D8` → `#013FD3`, celeste `#8EC4FB` → `#89BAF9`. El encargo da esos HEX como puntos de partida a ajustar con la luz, no como valores finales.
3. **Ojos.** Las pupilas de la referencia son negro puro con un solo brillo nítido; en el render salían gris oscuro (lum. 27) por el reflejo del entorno en la córnea y el cristal. Pupila `#000000` y Fresnel de córnea 1.376 → 1.05 y de lentes 1.18 → 1.05 (casi sin reflejo del entorno). Con un reflejo tan débil, el brillo de una luz se muestreaba mal (chispas sueltas), así que el punto blanco de la referencia —nítido, ≈23 px, arriba y hacia la nariz en cada ojo— es ahora un pequeño disco blanco sin sombreado sobre la córnea (`EyeHighlight_L/R`, hijo del ojo: gira con la mirada; solo lo ven los rayos de cámara y se exporta como emisivo, así que también aparece en el visor web). Posición y tamaño en `config/morfi.json → face.highlight`. Radios medidos en 8 direcciones desde el centro de la pupila (referencia 02): pupila ≈ 44 px, iris ≈ 64.5 px → ángulos 18.5° y 27.5°. El iris de la referencia es azul saturado sin rojo con degradado vertical (marino `#00113C` arriba, azul real `#003596` a los lados, azul brillante `#007CFD` abajo, donde se junta la luz); se pinta igual en la textura del ojo (`iris_top/side/bottom`), con anillo límbico suave.
4. **Rasgos de la cara medidos** (`scripts/face_landmarks.py`, perfiles de píxeles oscuros en columnas fijas y bordes superpuestos), iterando con renders rápidos solo del frente (`scripts/iterate_face.sh`: borrador → rig → render → medida): ojos y aros estaban ~0.03 anchos de cabeza más separados → centro de ojos 0.150 → 0.138, `lens_cx` 0.157 → 0.148, aro 0.024 → 0.019; el armazón entero estaba 12 px alto (aro superior y=349 contra 364 de la referencia) → baja 11.5 mm (aros, puente, bisagras y varillas); cejas bajadas y acercadas (centro 0.147/0.106 → 0.138/0.086, largo 0.084); boca más abajo y algo menor (z −0.1065 → −0.127, media anchura 0.051 → 0.047, caída inferior 0.035 → 0.028); apertura del ojo 0.084 × 0.075. Resultado en la prueba: aro superior 362–382 (ref. 364–381), cejas 303–351 (ref. 304–352), área visible del ojo 0.055 (ref. 0.054), boca a la misma altura y anchura.
5. **Mirada por toma** (`scripts/fit_gaze.py` → `view_gaze`). Se detectan las pupilas negras en cada referencia y se resuelve, sin renderizar (proyección + Gauss-Newton), el pequeño giro de cada ojo que las coloca en el mismo píxel. Con los ojos ya recentrados (punto 4) el giro que queda es de pocos grados (frente ≈ −5° y +2°, 3/4 frontal ≈ −10°). En la toma hero no se aplica: allí la diferencia de pupilas viene de la pose de la cabeza (pediría girar un ojo 20° y el otro 10°, lo que lo dejaría bizco).
6. **Cubos en perfil.** Los perfiles de referencia muestran los tres cubos dispuestos como en el frente. El ajuste de pose por toma incluye ahora el giro del hueso `pixels` (empieza desde el mejor cuarto de vuelta): es una "trampa" de cámara como las de animación estilizada, solo en las acciones `Ref_<vista>`; la pose neutra conserva la disposición canónica. Resultado: +87° en el perfil izquierdo, −85° en el derecho y −99° en la 3/4 posterior; la IoU del perfil izquierdo pasa de 0.919 a 0.940.
7. **Atribución de residuos por pieza** (`scripts/residuals.py`): cada píxel rojo/verde se asigna a la pieza más cercana (cabeza, cubos, sudadera, manos, piernas, tenis). Con eso: manos al 92 %, dobladillo de la sudadera más recogido (0.222 → 0.210) y bajo del cuerpo más redondeado, rollo de la capucha más ancho junto al cuello, mangas algo más finas arriba, cuello del tenis 7 mm más bajo y empeine más bajo. Cada cambio se probó con un ciclo rápido (`scripts/iterate_shapes.sh`: borrador → nube de puntos → IoU de las 6 vistas) y se descartó el que empeoraba alguna vista (suela más ancha: cerraba el hueco entre los pies en 3/4 posterior).
8. **Láminas de piezas con su cámara** (`scripts/fit_part_cameras.py` → `part_cameras`): cada lámina 08–14 tiene su cámara calibrada por silueta (y, para piezas sueltas, su colocación: los tenis escalonados, los cubos separados); `render_parts.py` la usa a la resolución de la lámina.
9. **Ajuste de pose semántico.** Además del contorno, la pose de cada toma se ajusta por zonas de color: referencia y modelo se dividen en azul (piel, cubos), negro (sudadera, montura, cejas) y blanco/gris (playera, tenis, blanco de los ojos); en el modelo cada píxel toma la clase de la superficie visible más cercana (z-buffer con prueba de profundidad, para que no se trasluzcan partes ocultas). La pérdida mezcla la IoU del contorno con la IoU media por clase, y los brazos arrancan desde varios balanceos hacia adelante (una mano delante del cuerpo queda dentro del contorno). Perfil izquierdo: contorno 0.918 → 0.947, clases 0.626 → 0.682.
10. **Pose hero.** En la imagen maestra la cabeza está más inclinada: la línea de los lentes sube 10.7° hacia la derecha, y en el render subía 4.9°. La inclinación de la cabeza de `Pose_Hero` pasa de −8° a −14.5° (`config/morfi.json → hero_pose`), con lo que los lentes quedan a ≈10°. Se probó resolver giro, inclinación y cabeceo para llevar los ojos a las pupilas de la maestra, pero allí los ojos están ~10 % más juntos de lo que permite el modelo y el ajuste "resolvía" eso enseñando el costado de la cabeza o aplanando la inclinación, así que se mantiene la medida directa.

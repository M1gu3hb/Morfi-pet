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

## 9. Calce con las referencias (ronda 7: cara calcada y sudadera rehecha)

1. **Cara calcada de la referencia** (`scripts/morfi/facetrace.py`, `config/morfi.json → face.trace`). En vez de describir la zona celeste con parámetros, se calca de la lámina 14 (cuerpo base, cara sin lentes): la imagen se clasifica en piel azul / celeste (el blanco de los ojos y la boca cuentan como celeste porque ahí van los ojos 3D y la boca modelada; las cejas y la cresta de la nariz, como piel), y cada texel del atlas de la cabeza se proyecta en esa imagen con la cámara calibrada de la lámina. Una corrección afín ajustada en puntos de referencia (centros de los ojos con peso triple, lados de la cabeza a la altura de los ojos, coronilla) absorbe la diferencia entre el modelo de cámara y la ilustración, de modo que los parches quedan centrados en los ojos del modelo. Resultado: dos parches redondeados con borde superior en arco, la cresta azul que baja entre los ojos hasta la nariz y el hocico celeste que ya no llega al borde de la cabeza, como en 14 y 02.
2. **Nariz, cejas y textura de la cara.** La nariz tiene relieve donde termina la cresta calcada (`nose_amp` 0.0045 → 0.010, punta a z −0.062). Las cejas de la referencia ya coincidían en forma y tamaño (grosor 26.8 px contra 24.7, arco 40 contra 43), pero salían grises por el brillo *sheen*; ahora son azul marino `#081633`, sin sheen y casi sin especular. La textura fina se midió con un filtro paso alto: en el celeste se notaba un 40 % más que en la referencia y en el azul un poco menos; se bajó el relieve (`normal` 0.95 → 0.62) y se reequilibró el contraste de las líneas (azul 3.8 contra 3.6 de la referencia).
3. **Sudadera rehecha.** Medido fila por fila, el contorno exterior ya coincidía; lo que la hacía "gordita" estaba dentro: mangas fundidas con el cuerpo, paneles abombados, hombros planos y ninguna capucha. Ahora:
   - **capucha tumbada** sobre la espalda: una capa de tela con contorno en U, costura central y borde marcado (unión dura, no difuminada), más gruesa en la nuca;
   - **bordes de la capucha**: un anillo que rodea el cuello por detrás y dos rollos que suben en diagonal desde los ojales de los cordones hacia la nuca, como en 02 y 06;
   - **hombros caídos** desde el cuello, **mangas separadas del cuerpo** por un pliegue (mezcla 0.018 → 0.014), **paneles más planos** (superelipse 2.7 → 3.4) y **bolsillos con relieve**;
   - **abertura delantera** más ancha arriba (media anchura 0.072 → 0.092) y más estrecha abajo (0.081 → 0.066), como en la referencia, y la playera recortada bajo la línea del hombro para que no asome.
   Se probaron 11 variantes con renders rápidos del frente, la espalda, el perfil y la 3/4, más el ciclo de siluetas: acercar codos y muñecas al cuerpo empeoraba la silueta del frente (las mangas de la referencia van más afuera) y se descartó.
4. **Capucha levantada para la foto de producto 08.** En la lámina la capucha está levantada porque no hay cabeza dentro. La sudadera tiene ese segundo estado (`Hoodie_Product`, `config/morfi.json → clothes.hood_up`): una cúpula de tela detrás del cuello con la abertura hacia delante y arriba y su borde enrollado. Vive en la colección `ProductShots`, no se exporta ni se rigea, y solo la usa la foto de pieza de la sudadera (con su cámara recalibrada).
5. **Rig más robusto.** En una construcción parcial apareció un ojo girado 90°: al emparentar un objeto rígido a su hueso, Blender reevalúa el esqueleto y puede mover el emparentado justo antes. Ahora `rig_model.py` emparenta todos los objetos rígidos y después restaura de una vez su posición en el mundo.

## 10. Calce con las referencias (ronda 8: capucha con volumen, cara multivista, cámaras de perfil)

1. **Capucha con volumen en la espalda.** En 04, 05 y 07 la capucha no es una capa plana: es una bolsa de tela que cuelga en U desde los hombros y sobresale ~7 cm de la espalda en el perfil 05 (medido con la escala de la cámara calibrada, 992 px/m), más abultada un poco por encima de la punta, con la parte de abajo mirando hacia el suelo (por eso proyecta la sombra que la hace legible desde atrás). `clothes.hood_layer` ahora tiene un perfil de grosor (`t_tip` 1.4 cm en la punta → `t_peak` 7 cm a `s_peak` 0.4 de la altura → `t_top` 4.5 cm hacia el cuello), abombado al centro (`x_puff`), con contorno en U más redondo (`tip_power` 0.5) y la punta en z 0.345 (en 04 está a z ≈ 0.33–0.35). La costura central sigue la superficie (3 mm de hondo sobre la capucha, no una ranura que la atraviese).
2. **Capucha levantada (lámina 08) rehecha.** El cuello del cuerpo cortaba la capucha levantada (se le restaba el volumen del cuello, que en la sudadera vacía no existe): por eso salía sin borde y con una abertura dentada. Ahora la capucha levantada no se recorta con el cuello; es una cúpula baja y ancha (centro z 0.48, semiejes 0.18 × 0.11 × 0.115) con la abertura inclinada 35° hacia arriba y un borde enrollado en arco (0.15 × 0.11, tubo 2.4 cm), como el arco que enmarca el interior oscuro en 08. Además la foto de producto lleva las mangas como en un maniquí invisible (`clothes.product_arm`: 22° hacia delante, 8 % más largas, con sus puños `Hoodie_Product_Cuff_L/R`). IoU de la silueta de la lámina 08 (render final): 0.835 → 0.859.
3. **Cara calcada desde varias tomas.** La lámina 14 ve la cara de frente; los lados de la cabeza (donde el hocico celeste envuelve las mejillas) solo los roza, y en la ronda 7 esa proyección rasante dejaba una media luna celeste en el costado. Ahora la 3/4 06 también proyecta su máscara con su cámara calibrada y la pose de cabeza ajustada, y cada texel mezcla las tomas según lo de frente que lo ve cada cámara (texturizado proyectivo multivista, como en fotogrametría): donde la lámina ve la cara de frente manda la lámina, lo que tapan los lentes toma el valor de la piel visible más cercana (lo que se ve a través del cristal cuenta como celeste, como el ojo) y donde ninguna cámara ve bien queda piel azul. Se probaron también los perfiles 03/05, pero en ellos la cara está girada hacia la cámara (la trampa del §7 de `validation.md`) y su celeste quedaba flotando a media mejilla: se dejaron fuera. La clasificación celeste/azul usa ahora el cociente rojo/azul (el celeste lo conserva en la sombra bajo la barbilla, donde el umbral de brillo lo convertía en azul y dejaba un borde desgarrado), descarta el filo de luz de la silueta y el borde se afila (`sharpen`).
4. **Mirada de la lámina 14.** El render del cuerpo base miraba al frente sin más: las pupilas quedaban un 15 % más separadas que en la lámina (0.390 contra 0.339 del ancho de la cabeza). `fit_gaze.py` ajusta ahora también la mirada de la lámina 14 con su cámara de producto, y `render_parts.py` la aplica.
5. **Cejas** menos arqueadas y más gruesas (`brow_arch` 0.027 → 0.015, grosor 0.025 → 0.029, extremo interior más alto), como en 14.
6. **Textura de fieltro.** De cerca (frente de 02, ×4) las líneas de la referencia son finas, más separadas y de contraste variable; el laberinto denso y uniforme se veía como gusanos. Piel: `f0` 56 → 38, línea 0.12 → 0.05, ganancia 0.55 → 0.35 y contraste modulado (`mod_lo` 0.2). Sudadera: más fina y menos marcada (`f0` 30 → 40, línea 0.10 → 0.06, ganancia 0.9 → 0.45, `mod_lo` 0.3).
7. **Cámara del perfil derecho.** En un perfil la silueta casi no cambia con la altura de la cámara y el ajuste se había ido a 1.08 m (mirando los tenis desde arriba, con el tenis lejano asomando por encima del cercano). En 05 el tenis lejano apenas asoma ~25 px: con los pies a 0.18 m y la cámara a 2.5 m eso es una cámara a ~0.4 m, la misma altura que da el ajuste del otro perfil (0.37). Con la altura fija en 0.40 (`fit_view_poses.py → HEIGHT_FIX`) el ajuste mejora mucho: IoU 0.904 → 0.925 y clases 0.62 → 0.68, y el brazo derecho queda adelantado como en la referencia.
8. **Pose hero calzada con los lentes.** Midiendo en la imagen maestra 00 los centros de los dos lentes y el contorno de la cabeza (`scripts/hero_landmarks.py`), el render tenía la cabeza 20 px a la izquierda y los lentes 60 px a la izquierda y 30 px arriba: con esa pose, ajustar la mirada pedía girar los ojos más de 20° (bizcos). Ahora la columna se inclina hacia la derecha (2°) y la cabeza gira menos (−22° → −13°), cabecea 6° y se inclina −20° (`config → hero_pose`): los lentes caen a menos de 9 px de los de 00, el contorno de la cabeza a menos de 7 px y la línea de los lentes tiene la misma inclinación (−12°). Solo entonces se ajustó la mirada (4.6° y 8.8°, ya sin bizquear).
9. **Cuerpo base más parecido a la lámina 14.** Medido fila por fila contra la silueta de 14, los brazos del cuerpo base eran un 30 % más delgados y los pies desnudos un 40 % más angostos que en la lámina (allí son casi del tamaño de un tenis). Los brazos engordan hasta donde lo permiten las mangas y los puños sin atravesarlos (radios 0.043/0.039/0.038 → 0.050/0.046/0.041) y los pies crecen (semiejes 0.060 × 0.105 × 0.034 → 0.085 × 0.125 × 0.040), siempre dentro de los tenis: se comprobó en el frente, los perfiles, la espalda y la 3/4 que no asoman. IoU de la silueta de la lámina 14: 0.913 → 0.932.
10. **Brazos en los perfiles.** En 03 y 05 el brazo cercano cuelga junto al cuerpo con la mano adelante; con el brazo separado como en reposo, de lado la manga apuntaba a la cámara y se veía la boca del puño. Ni el contorno ni las zonas de color lo distinguen (manga y cuerpo son negros), así que en esas dos tomas se fija a ojo solo cuánto se acerca el brazo al cuerpo (`fit_view_poses.py → POSE_FIX`: 18°) y el resto (balanceo, codo, cabeza, cámara) se ajusta como siempre. Así el perfil izquierdo mejora también en los números (IoU 0.936 → 0.938); fijar además el codo doblado empeoraba la silueta (0.928) y se descartó. La playera conserva su propio radio de manga (`clothes.shirt_arm_r`) para no asomar por la sisa de la sudadera al engordar el brazo del cuerpo base.

**Números de la ronda 8** (render final contra la versión publicada anterior, ronda 6): perfil derecho IoU 0.915 → 0.928 y ΔE 13.1 → 12.1; 3/4 frontal ΔE 12.1 → 11.6; 3/4 posterior ΔE 8.3 → 7.4; frente ΔE 11.4 → 11.1; espalda ΔE 7.7 → 7.6; láminas 08 y 14 arriba. El perfil izquierdo empeoró (IoU 0.942 → 0.932, ΔE 15.2 → 18.6) porque la mejilla celeste que envuelve la esquina de la cara quedó azul en el costado (ver `validation.md` §7).

## 11. Calce con las referencias (ronda 9: sudadera en triángulo, cara de los perfiles)

1. **Caída de la sudadera.** Medido fila por fila (ancho de la zona negra en 02 y 04), en las referencias el contorno baja casi en línea recta desde el borde de la capucha hasta los puños: un triángulo. El modelo se ensanchaba en los hombros (+22–35 px), tenía los puños bajos y el cuerpo en barril, y por eso se leía "gordito". Cambios:
   - Mangas raglán que nacen junto al cuello (`sleeve_start` 0.092 / 0.476) y bajan en diagonal hasta los puños, unidas al cuerpo con un empalme suave (`sleeve_blend` 0.04, sin pliegue en el hombro).
   - Cuerpo más angosto y plano: semieje x 0.226 → 0.205 y sección más cuadrada (`p_h` 4, `q_top` 2.8, `q_bot` 6). Los hombros caen desde el cuello (`shoulder_slope`: desde 10 cm del centro, con pendiente 0.9) y los rollos del borde de la capucha son más grandes (`hood_rolls`).
   - El aro del borde de la capucha era tan ancho como los hombros (0.165 m de semieje lateral). Visto de frente, sus costados formaban una barra horizontal que se leía como hombreras. Ahora abraza el cuello (0.12 × 0.12, tubo 3.5 cm adelante → 5 cm atrás), y la línea del hombro baja desde la capucha como en 02 y 04. La bolsa de la capucha en la espalda no cambia.
   - Puños más anchos (0.062 / 0.060). La muñeca sube 2 cm por el antebrazo y las manos crecen ×1.03.
   - Dobladillo más alto (z 0.222) con una banda de rib más alta (hasta z 0.270), como en 02. El cuerpo de la sudadera entra 3 cm en la banda (`hem_overlap`), porque la cámara de la espalda mira desde arriba y si no veía el interior.
   - Bajo la sudadera la playera va sin mangas. Las mangas cortas nunca se ven y atravesaban las mangas raglán, más delgadas. Como en los pipelines de personajes de juego, se quita lo oculto. La lámina 09 usa `Tshirt_Product`, la misma playera con mangas, que solo existe para esa foto.
   - Los laterales, que ya se parecían, no cambian de forma.
2. **Cara de los perfiles: trampa de cámara.** Analizando solo las referencias, en 03 y 05 la cabeza está dibujada en perfil puro: su contorno mide 0.88 del ancho frontal, igual que el modelo visto de lado. Pero el lente se ve con ancho/alto 0.48 (03) y 0.39 (05) en vez de verse de canto, y se ven el ojo con su iris, la boca y la mejilla celeste, como si la cara estuviera girada hacia la cámara. Ninguna cabeza rígida hace las dos cosas. La animación estilizada lo resuelve con una "trampa de cámara" por toma, y eso hace ahora `scripts/morfi/facecheat.py`.
   - En el render de cada perfil, cada punto de la cara se desliza por la superficie de la cabeza con el acimut φ' = φ + θ(1 + cos φ)/2. El centro de la cara gira θ, los lados la mitad y la nuca nada.
   - Cada punto conserva su altura y su profundidad relativa a la superficie, así que el contorno de la cabeza no cambia.
   - Cabeza, cejas, lentes y ojos (con córnea y brillo) reciben una shape key exacta para esa toma.
   - Los ojos reciben además el movimiento rígido que mejor sigue su propio deslizamiento (ajuste de Kabsch), para que la mirada siga girando alrededor del centro del globo. Con un ojo rígido sin esa corrección, el blanco del ojo asomaba fuera de la cuenca donde la cara plana dobla la esquina de la cabeza.
   - El relieve de la cara se conserva al 35 % (`depth`): los lentes delante de la piel y el ojo que sobresale. En los perfiles dibujados el ojo queda bajo su lente; con el relieve real asomaba blanco por detrás de la montura.
   - θ = 26° en 03 y −20° en 05, medidos con el lente: ancho/alto 0.48 y 0.39, como en las referencias. La mirada gira 0.25 hacia la cámara, con lo que el iris queda un poco por delante del centro del lente, como en 03/05.
   - Solo afecta a los renders por toma (config `face_cheat`). El `.blend` maestro y los GLB no cambian.
3. **Mejilla celeste de los perfiles.** Con la trampa, 03 y 05 ya pueden calcar la cara. Su máscara se proyecta a través del mismo deslizamiento (`ViewTrace` con `face_cheat`) y se mezcla con la lámina 14 y la 3/4 06 según lo de frente que cada cámara ve cada texel. En la ronda 8 se habían descartado porque, sin la trampa, su celeste quedaba flotando en el costado.
4. **Cubos de los perfiles.** En 03 y 05 los cubos están dibujados de frente a la cámara: 05 espejado no coincide con 03, mientras que 02 y 04 espejado sí coinciden, y en los perfiles de 01 la pila es la física. El giro del grupo en esas dos tomas ya no se ajusta (daba 46°): se fija a "de frente a la cámara" (`fit_view_poses.py → POSE_FIX`).
5. **Cejas** 6 mm más arriba (`brow_center` z 0.086 → 0.092). Respecto del borde superior de la montura, en 02 y 06 quedan 7 px más altas que en el render. La lámina 14 las tiene más bajas, pero manda la vista principal.
6. **Cremallera, playera y cuello.** Con el dobladillo más alto el cursor quedaba fuera de la tela y no se veía. Ahora los dientes son más gruesos y espaciados (paso 5.8 → 6.6 mm) y el cursor y su tirador son más grandes, a la altura del rib como en 02. La playera termina más arriba (z 0.245) y su cuello redondo sube 1.5 cm, de modo que se ve menos cuello azul, como en 02.
7. **Brazos en los perfiles.** En la pose de reposo el brazo sale 50° del cuerpo. Con solo 18° de aducción (ronda 8), en 03 y 05 la manga seguía apuntando a la cámara: se veía la boca del puño y la mano colgaba debajo. En las referencias, en cambio, el brazo cuelga junto al cuerpo y la mano queda adelante, a la altura del dobladillo. Ahora el brazo cercano se acerca 28° al cuerpo, se adelanta 8° y dobla el codo 25° (`POSE_FIX`): la manga se ve de lado y la mano queda justo bajo el puño, un poco adelante. Con más aducción el brazo atraviesa el torso, y con el codo más doblado la mano sobresale por delante de la sudadera. El contorno casi no cambia (unas milésimas de IoU): ni la silueta ni las zonas de color distinguen la manga del cuerpo, que son negros los dos.

**Números de la ronda 9** (render final contra la ronda 8):
- Frente: IoU 0.943 → 0.945 y ΔE 11.1 → 10.7, con las zonas de color del ajuste de pose en 0.663 → 0.692. La zona negra (sudadera) del frente pasa de IoU 0.77 a 0.81.
- Espalda: 0.944 → 0.943, ΔE 7.6 → 7.5. 3/4 frontal: 0.902 → 0.909.
- Láminas: sudadera 0.859 → 0.864, playera 0.881 → 0.928, cuerpo base 0.932 → 0.940.
- Perfil izquierdo: ΔE 18.6 → 17.6, con la cara visible.
- La IoU de los perfiles baja (0.932 → 0.920 y 0.928 → 0.908): los cubos y el brazo cercano se fijan ahora como están dibujados y no como prefiere el contorno (ver `validation.md` §1).
- La 3/4 posterior baja un poco (0.902 → 0.897, ΔE 7.4 → 7.7).

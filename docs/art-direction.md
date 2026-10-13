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

Las referencias son renders generados individualmente, no fotos calibradas. Se estimó una cámara común comparando la altura aparente frente/espalda (diferencia de perspectiva ≈3.4 %) y el encuadre:

| Parámetro | Valor |
|---|---|
| Lente | 65.2 mm sobre sensor vertical de 36 mm (FOV vertical ≈30.9°) |
| Distancia horizontal | 2.5 |
| Altura de cámara | 0.756 (mira hacia z = 0.52, inclinación ≈5.4°) |
| Azimuts | frente 0°, perfil izq. +90°, espalda 180°, perfil der. −90°, 3/4 frontal +33°, 3/4 posterior −150° |
| Hero (master) | −33°, lente 55 mm, distancia 2.3, altura 0.86 |

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
| Sudadera, ancho en dobladillo | ±0.216 | frente |
| Sudadera, fondo | −0.186 (cierre) … +0.17 (espalda) | perfil |
| Dobladillo acanalado | z 0.212 → 0.255 | espalda (≈0.23) y frente (≈0.205), promedio |
| Puños | 0.068 de largo, r ≈ 0.053 | espalda |
| Entrepierna | z ≈ 0.17 | frente |
| Tenis | largo 0.318, centros x = ±0.163, punta de pie 5° hacia fuera, alto 0.13–0.14 | perfil + frente |
| Manos (centro) | x ≈ ±0.35, z ≈ 0.23 | frente/perfil |

## 4. Decisiones por elemento

**Cabeza.** Superficie paramétrica (cube-sphere) proyectada radialmente a una superelipse con exponentes que dependen de la dirección: más cuadrada abajo, más redonda arriba y en perfil, como se mide en las vistas. La UV es un atlas de 6 caras (la frontal ocupa 2048² del atlas de 4096²), de modo que la máscara celeste, la boca y la línea de párpado se **hornean desde funciones 3D** y coinciden exactamente con el relieve.

**Cara.**
- Zona celeste (`#8EC4FB`): parches alrededor de los ojos unidos a un hocico celeste que envuelve las mejillas; el límite lateral depende de la orientación de la superficie (más envolvente abajo), compromiso entre el frente (02) y el master (00).
- "Nariz": cuña azul intermedia entre los parches, con relieve muy sutil (4.5 mm).
- Ojos: globos reales (R = 0.125) con iris/pupila en textura, apuntando a un punto a 0.85 delante de la cara (convergencia amable, como en las referencias). La piel alrededor de la apertura se ajusta a una cáscara concéntrica (párpado de 3.5 mm), así el blanco visible tiene exactamente la forma de la apertura y no hay paredes de cuenca visibles en 3/4.
- Córnea separada (tapa transparente sobre el iris). Un *catch-light* pequeño enlazado solo a la córnea (light linking) produce el punto de brillo nítido de las referencias sin agrisar la pupila.
- Cejas: tubos curvos proyectados sobre la superficie (no pintados) → leen volumen en perfil.
- Boca: cavidad real por desplazamiento + textura (interior `#3A1512`, lengua `#9A4038`).

**Lentes.** Montura SDF con esquinas muy redondeadas (radio 0.092 sobre medio ancho 0.125), puente recto, bisagras y patillas que corren hacia atrás sin atravesar la cabeza. El plano de la montura se calcula para no tocar mejillas ni globos oculares. Cristal "delgado": en Cycles transparente + reflejo Fresnel suave (sin refracción ni sombras grises); en glTF `KHR_materials_transmission` (IOR 1.45).

**Tres cubos.** Tres superelipsoides independientes (`Pixel_01..03`) en el plano frontal: grande a la izquierda del espectador, mediano arriba a la derecha, pequeño abajo a la derecha apoyado en la cabeza. Posiciones medidas en frente **y** espalda (coinciden en espejo). En perfil se ocultan por oclusión: es intencional (las referencias de perfil los muestran "de frente a cámara", lo que contradice el resto; el encargo pide no reordenarlos).

**Cuerpo base.** SDF suave de una sola piel: torso en pera, cuello ancho, brazos cortos y gruesos, manos tipo mitón con **pulgar + 3 dedos** (decisión consistente), piernas cortas y pies redondeados que caben dentro del tenis.

**Playera.** Cascarón de 5 mm sobre el torso, cuello redondo con ribete, mangas cortas, dobladillo a z = 0.232. "M" azul de trazo grueso y extremos redondeados como capa de 1.3 mm conformada a la tela (efecto *puff print*).

**Sudadera abierta.** Cascarón de tela de 11 mm separado de la playera (holgura ≈2.5 cm): cuerpo tipo caja acolchada, mangas gruesas con pliegues suaves cerca del puño, capucha en la espalda con caída en "V" y costura central, rollo de capucha alrededor del cuello, bolsillos de parche, abertura frontal real. Puños y dobladillo acanalados como objetos propios (UV cilíndricas para que el acanalado siga la banda). Cierre metálico de dos hileras de dientes, topes, cursor y jalador; dos cordones con ojales y puntas metálicas. **Sin M en la sudadera.**

**Tenis.** Izquierdo y derecho independientes (espejados): suela de goma con ranura perimetral, puntera con costura, panel lateral, lengüeta acolchada, dos correas anchas sobre la lengüeta que entran en ojales grandes, contrafuerte azul en el talón y hueco interior real para el pie.

**Laptop.** Objeto independiente cerrado: base + tapa con ranura de cierre, bisagra, muesca frontal, dos puertos, **dos cuadrados azules en diagonal** (no tres). En la pose neutra no se muestra; en la pose Hero cuelga del hueso `hand.R`.

## 5. Materiales

| Material | Color base (sRGB) | Notas |
|---|---|---|
| Piel / cubos | `#0757F5` | rugosidad 0.78, *sheen* azul 0.45, normal "terciopelo" tileable (celdas finas) |
| Celeste facial | `#8EC4FB` | en el atlas de la cabeza |
| Sudadera | `#1D1E23` | felpa: normal tileable, sheen 0.35 |
| Acanalados | `#1D1E23` | normal de rib con UV cilíndricas |
| Playera | jaspeado ≈ `#C5C5C8` | textura tileable de color + tejido |
| Logo M | `#1F6BFF` | satinado con capa de barniz leve |
| Montura | `#070E20` | acetato satinado |
| Tenis | `#F0F0ED` / suela `#F4F4F1` / azul `#0B5CF2` | grano fino |
| Metal | `#C9CDD3` | metálico, rugosidad 0.22 |
| Laptop | `#B9BDC5` | metálico satinado |

Las texturas tileables (`textures/master/tile_*.png`) se generan con ruido periódico y Voronoi toroidal, son las mismas en Cycles y en glTF. El relieve se mantiene fino: no cambia la silueta.

## 6. Esqueleto y animación

Huesos: `root, hips, spine, chest, neck, head, pixels, eye.L/R, shoulder/upper_arm/forearm/hand/fingers/thumb .L/.R, thigh/shin/foot/toe .L/.R`. Los pesos se calculan con las mismas partes SDF del cuerpo (torso, brazo, mano, pierna) para cuerpo **y** ropa, así la ropa se deforma igual que la piel. Cabeza (con cara, lentes y cubos) y tenis siguen a su hueso de forma rígida.

Acciones incluidas en el `.blend` y en los GLB: `Pose_Neutral`, `Pose_Hero`, `Idle`, `Walk`, `Run`, `Wave`.

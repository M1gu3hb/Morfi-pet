# MISIÓN: construir el modelo 3D definitivo de Morfi

## 1. Ejecuta el proyecto completo

Actúa como artista técnico de personajes 3D, modelador, especialista en materiales y desarrollador de herramientas de visualización. Vas a trabajar en un repositorio de GitHub inicialmente vacío. El paquete adjunto contiene 15 imágenes del personaje aprobado y este encargo. Inspecciona todas las imágenes visualmente antes de modelar; no te bases únicamente en esta descripción.

Construye un modelo 3D real, editable, de alta fidelidad visual, de **Morfi**, mascota de **Morphiq**. Entrega geometría, materiales, texturas, escena editable, archivos GLB, renders y un visor sencillo para inspeccionarlo. El objetivo es reproducir al personaje aprobado con la mayor precisión posible, no reinterpretarlo ni entregar una mascota genérica inspirada en él.

No termines en un plan, una maqueta, un README o un generador sin ejecutar. Implementa, genera el modelo, renderiza, inspecciona los resultados y corrige las diferencias. Un conjunto de cubos y esferas básicos solo es un bloqueo inicial, no el resultado final. Una imagen aplicada sobre un plano, una cara que siempre mira a cámara, un sprite, un depth map o un giro de PNGs no cuentan como modelo 3D.

Las referencias son ilustraciones generadas individualmente, no fotografías calibradas ni planos de ingeniería. Tienen discrepancias menores. No es posible satisfacer simultáneamente cada píxel de todas: establece un único personaje coherente siguiendo la prioridad de referencias de este documento. No afirmes precisión exacta o reconstrucción medida si no puedes demostrarla. La meta es máxima fidelidad, geometría consistente y evidencia visual verificable.

No necesitas rediseñar la identidad ni pedir aprobación para cada decisión de implementación. Respeta las instrucciones del entorno y los permisos existentes. No contrates APIs, servicios de generación ni infraestructura de pago. Si falta una capacidad indispensable y no existe una alternativa válida, documenta el bloqueo concreto, conserva el trabajo y distingue lo realizado de lo pendiente.

## 2. Referencias y autoridad visual

Todas las rutas son relativas a la raíz de este paquete. Consulta también `INDICE_REFERENCIAS.md` y `manifest.json`.

| Orden | Archivo | Qué gobierna |
|---|---|---|
| 1 | `references/00_Morfi_master_wordmark.png` | Identidad definitiva: cara, ternura, ojos, proporciones, color, sudadera abierta, laptop, pose de presentación y wordmark. Es la autoridad principal. |
| 2 | `references/01_Morfi_turnaround_seis_angulos.png` | Volumen general, capucha, espalda, perfiles y coherencia de la rotación. |
| 3 | `references/02_Morfi_frente.png` | Lectura frontal y pose neutra. |
| 3 | `references/03_Morfi_perfil_izquierdo.png` | Profundidad de cabeza, gafas, torso y zapato; personaje mirando a la izquierda de la imagen. |
| 3 | `references/04_Morfi_espalda.png` | Parte posterior de cabeza, capucha, prenda y talones. |
| 3 | `references/05_Morfi_perfil_derecho.png` | Perfil opuesto; personaje mirando a la derecha de la imagen. |
| 3 | `references/06_Morfi_tres_cuartos_frontal.png` | Transición entre cara y costado; volumen real de gafas y mejillas. |
| 3 | `references/07_Morfi_tres_cuartos_posterior.png` | Transición entre espalda y costado; capucha y patillas. |
| 4 | `references/08_Morfi_sudadera.png` | Construcción de sudadera, apertura, costuras, cierre, bolsillos y capucha. |
| 4 | `references/09_Morfi_playera.png` | Jersey gris, cuello, dobladillos y emblema M. |
| 4 | `references/10_Morfi_tenis.png` | Construcción de los dos tenis, suelas, lengüetas y detalles azules. |
| 4 | `references/11_Morfi_lentes.png` | Montura, puente, bisagras, lentes transparentes y patillas abiertas. |
| 4 | `references/12_Morfi_tres_cubos.png` | Tres piezas azules independientes, bordes redondeados y acabado suave. |
| 4 | `references/13_Morfi_laptop.png` | Laptop plateada cerrada y marca de dos píxeles. |
| 4 | `references/14_Morfi_cuerpo_base.png` | Cuerpo completo debajo de ropa y accesorios; no debe sustituir la identidad facial del master. |

Resuelve las diferencias por propiedad: el master manda sobre rostro, escala relativa y estilo; los perfiles explican profundidad; las piezas aisladas explican construcción, sin agrandarlas arbitrariamente al ensamblar. No copies las exageraciones de microrelieve o cambios de encuadre de las imágenes auxiliares como si fueran medidas.

Invariantes expresos:

- Hay **tres cubos** sobre la cabeza. En un perfil alguno puede ocultarse por oclusión; el modelo conserva los tres.
- En la tapa de la laptop aprobada hay **dos cuadrados azules** en diagonal. No confundirlos con los tres cubos de la cabeza.
- El rostro tiene una zona **celeste**, no una máscara blanca ni una pantalla.
- Los lentes definitivos son **cuadrados con esquinas muy redondeadas**, no los redondos de propuestas anteriores.
- La sudadera está **abierta**; la M azul está en la playera gris interior.
- La textura debe sentirse suave y fina. No convertir los patrones accidentales de algunas imágenes en grabados grandes sobre la piel.

## 3. Identidad, forma y proporciones

Morfi es una criatura digital azul, tierna, inteligente, curiosa y amistosa. Tiene aspecto de nerd accesible, no de robot mecánico ni de humano realista. Debe conservar el mismo encanto con materiales grises de diagnóstico: la identidad no puede depender solo del color o una textura pegada.

Usa una escala reproducible. Puedes normalizar la distancia de la planta del zapato a la parte superior de la cabeza, sin cubos, a **H = 1 unidad**. Es una convención de trabajo, no una estatura física conocida. Estas proporciones son estimaciones iniciales que deberás ajustar comparando con las referencias:

| Relación inicial | Rango orientativo |
|---|---|
| Altura de la cabeza / H | 0.44–0.50 |
| Ancho de cabeza / H | 0.58–0.66 |
| Profundidad de cabeza / ancho de cabeza | 0.50–0.66 |
| Ancho de torso sin brazos / ancho de cabeza | 0.52–0.64 |
| Extensión vertical del conjunto de cubos / H | 0.11–0.17 |

No uses estas cifras como excusa para desobedecer la imagen. Estima puntos clave en coordenadas normalizadas, alinea cámaras y corrige a partir de renders. La cabeza domina; cuello corto, cuerpo compacto, extremidades cortas, manos redondeadas y pies estables. Nada de cuello largo, mandíbula humana, hombros anchos, cintura marcada, orejas o cola inventadas.

### Cabeza y rostro

- Cabeza como caja ancha suavemente inflada, con esquinas de radio amplio y transiciones orgánicas. No esfera, no cilindro, no bloque con biseles pequeños. La cara frontal tiene leve convexidad y el cráneo mantiene volumen desde atrás.
- Zona celeste que rodea los ojos y se une por mejillas y área de la boca, siguiendo el master. Debe integrarse con la superficie; no flotar como una segunda máscara gruesa ni provocar z-fighting. Puede realizarse mediante máscara de material/UV y relieve muy sutil si ayuda.
- Ojos grandes y expresivos: esclerótica blanca, iris azul con gradiente/radios discretos, pupila oscura, brillo de córnea controlado. Volumen ocular real, sin ojos pintados planos. El reflejo principal viene de las luces; no multipliques puntos blancos artificiales.
- Párpados y bordes suaves que encajen con ojos y gafas. Mirada centrada y amistosa, sin estrabismo. Ceja azul marino oscura, corta, redondeada y ligeramente arqueada sobre cada ojo.
- Sonrisa pequeña abierta, curvada y amable, con interior oscuro y un pequeño tono cálido interno como en la referencia. Sin dientes humanos grandes ni hocico añadido. El centro de la cara solo tiene un volumen discreto: no inventar una nariz prominente.
- Sin costuras grandes en el cráneo. Si necesitas UV seams, deben quedar invisibles en el render.

### Cuerpo base, manos y pies

- Torso azul pequeño y ligeramente ovalado, superficie continua, bajo la ropa completa. Brazos cortos y algo gruesos, con articulaciones suaves.
- Manos tipo caricatura: adopta **cuatro dígitos por mano, incluido pulgar**, de forma consistente; esta es una decisión de modelado para resolver la ambigüedad de los renders, no una medición del master. Evita dedos fusionados o desiguales entre vistas.
- Piernas cortas separadas, pies simples redondeados ajustados al interior de los zapatos.
- Base sin ropa de criatura estilizada: pecho y pelvis lisos, sin anatomía sexual, ombligo ni musculatura humana. No agregues ropa pintada en la piel.
- Pose base A relajada: brazos separados aproximadamente 25–30°, manos despejadas del torso y pies a una distancia natural. Cabeza recta para la inspección; inclinación leve solo en la pose hero.

### Tres cubos de identidad

- Tres mallas independientes: cubo grande a la izquierda del espectador en frontal; mediano elevado a la derecha; pequeño abajo a la derecha. Ajusta posición, orientación y tamaño a la referencia principal.
- Esquinas redondeadas, caras ligeramente suaves y profundidad real. Comparten el material azul suave de Morfi.
- Fija sus transformaciones respecto a la cabeza. Al girar no se reordenan para mirar a la cámara. La oclusión natural está permitida.
- Sin soportes visibles, antenas, cables ni piezas adicionales. Desactivables como grupo sin borrar la geometría.

## 4. Ropa y accesorios con volumen real

### Sudadera abierta

Negro carbón, corta y acolchada visualmente, pero de algodón suave. Debe existir separada del cuerpo y de la playera. Frente abierto en dos paneles, cierre metálico plateado con dientes, cinta y cursor; bolsillos frontales divididos, puños y dobladillo acanalados, mangas cortas en proporción a sus brazos, pliegues moderados. Capucha apoyada detrás del cuello con abertura y espesor reconocibles; no una esfera pegada a la espalda. Dos cordones con terminales plateadas. Costuras delicadas y lógicas.

Usa espesor de tela real y separación suficiente de la playera. La prenda debe funcionar al verla de costado y al ocultar el cuerpo. No pongas una M en la sudadera, ni cierres el frente para simplificarla. No uses ruido uniforme como sustituto de pliegues, costuras y bordes.

### Playera

Gris claro jaspeado, cuello redondo ribeteado, mangas cortas, dobladillo, tejido de jersey fino. Proporciones compactas. Pequeña M azul centrada en el pecho, de trazos anchos y extremos suaves, siguiendo la referencia. Usa decal/material o geometría muy delgada estable, sin convertirla en un bloque gigante. No reemplazarla por otro logo. Prenda completa debajo de la sudadera, sin agujeros cuando esta se oculte.

### Tenis

Dos objetos separados, izquierdo y derecho. Blancos, bajos, redondeados, ligeramente grandes. Puntera, paneles cosidos, lengüeta y cuello acolchados, suela de goma con hendiduras discretas, cordones anchos y detalle azul en talón/lateral posterior. Resuelve de forma consistente los tramos de cordón siguiendo primero el master. Hueco interno realista suficiente para que funcionen como accesorios aislados. La textura es micrograno de calzado y goma, no terciopelo azul.

### Lentes

Montura azul marino muy oscuro, dos aros grandes cuadrados con esquinas amplias, puente suave y dos patillas que recorren el costado de la cabeza. Marcos sólidos con espesor; bisagras discretas; cristales transparentes reales que permitan ver los ojos sin oscurecerlos. No lentes de sol. La montura no atraviesa iris, frente o mejillas. El grosor y la posición deben conservar la expresión del master.

### Laptop

Objeto independiente: portátil plateado cerrado, tapa, base, separación de cierre, esquinas redondeadas, bisagra y pocos puertos discretos. Dos cuadrados azules en diagonal sobre la tapa. Tamaño de accesorio, coherente con el brazo de Morfi. Metal satinado con microcepillado fino, no cromado. Prepara un punto de anclaje para sostenerla con el brazo de la pose hero, sin fusionarla con mano o manga. La pose neutra de inspección no necesita sostenerla. No inventes teclado/pantalla detallados si no vas a abrirla.

## 5. Materiales: suavidad antes que ruido

Construye materiales PBR diferenciados. Los colores de esta tabla son **puntos de partida estimados en sRGB**, no muestras certificadas del archivo ni valores finales. Ajusta después con gestión de color y luz coherentes. Convierte sRGB a espacio lineal donde corresponda; no ingreses HEX como valores lineales sin conversión.

| Material | Color inicial aproximado | Roughness inicial | Metalness | Acabado |
|---|---|---|---|---|
| Azul de piel/cubos | `#0757F5` | 0.65–0.85 | 0 | Suavidad aterciopelada, relieve finísimo, reflejo ancho. |
| Zona celeste facial | `#8BCBFF` | 0.70–0.88 | 0 | Misma familia suave; no blanca. |
| Sudadera | `#171A21` | 0.78–0.94 | 0 | Algodón/fleece, trama fina, sin perder detalle en negro. |
| Playera | `#D6D7DA` | 0.80–0.95 | 0 | Jersey gris ligeramente jaspeado. |
| Montura | `#10213C` | 0.25–0.42 | 0 | Acetato satinado, bordes con reflejo suave. |
| Blanco tenis | `#F0F0ED` | 0.48–0.70 | 0 | Piel sintética mate y goma; separar materiales si conviene. |
| Laptop/cierre | `#B9BDC5` | 0.30–0.48 | 1 | Metal plateado satinado. |
| Iris/pupila | Azul profundo / casi negro | Ajustar capas | 0 | Iris legible y córnea brillante. |

Estos parámetros son una propuesta de dirección artística, no una receta universal entre motores. Verifica cada resultado.

Piel: combina color limpio, variación de roughness muy pequeña, normal/bump de alta frecuencia y sheen suave si el pipeline lo soporta. No uses el mismo patrón de ruido en cabeza, tela, metal, goma y vidrio. La superficie debe verse tersa a distancia y suavemente texturizada al acercarse. Nada de grietas, escamas, laberintos profundos, piel de naranja gruesa ni relieve que cambie la silueta. Cualquier microfibra de la versión de render debe ser extremadamente corta; no volverlo peludo. Para web, conserva esa percepción sin depender de millones de fibras.

Cristales: transparencia/transmisión con IOR orientativo alrededor de 1.45–1.5 y baja rugosidad, ajustados para no deformar exageradamente los ojos. Si necesitas un tratamiento más sencillo en GLB, conserva la lectura de ojos y documenta la diferencia. Evita ordenar mal transparencias o convertir los cristales en discos blancos. Córnea y lentes son materiales distintos.

Trabaja con UVs limpias y densidad coherente. Conserva procedurales editables en Blender, pero hornea a mapas compatibles cuando el formato final no represente esos nodos. No presupongas que exportar un GLB conservará toda la red de materiales.

- Mapas según necesidad: base color, normal tangente, roughness, metallic y AO; empaqueta ORM solo si el pipeline elegido lo requiere y documenta canales.
- Base color sin luces, sombras de estudio ni reflejos horneados. AO separado; normales y máscaras tratados como datos, no imágenes de color sRGB.
- Texturas maestras de 2K–4K según área útil; versión web optimizada después de aprobar el aspecto. No aumentar resolución artificialmente para presumir detalle.
- Verifica sheen, transmisión y conversión de materiales en las versiones reales de exportador y visor. Si una extensión no se interpreta, aplica una alternativa explícita y comprueba el resultado.

## 6. Arquitectura del modelo y proyecto

Ruta preferida: **Blender + scripts de Python** para modelo/escena/render, **glTF/GLB** para intercambio y **Three.js + TypeScript + Vite** para inspección web. No hace falta un backend, cuentas de usuario, base de datos ni una landing de marketing. Puedes adaptar el enfoque a capacidades reales, manteniendo los entregables y la fidelidad. Comprueba la versión instalada y consulta documentación oficial cuando necesites una API concreta; no inventes opciones o nombres de sockets.

Primero inspecciona el repositorio, instrucciones existentes, imágenes, Python, Blender, Node y capacidad de render. Usa CPU si no hay GPU; no declares bloqueo únicamente por falta de GPU. Puedes instalar dependencias permitidas. No modifiques configuraciones globales innecesarias ni añadas secretos. Registra versiones y comandos reproducibles. Si Blender no está disponible, intenta una instalación permitida; si es imposible, puedes avanzar con geometría real mediante otra herramienta, pero declara exactamente qué entregables no pudiste generar.

Organiza al menos estas piezas con nombres estables:

```text
Morfi_Root
  Body_Base
  Head
  Face_Details
    Eye_L / Eye_R
    Eyelid_L / Eyelid_R
    Brow_L / Brow_R
    Mouth
  Clothing
    Hoodie
    Tshirt
    Shoe_L / Shoe_R
  Accessories
    Glasses_Frame / Glasses_Lens_L / Glasses_Lens_R
    Pixel_01 / Pixel_02 / Pixel_03
    Laptop
```

La jerarquía puede ajustarse por rig/skin, conservando nombres y visibilidad independiente. La cara celeste puede ser una máscara de material en Head; no exige una malla superpuesta. Usa subobjetos para costuras/cierre cuando sea necesario y agrúpalos con su prenda.

- Mantén fuente de alta calidad y una variante optimizada. No destruyas el master para reducir peso.
- Normales correctas, escala consistente, pivotes lógicos, sin caras duplicadas, z-fighting ni agujeros accidentales. Las aberturas intencionales de ropa se permiten.
- Define ejes, frente y unidad. Documenta la conversión de Blender a glTF y comprueba que el exportado no esté acostado o reflejado.
- Modelo reproducible mediante scripts y configuración central de proporciones/materiales/luces. Evita números mágicos distribuidos en decenas de archivos.
- Mallas y prendas separadas, listas para futura animación. Un rig básico solo si ayuda a lograr la pose hero; no sacrifiques fidelidad por producir muchas animaciones. Una jerarquía de objetos no se debe presentar como skinning completo.
- Si añades shape keys o rig, prueba que ojos, gafas, ropa y cubos acompañen la pose sin atravesarse.

## 7. Escena, cámaras y renders

Monta un estudio claro: fondo blanco cálido, piso mate, sombras suaves de contacto y luces de área grandes. Iluminación principal arriba/frente a un lado, relleno suave al opuesto y separación posterior discreta. Ajusta intensidades a la escala y motor elegidos; no uses números arbitrarios como garantía. El azul debe conservar saturación, la sudadera detalle y el blanco no quemarse.

Elige gestión de color y exposición, registra ambas y compara Blender/visor. Sin bloom excesivo, neones, iluminación cinematográfica dramática o profundidad de campo que oculte errores. Renders de control con materiales neutros y albedo ayudan a separar geometría de luz.

Genera desde el **mismo modelo**:

1. Frente, espalda, perfil mirando a izquierda, perfil mirando a derecha y dos tres cuartos. Cuatro vistas cardinales ortográficas, escala/altura/framing idénticos; tres cuartos compatibles. No modeles seis versiones diferentes.
2. Hero que replique el master: inclinación leve, laptop bajo el brazo y mano opuesta en cintura, misma expresión y encuadre semejante.
3. Hero con wordmark y hero sin texto. El wordmark es una capa de composición separada; no un texto incrustado en la anatomía.
4. Vista aislada de sudadera, playera, par de zapatos, lentes, tres cubos, laptop y cuerpo base sin accesorios. Los objetos deben ser exactamente los usados en el ensamblado.
5. Giro continuo de 360° de 6–10 segundos, a 24 o 30 fps, del personaje completo sin que cambien formas, cubos, textura o pose.

Renders finales: PNG, preferentemente lado largo de 3000 px o más si los recursos lo permiten; vistas transparentes además de las de estudio. Exporta transparencia real y evita halos de premultiplicación. Si necesitas renders pequeños para iterar, no los presentes como finales de alta resolución. Guarda los ajustes de render y una cámara por vista.

Wordmark: toma `00_Morfi_master_wordmark.png` como referencia exacta. Texto **Morfi**, M mayúscula y resto minúsculas, letras gruesas redondeadas azul marino, acento de dos píxeles azules sobre la i como en la imagen. No una tipografía genérica elegida al azar. Puedes recortar limpiamente la marca original y trabajar en composición; si la vectorizas/trazas, compara su silueta y declara cualquier diferencia. No confundas los dos píxeles del wordmark con los tres de la cabeza. No escales un recorte pequeño y lo llames vectorial. Sin fondo blanco rectangular pegado sobre una composición transparente.

## 8. Visor web para revisar y reutilizar

Una interfaz sencilla centrada en el personaje:

- Carga del **GLB exportado**, no un segundo Morfi reconstruido con geometría diferente dentro del frontend.
- Girar, zoom y encuadre con mouse y táctil; restablecer cámara; giro automático opcional.
- Presets para los seis ángulos; pose neutra/hero si están implementadas.
- Mostrar/ocultar sudadera, playera, zapatos, lentes, cubos y laptop. Preset cuerpo base. Sin interpenetraciones visibles al ocultar prendas.
- Fondo claro, oscuro y transparente para comprobar bordes; modo de inspección wireframe/material gris; iluminación controlada sin que el usuario necesite saber de shaders.
- Descarga del GLB y captura PNG realmente funcional; captura con la misma gestión de color y encuadre que el visor. No botones decorativos.
- Estado de carga y error útil, móvil y escritorio, recursos locales sin dependencias ocultas de CDN, sin consola llena de errores.

Conserva el modelo de alta calidad y crea el web después. Como objetivos iniciales, considera 40k–120k triángulos para la versión web y 10–20 MB para el GLB, ajustables con justificación visual y medición real. Son presupuestos orientativos, no requisitos para degradar cara o materiales. Cuenta triángulos, materiales, draw calls y tamaño real. Reporta FPS solo en el entorno donde lo mediste y no prometas rendimiento universal. Si usas compresión, incluye y prueba los decodificadores necesarios.

## 9. Flujo de trabajo y revisión obligatoria

1. **Inspección:** abre las 15 referencias, inventaría herramientas y archivos y escribe un resumen breve de decisiones. Conserva intactas las referencias originales.
2. **Bloqueo de forma:** modela silueta/cabeza/cuerpo/cubos, monta cámaras y renderiza frente/perfil/espalda con material neutro. Corrige proporciones antes del microdetalle.
3. **Identidad:** ojos, celeste facial, boca, cejas y gafas. Compara primer plano y cuerpo completo contra el master. La expresión tiene prioridad.
4. **Prendas y accesorios:** modela separación, espesor, costuras, capucha, calzado y laptop. Revisa intersecciones.
5. **Materiales e iluminación:** ajusta suavidad, color y escala de textura. Inspecciona tanto a tamaño completo como al 100% en recortes de cara, piel y tela.
6. **Renders comparativos:** alinea escala/posición de referencia y render. Genera comparación lado a lado y overlays de diagnóstico, sin contaminar las imágenes finales.
7. **Exportación:** hornea lo necesario, exporta GLB, reimpórtalo en una escena limpia y cárgalo en el visor real. No basta con que exportar no lance excepción.
8. **Iteración:** corrige las diferencias materiales detectadas y repite las vistas afectadas. Guarda al menos un registro antes/después de la mayor corrección. No sigas renderizando sin un defecto concreto que resolver.
9. **Entrega:** produce los archivos finales, verifica el proyecto desde una instalación limpia y documenta límites pendientes con honestidad.

Mide diferencias de silueta, anchura de cabeza, altura de ojos, posición de gafas, proporción cabeza/cuerpo, separación de pies y ubicación de cubos. Una métrica de píxeles completa no es prueba de identidad: luz, pose y fondo influyen. Usa métricas como apoyo, con revisión visual explícita. No declares que viste un render si no lo abriste.

## 10. Criterios de aceptación

- [ ] Se reconoce al Morfi del master sin explicación: cara celeste, lentes cuadrados redondeados, expresión cálida y proporciones fieles.
- [ ] La silueta y los volúmenes son coherentes desde frente, ambos lados y atrás; nada gira artificialmente para mirar a cámara.
- [ ] Exactamente tres cubos en la cabeza; dos píxeles en laptop; marcas de playera y wordmark correctas.
- [ ] Sudadera abierta de verdad, playera debajo, capucha y patillas correctas, tenis distintos izquierdo/derecho.
- [ ] La piel se percibe suave; ni plástico brillante ni pelo largo ni grabados gruesos. Cada material responde de forma diferenciada.
- [ ] Base completa al retirar accesorios, sin huecos, anatomía humana inventada o ropa pintada.
- [ ] Objetos seleccionables y prendas ocultables; ninguna pieza principal fusionada por comodidad.
- [ ] GLB válido con texturas presentes y apariencia revisada tras reimportación; cualquier diferencia respecto al render offline está documentada.
- [ ] Visor y comandos reproducibles funcionan; cámaras y exportaciones no cortan cabeza, cubos ni zapatos.
- [ ] Renders, giro, fuente y exportaciones existen realmente; no se listan archivos que no fueron creados.
- [ ] Informe final distingue aprobación técnica de evaluación estética y enumera discrepancias concretas que aún existan.

No se acepta un cumplimiento meramente textual de estas casillas. Acompáñalas con evidencia visual y comprobaciones reales. Ejecuta validación glTF con una herramienta adecuada si está disponible y revisa sus errores; no ocultes warnings sin leerlos. Para el visor, prueba carga, presets, controles, toggles, captura y descarga. No escribas cientos de pruebas que solo repitan constantes del código.

## 11. Entregables mínimos del repositorio

Organización sugerida; adapta rutas si mejora el proyecto, pero documenta todo:

```text
README.md
package.json + lockfile
references/                     # Las 15 imágenes, sin alterar
docs/
  art-direction.md              # Medidas estimadas y decisiones canónicas
  validation.md                 # Evidencia, métricas reales y límites
scripts/
  build_model.py                # O equivalente reproducible
  render_views.py
  export_assets.py
  validate_assets.py
config/
  morfi.json                    # Proporciones, materiales y cámaras
source/
  morfi_master.blend            # Escena editable, materiales y cámaras
textures/
  master/
  web/
exports/
  morfi_master.glb
  morfi_web.glb
  parts/                        # Piezas separadas exportables
renders/
  hero.png
  hero_wordmark.png
  transparent/
  views/
  parts/
  comparisons/
  morfi_turntable.mp4
web/                            # Visor mínimo, responsive
```

Incluye instrucciones concretas de instalar, generar, renderizar, exportar, validar y abrir el visor, con versiones reales. Empaqueta texturas o usa rutas relativas; la escena debe abrir sin recursos perdidos. Usa Git LFS para binarios que lo requieran y verifica que los archivos estén disponibles, no solo punteros inaccesibles. No subas node_modules, cachés ni renders temporales enormes. No cambies la licencia de las referencias ni apliques una licencia abierta global a la marca sin indicación del propietario.

Haz commits claros y, cuando las credenciales y permisos del entorno lo permitan, deja el trabajo en la rama asignada del repo. Si no puedes subirlo, conserva los archivos y explica el bloqueo. No despliegues en producción ni configures pagos para cumplir este encargo; el objetivo es el modelo, sus renders y un visor ejecutable.

Prioridad ante límites reales de recursos: **identidad y geometría → materiales → master editable y GLB válido → renders de control → visor → optimización y giro final**. Esta prioridad organiza el trabajo, no autoriza a declarar terminado lo que falte. No sustituyas el modelo por una web bonita.

## 12. Formato de cierre de Codex

Entrega una respuesta breve con:

1. Rutas y miniaturas de los renders reales más importantes.
2. Archivos master y GLB, tamaño, cantidad de triángulos y materiales.
3. Comandos exactos para ejecutar y reproducir.
4. Qué validaste, en qué entorno y con qué resultado.
5. Diferencias visibles pendientes frente al master, si existen.
6. Rama/commit y estado de subida, sin inventar enlaces ni afirmar un despliegue no realizado.

Empieza ahora por inspeccionar visualmente las referencias y revisar las herramientas del repositorio. Avanza hasta producir y comprobar los entregables, sin detenerte en una propuesta.

---

## Notas técnicas de consulta

La especificación artística, las proporciones y los parámetros de este encargo son criterios de trabajo propios, no valores tomados de documentación de software. Consulta las APIs exactas de las versiones instaladas.

- [Three.js: GLTFLoader](https://threejs.org/docs/pages/GLTFLoader.html): carga de glTF y configuración de decodificadores; verificar compatibilidad efectiva de extensiones en la versión utilizada.
- [Khronos: KHR_materials_sheen](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_materials_sheen/README.md): capa de sheen para representar respuestas de tela y terciopelo; validar su apariencia en el exportador/visor elegido.
- [Blender: glTF 2.0](https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html): localizar la página correspondiente a la versión instalada para materiales, texturas y exportación. Las rutas del manual pueden cambiar.

Estas fuentes son orientación del pipeline; las **15 imágenes adjuntas** son la autoridad sobre cómo debe verse Morfi.

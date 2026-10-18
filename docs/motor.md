# Motor de animación de Morfi

Base para producir animaciones nuevas de Morfi (y, más adelante, el skill que armará videos tutoriales de
punto de venta). Todo es código: una acción es una función de Python que llena canales cuadro por cuadro;
el motor la hornea al rig, resuelve los contactos con los objetos, impide que el cuerpo se atraviese y lo
verifica. Nada se ajusta a mano en Blender.

Archivos: `scripts/ia3d/anim/` (`clip.py`, `motor.py`, `contacts.py`, `rigmap.py`, `curves.py`, `acting.py`,
`performance.py`, acciones en `actions*.py`, `catalog.py` con las etiquetas del visor y `scenes.py` con las escenas)
y los scripts de hornear, exportar y verificar en `scripts/ia3d/` (`make_actions.py`, `make_scenes.py`,
`export_*.py`, `check_*.py`).

## 1. Cadena de construcción

```bash
B=/d/tools/bl.sh     # Blender 4.5 portátil en D:, temporales en D:
# (pasos 1-3 de docs/ia3d.md §7: malla, regiones, rig del cuerpo -> work/ia3d/morfi_ia_rig_nohands.blend)
$B -b work/ia3d/morfi_ia_rig_nohands.blend --python scripts/ia3d/build_hands.py -- --out work/ia3d/morfi_ia_rig_hands.blend
$B -b work/ia3d/morfi_ia_rig_hands.blend --python scripts/ia3d/build_controls.py -- --out work/ia3d/morfi_ia_rig_full.blend
$B -b work/ia3d/morfi_ia_rig_full.blend --python scripts/ia3d/build_face.py -- --features work/ia3d/face/face_features.json --out work/ia3d/morfi_ia_face2.blend
# muñecas que doblan como muñeca (sin mano que se sale de la manga): ANTES de hornear, para que los
# contactos se resuelvan sobre el rig que los va a reproducir
$B -b work/ia3d/morfi_ia_face2.blend --python scripts/ia3d/fix_wrists.py -- --out work/ia3d/morfi_ia_face3.blend
# los 40 clips (bake + contactos + pasadas FK; ver "Hornear en paralelo" abajo)
$B -b work/ia3d/morfi_ia_face3.blend --python scripts/ia3d/make_actions.py -- --out work/ia3d/morfi_ia_anim4.blend
# anim7 = los 40 clips re-horneados con la capa de manos viva (segunda pasada, mano en reposo viva), unidos con --merge (ver "Hornear en paralelo");
# anim6 y anim5 (clips anteriores) quedan como respaldo. Scratch_Head ya no se publica
# materiales y estudio
$B -b work/ia3d/morfi_ia_anim7.blend --python scripts/ia3d/build_look.py -- --regions work/ia3d/regions/regions.npz --face work/ia3d/face --out work/ia3d/morfi_ia_look4.blend
# lentes y armazón como geometría limpia (idempotente, ~30-60 s)
$B -b work/ia3d/morfi_ia_look4.blend --python scripts/ia3d/fix_glasses.py -- --out work/ia3d/morfi_ia_look5.blend
# cuello sin unión, puños que no atraviesa la mano, sin membrana entre dedos (idempotente; --undo restaura el cuerpo)
$B -b work/ia3d/morfi_ia_look5.blend --python scripts/ia3d/fix_body.py -- --out work/ia3d/morfi_ia_look6.blend
# piel de las cejas sin triángulos visibles (mismas posiciones de ceja; idempotente, marca `brows_fix`) -> base final
$B -b work/ia3d/morfi_ia_look6.blend --python scripts/ia3d/fix_brows.py -- --out work/ia3d/morfi_ia_look7.blend
# visor web: el GLB principal, las curvas de cara de los clips y las escenas (siempre sobre look7)
$B -b work/ia3d/morfi_ia_look7.blend --python scripts/ia3d/export_web.py -- --out work/ia3d/web/morfi_live.glb --face-json work/ia3d/web/morfi_live_face.json
python scripts/ia3d/export_face_anims.py --out work/ia3d/web/morfi_live_anims.json
$B -b work/ia3d/morfi_ia_look7.blend --python scripts/ia3d/export_scenes.py -- --scenes work/ia3d/morfi_ia_scenes3.blend     --pos "D:/MIS PROYECTOS/MORFI PET/MORFI PET/videos/morfi-pos/blender/pos_video.blend"     --pos-audio "D:/MIS PROYECTOS/MORFI PET/MORFI PET/videos/morfi-pos/audio/mix.wav"     --out work/ia3d/web/morfi_live_scenes.glb --json work/ia3d/web/morfi_live_scenes.json --audio-dir web/public/voice/scenes
cd web && npm run sync-live && npm run build && npm run test:live
```

`morfi_ia_scenes3.blend` (las 6 escenas con la capa de manos viva; `morfi_ia_scenes2.blend` y `morfi_ia_scenes.blend` son versiones anteriores) sale de `make_scenes.py` (§8). Los pasos de `export_scenes.py` y de la web (qué es cada
archivo, publicar, verificar): [laboratorio.md](laboratorio.md) §5-8.

**Cadena anterior (videos).** Los videos del POS se renderizaron con `look3`: `face2 → make_actions → anim3 →
build_look → look2 → fix_wrists → look3` (26 clips, sin el arreglo de contactos FK ni los lentes nuevos). Quedan
como están; para un video nuevo se parte de `look7`.

**Orden de `fix_body.py` y `fix_brows.py`**: `fix_body` cambia la topología de `Morfi_Body` (separa la costura del cuello, añade la "copa" bajo la cabeza, quita las membranas entre dedos), por lo que los polígonos ya no son todos triángulos; `fix_brows` va después y trabaja con triángulos y cuadriláteros (triangula en abanico para calcular el campo de las cejas). Comprobado en `look7`: vértices = claves de forma = UV = pesos sin vértices sin peso, 0 caras degeneradas, 0 UV volteados.

**Hornear en paralelo.** El bake completo toca contactos cuadro por cuadro: una sola corrida de los 40 clips
tarda más de una hora. Se parte en grupos con `--only` (cada uno a su archivo, varios Blender a la vez, ~35
min en total con 11 grupos) y se unen con `--merge`:

```bash
$B -b work/ia3d/morfi_ia_face3.blend --python scripts/ia3d/make_actions.py -- --only Think,Laugh --out parts/a.blend
$B -b work/ia3d/morfi_ia_face3.blend --python scripts/ia3d/make_actions.py -- --only Tablet,Calculator --out parts/b.blend
# unir: las acciones se cargan tal cual, no se hornea nada; "archivo@A+B" toma solo esas (los últimos archivos ganan)
$B -b work/ia3d/morfi_ia_face3.blend --python scripts/ia3d/make_actions.py -- --merge parts/a.blend,parts/b.blend@Tablet --out work/ia3d/morfi_ia_anim4.blend
```

`morfi_ia_anim7.blend` = los 40 clips re-horneados desde `face3` con la capa de manos viva (§3 "Manos y dedos vivos"), pasados por `anim/cuff_pass.py` y unidos con `--merge`.

`morfi_ia_anim5.blend` = `anim4` + 7 clips re-horneados (Scratch_Head, Facepalm, Blow_Kiss, Think, Angry, Tablet,
Calculator), unidos con `make_actions.py --merge anim4.blend,<partes>.blend@…`. Conserva `Scratch_Head` como acción
sin usar; los exportadores solo publican los nombres de `ACTIONS`.

`--only` hornea solo esas acciones y guarda un archivo que contiene solo ellas; el archivo completo se arma con
`--merge`, que avisa con `MISSING` las que no están. Los exportadores (`export_web.py`, `export_face_anims.py`)
exigen los 40 nombres de `ACTIONS`: si el .blend no los tiene, `export_web.py` falla con `KeyError`.
`build_controls.py --props-only` reconstruye solo la tablet y la calculadora.

## 2. El esqueleto

- **Cuerpo**: `root`, `hips`, `spine`, `chest`, `neck`, `head`, `hood`, `pixels` (los cubos), hombros, brazos,
  piernas con IK (`foot_ik.<L|R>`, `knee_pole.<L|R>`). Morfi mira hacia −Y; su izquierda es +X; mide 1.14 m
  con los cubos.
- **Manos** (`build_hands.py`): pulgar y tres dedos (índice, medio, anular), tres falanges cada uno
  (`index.01-.03.<s>`, …, `thumb.<s>`, `thumb.02/.03.<s>`). Malla propia de caricatura: palma redondeada
  (tres elipsoides fundidos, ~1.3 veces el grosor de un dedo), dedos que nacen al ras de su borde, pulgar con
  base carnosa y una muñeca que llena el puño de la manga. Cada dedo se funde solo con la palma (entre dedos
  queda un pliegue limpio) y cada vértice sigue a su dedo y a la palma, nunca al dedo vecino: doblar un dedo
  no estira la piel del de al lado.
- **Controles** (`build_controls.py`):
  - IK de brazo (`hand_ik.<s>`, `elbow_pole.<s>`), apagado salvo cuando una acción lo pide (canal `ik.<s>`).
    El IK de Blender estira sin límite; el motor **topa el alcance a 1.08× el largo del brazo**
    (`contacts.MAX_REACH`): estiramiento de caricatura, nunca brazo de chicle. Un clip que se toca la cara pide
    un poco más con `c.max_reach = 1.10` / `1.12` (ver §7).
- **Muñecas** (`fix_wrists.py`): el dorso de la mano (detrás de la articulación) sigue al antebrazo y se funde con
  la mano en 3 cm, el puño de la manga sigue al antebrazo con 30 % de la mano, y un `Limit Rotation` en
  `hand.<s>` (después del `Copy Rotation` del objetivo IK) mantiene la muñeca en un rango humano.
  - Objetos: hueso `prop` frente al pecho, con `prop_tablet` y `prop_calc` (escala 0 = oculto). Los objetivos de
    las manos cuelgan de `prop`, así una mano que sostiene algo lo sigue a donde vaya.
- **Cara** (`build_face.py`, propiedades del rig de −1 a 1 o de 0 a 1): `blink_L/R`, `gaze_x/y`, `mouth_open`,
  `smile` (−1 = boca triste), `mouth_round`, `mouth_side`, `teeth`, `brow_L/R` (sube/baja, recorrido 1.6 cm),
  `brow_in_L/R` (extremo interior: +1 preocupado, −1 enojado), `squint`, `lid_drop`, `lid_angle`
  (+1 enojado, −1 triste), `pupil` (−1 miedo, +1 ternura), `eye_calm` (ojos cerrados tranquilos).
  La cavidad esculpida de la boca se rellenó: la boca es una calcomanía libre sobre la cara plana y se desliza
  ~2.4 cm de lado a lado (`mouth_side`) arrastrando la piel (`Mouth_Shift`). Las mejillas se inflan y suben al
  sonreír o hacia el lado de la boca (`Cheek_L/R`) y la barbilla baja al abrirla (`Jaw_Open`); esas formas se
  calculan solas a partir de `smile`, `mouth_side`, `squint` y `mouth_open`, igual en Blender y en la web.

**Alcance real.** El brazo mide 20 cm del hombro a la muñeca y la panza sobresale 10 cm: una muñeca llega a
3-6 cm frente a la panza. Un objeto se sostiene pegado a la panza, un poco a la izquierda, sobre la palma
izquierda, y el índice derecho cruza a tocarlo. `reach_map.py` calcula, para cada mano y orientación, en
qué puntos cabe la muñeca sin estirar de más ni chocar con la cabeza o el torso.

## 3. Escribir una acción

```python
from .clip import Clip
from . import curves as C

def saludo_contento():
    c = Clip(90)                                   # 3 s a 30 fps
    c.life(seed=7, blinks=[20, 70])                # respiración, micro movimiento, brazos relajados, parpadeos
    c.arm_raise("R", [(0, 0), (12, 70), (78, 70), (90, 0)])
    c.elbow("R", [(0, 0), (12, 60), (78, 60), (90, 0)])
    c.hand("R", [(0, "relaxed"), (10, "open"), (80, "open"), (90, "relaxed")])
    c.expr([(0, "neutral"), (10, "joy"), (90, "happy")])
    c.secondary()                                  # cubos, capucha y pies: siempre al final
    return c
```

Se registra en un diccionario de `actions*.py` (`ACTIONS.update(...)`) y `make_actions.py` la hornea.

### Canales (`rigmap.py`)

| canal | qué hace |
|---|---|
| `<hueso>.rx/ry/rz` | grados en los ejes del mundo en reposo, relativo al padre (+rx inclina al frente, +ry a su izquierda, +rz gira a su izquierda) |
| `<hueso>.tw` | giro sobre el propio eje |
| `<hueso>.cx/cz` | ejes locales (dedos: +cx dobla hacia la palma, cz abre) |
| `<hueso>.lx/ly/lz` | traslación en metros (raíz, cadera, IK, objeto) |
| `<hueso>.s` / `.sy` | escala uniforme (objetos: 0/1) / estirar con volumen (`rigmap.bake` escribe la escala `(s/√sy, s·sy, s/√sy)`) |
| `ik.<L/R>` | 0..1, IK del brazo |
| `prop.<cara>` | propiedad de la cara (`prop.smile`…); `prop.rx`, `prop.lx`… son del hueso `prop` |

Cada acción guarda **todos** los huesos y gestos (en reposo si no los usa): las acciones se encadenan sin saltos.
Eso incluye la **escala**: `rigmap.bake` escribe escala 1 en todo hueso que el clip no escala (si no, el
estirón del clip anterior se quedaba pegado: `Nod_Yes`, `Sad`, `Calm` y `Shake_No` heredaban un estirón
constante de 1.08 en el brazo izquierdo).

### Ayudas del motor (`clip.py`, `motor.py`)

- Cuerpo: `arm_raise`, `arm_fwd`, `arm_swing`, `elbow`, `forearm_lift`, `forearm_in`, `palm`, `wrist`, `shrug`,
  `foot`, `life`, `secondary`, `plant_feet`.
- Manos (`c.hand(lado, [(cuadro, forma)])`): `rest`, `relaxed`, `fist`, `open`, `stop`, `point`, `tap`, `count1`…`count4`,
  `thumbs_up`, `grip`, `pinch`, `hold_flat`, `claw`, o un diccionario propio de ángulos por falange.
- Cara (`c.expr([(cuadro, expresión[, peso])])`): `neutral`, `happy`, `joy`, `laugh`, `sad`, `angry`, `scared`,
  `surprised`, `calm`, `thinking`, `skeptical`, `smug`, `love`, `wink`, `determined`, `confused`, `shy`, `sleepy`.
  Los canales `c.prop(...)` se suman encima (habla, miradas).
- Mirar: `c.look_at([(cuadro, punto | None), ...])` gira la cabeza y el cuello hacia el punto (el
  cabeceo se topa en 7°: con su cabezota, más abajo la cara deja de verse de frente y la barbilla choca con sus manos) y los ojos completan el
  resto. Úsalo siempre que toque algo: así se siente que lo está viendo.
- Vida: `c.life()` ya trae respiración, el peso que pasa de un pie a otro (las rodillas lo absorben), torso y
  cabeza que nunca están quietos, brazos y dedos que derivan; `c.secondary()` añade la inercia de cubos, capucha,
  brazos, manos y cabeza. Toda acción empieza con `life` y termina con `secondary`.
- Alcanzar: `c.reach(lado, [(cuadro, punto_muñeca | None[, peso])])` con orientación
  `orient_keys(lado, [(cuadro, dirección_dedos, dirección_palma)], prop_rot=...)` → `c.reach_rot(...)`.
  Con un objeto girado, los puntos se convierten con `prop_space()` / `prop_world()`.
- Objetos: `c.show("prop_tablet", [(0, 1)])`, `c.place_prop(loc=[...], rot=[...])`.
- Estirón: `c.stretch(lado, [(cuadro, factor)])` (`.sy` de brazo y antebrazo, hasta ~1.12; 1.0 = reposo),
  `c.sy("head", 1.0 + curva)` para el squash de cabeza/cuello (valores absolutos alrededor de 1.0, varias llamadas
  se suman como deltas; cadera, columna y pecho deforman los brazos: dentro de ±3 %), `c.hop(f0, f1, height, crouch, stretch, arms)` para un
  salto con anticipación, estirón, squash al caer y asentamiento.
- Más atributos del clip: `c.max_reach` (tope de alcance propio), `c.stride` (Walk, Run, Sneak: avanzan en el
  sitio y llevan este atributo en la acción), `c.loop`.

### Contactos (`contacts.py`)

- `clip.supports = [{"side": "L", "prop": "Prop_Calc", "frames": (a, b)}]`: el objeto descansa en la palma; el motor
  mueve la mano hasta que toca la cara trasera del objeto, sin atravesarla (también cuenta el puño de la manga).
- `clip.contacts = [{"side": "R", "tip": "index.03.R", "target": "Prop_Calc_Key_21" | "Prop_Tablet_Screen",
  "local": (x, z) | None, "frames": (f0, f1), "ramp": 6}]`: el índice toca exactamente ese punto de f0 a f1,
  baja en línea recta desde 2 cm y vuelve a subir; entre toques flota sobre la superficie.
- `clip.contacts = [{"side": "L", "touch": "head" | "torso", "point": (x, y, z), "region": [grupos],
  "frames": (f0, f1), "ramp": 8}]`: la mano se apoya en el propio Morfi (palmas en las mejillas, puño bajo la
  barbilla, palma en la panza). El punto, dado en reposo, viaja con la cabeza o el pecho y se proyecta en la piel
  deformada cada cuadro; la mano llega por la normal, se apoya exactamente y se queda.
- `resolve_body()`: en todas las acciones con IK, una mano que entra en la cabeza o el torso se empuja hacia afuera
  por la normal de la superficie hasta apenas tocar.
- `clamp_reach()`: el tope de alcance.
- `hold_prop()`: un objeto que él sostiene va en su mano: se toma el agarre en un cuadro (la palma apoyada
  bajo el objeto) y el hueso del objeto sigue a `hand.<lado>` cuadro por cuadro. Un objeto fijo en el espacio
  obliga a la mano a perseguirlo y, al límite del alcance, la mano tiembla.
- `smooth_ik()`: los solvers corrigen un cuadro a la vez (alcance, cuerpo, toques); lado a lado eso hace
  zigzag (una mano que tiembla). Pasa un filtro temporal a los objetivos IK y deja exactos los cuadros de
  contacto. `videos/morfi-pos/tools/diag_jitter.py` lo mide (aceleración que cambia de signo cuadro a cuadro).
- `smooth_touches()`: en tomas largas, una mano apoyada en Morfi se resuelve cuadro por cuadro y puede caer en un
  punto distinto de un cuadro al siguiente (tiembla). La pasada la filtra (mediana + media) y la vuelve a apoyar en
  la piel sin deslizarla.

Pasadas que corren después de convertir los brazos a FK (`rebake_arms`, ver §7): `resolve_body_fk` (pasada de
cuerpo), `clear_sleeves_fk` (giro de la manga) y `refine_contacts_fk` (refinar contactos); `hands_keep_size` es el
contexto que mantiene el tamaño de las manos mientras se resuelve el IK.

### Actuación de cuerpo completo (`acting.py`)

Un gesto mueve dos partes; una persona mueve todo. `Acting(p)` escribe la capa del cuerpo debajo de los
gestos: el peso pasa de un pie al otro en cada frase (cadera, pelvis, columna en contra, el talón libre se
despega), las rodillas ceden en las palabras con acento, el pecho se inclina hacia la cámara, pasos reales
(el pie se despega, viaja en arco y aterriza), saltos con anticipación / estirón / squash al caer, un meneo
feliz y golpes de mano en las palabras. Los cambios de peso se aplican en orden de tiempo al final (`finish()`).

Lecciones del primer video (para cualquier coreografía):
- La cabeza es más ancha que los hombros y sobresale al frente: una mano "junto a la cara" a la altura de la
  cara queda dentro de la cabeza. Para contar con los dedos, la mano va al lado (x ≈ ±0.30, z ≈ 0.46).
- Los brazos miden ~0.20 m (hombro a muñeca): un objeto sostenido va bajo la barbilla y el hombro se adelanta
  (`shoulder.<s>.rz`) en vez de estirar el brazo.
- Al tocar una pantalla, el índice apunta abajo y un poco a su izquierda: la muñeca queda arriba y al frente
  del pecho (si el dedo apunta al frente, la muñeca cae dentro del torso).
- Dos formas de mano a menos de 4 cuadros una de otra se ven como un chasquido de los dedos.

### Actuaciones largas (`performance.py`)

Para videos: una sola toma continua (no acciones de 2-7 s). `Performance(n)` junta la vida de fondo, la boca
sincronizada con la voz real (`speak(lines)`, letras de la alineación de ElevenLabs + envolvente de audio, más
asentimientos y cejas en las palabras con acento) y los gestos en el cuadro de la palabra que les toca. Cada lista
por mano y por cara se aplica una sola vez al construir (`build()`), porque los canales del clip se suman.
Ejemplo completo: `videos/morfi-pos/tools/choreo.py` (fuera del repo), que después se hornea con `scene.py bake`:
bake → `clamp_reach` → `resolve_body` → `contacts.solve` → `smooth_touches` → `resolve_body` otra vez fuera de
los contactos → `verify`.

Ver `anim/actions_props.py` (`Tablet`, `Calculator`): son la plantilla para acciones con objetos.

## Manos y dedos vivos

Miguel: las manos se sentían rígidas, "el mismo caso que tenía el cuerpo primero": la misma pose de dedos en todos
los clips, todos los dedos cambiando de forma a la vez, un saludo sin articulación. La regla: **no se le
hardcodea movimiento a los dedos clip por clip; la capa de manos del motor lo hace sola** y el autor del clip
solo decide la intención (qué forma, cuándo, qué gesto). No significa moverse todo el tiempo: una mano en reposo
se mueve poco, pero nunca igual ni congelada.

**Qué hace el motor solo** (`motor.hand_channels`, `motor.hand_follow`; las usan `c.hand`, `c.secondary()` y
`Performance`, así que todo clip y toda escena las reciben):
- **Cascada**: cada dedo se mueve en su propio reloj. Al abrir va primero el índice, al cerrar los dedos de afuera;
  la falange de la punta llega después de su base y el pulgar tiene su tiempo (`LAG_OPEN`, `LAG_CLOSE`). Cada
  transición sortea un desfase distinto (0-0.8 cuadros), así dos repeticiones no son iguales.
- **Resorte con rebasamiento**: cada dedo sigue su curva con un resorte propio (`FINGER_SPRING`: el índice rápido,
  el anular y el pulgar más lentos, la punta más lenta que la base): llegan un poco tarde, se pasan un poco y
  se asientan.
- **Sin chasquidos**: dos formas distintas a menos de 4 cuadros (`MIN_GAP`) se separan (la segunda se mueve hacia
  adelante, nunca antes).
- **Manos relajadas nunca idénticas**: cada forma suelta (`LOOSE`: relajada, suave, abierta, abierta de par en par)
  recibe un desplazamiento aleatorio por llave, un gradiente de curvatura (índice el más recto, anular el más
  cerrado) y una deriva lenta y asíncrona por dedo y por mano (semilla = `c.life(seed=…)`). Las formas
  exactas (`tap`, `grip`, `hold_flat`, `pinch`, `point`, `count*`) casi no varían: un toque o una palma que carga
  un objeto necesitan sus ángulos.
- **Arrastre y seguimiento** (`hand_follow`, dentro de `c.secondary()`): la muñeca se queda atrás del antebrazo y
  rebasa al frenar (resorte sobre el ángulo del brazo); los dedos se arrastran con la velocidad del brazo (las
  puntas se estiran un poco y el abanico se abre) y se asientan después. Una mano que ningún clip dibujó recibe una
  mano relajada viva (`c.life(hands=…)` ya no escribe el mismo `curl` en todos los dedos).
- **Límites anatómicos** (`CURL_LIMITS`, `FAN_LIMITS`, `THUMB_OUT_LIMITS`): sin hiperextensión, sin dedos cruzados,
  el pulgar fuera de la palma; se aplican al final sobre todo lo que se haya sumado.
- **Mano y puño** (`cuff_pass.py`, ver abajo): donde la muñeca doblada mete la palma o el pulgar detrás del puño de
  la manga, se estira la mano unos milímetros y, si no basta, la muñeca se dobla menos (se conserva el giro de la
  palma).

**Segunda pasada (la mano en reposo, la que más se ve)**: la forma `relaxed` ya no se enrosca sobre la pose de
reposo (que de por sí es una curva suave de ~55°: sumar +44° daba un guante de dos lóbulos). Ahora parte de ella
y la abre un poco: gradiente índice → anular (−6 / +4 / +14° en la base), **abanico de 12-15°** (huecos entre los
dedos) y el pulgar recogido junto al índice (`thumb_out` −20°; `THUMB_OUT_LIMITS` baja a −30°). Encima, el motor
añade solo, en toda forma suelta:
- **Carácter por mano** (`pers`): cada mano (semilla distinta por lado y por clip) lleva su propio desplazamiento de
  curvatura por dedo, de pulgar y de abanico (±7° / ±8° / ±2°), así izquierda y derecha nunca coinciden. Pesa
  según lo suelta que sea la forma (`pw`): reposo 1, puño ~0.6, formas exactas 0.
- **Cambios de dedo** (`finger_shifts`): cada dedo, cada 2-4 s, se acomoda en otra curvatura (±14°), la sostiene y
  regresa; más una deriva de ±5° y el abanico que respira. Visible pero calmado.
- **Esfuerzo del puño**: `fist` y formas intermedias se aprietan y aflojan lento (`eff`, ~±4°).
- **Muñeca viva** (`hand_follow`): una mano libre se mece con la respiración (`chest.rx`) y el cambio de peso
  (`hips.ry`) más un ruido lento de ±3° en flexión, lado, giro y torsión, distinto por lado.
- **Formas exactas de verdad**: una forma con `_loose` ≤ 0.05 (`exact(...)` en las escenas, la yema que toca la
  barbilla) no recibe deriva, cambio de dedo ni arrastre (`free`): un dedo que debe llegar a la piel llega.
- `c.hand_flutter(lado, fuerza, cuándo)` (`motor.hand_flutter`): temblor nervioso, cada dedo con su ritmo
  (3-6 cuadros, ~3°). Lo usan `scared` y `shiver`.
- Forma nueva `palm_up` (palma abierta con dedos relajados, curvos y algo separados): `shrug`; en `yawn_stretch`
  el estirón abre `spread` (no puño) y baja a `palm_up`.
Cómo revisarlo: ráfaga de 10 cuadros en 2 s de la mano de `Idle` y de otro clip relajado (los dedos deben
cambiar visiblemente, izquierda ≠ derecha, huecos entre dedos, pulgar junto al índice).

**Qué debe seguir haciendo el autor del clip**:
- Poner llaves de forma de mano (`c.hand`) con intención y en el momento del gesto; no repetir la misma forma
  en todos los gestos (`spread` no es "mano abierta" en general: `open`, `soft`, `stop`, `claw`, `fist`, `grip`).
  Entre forma y forma, al menos 4 cuadros; para un golpe pon la llave "antes" 2-3 cuadros antes del tiempo.
- Gestos con articulación propia: `c.finger_roll(lado, onda, amp, lag)` (cascada rodante: un saludo, un aleteo,
  dedos que se agitan), `c.hand_beat(lado, [cuadros], fuerza)` (la mano se abre y se separa en un énfasis),
  `motor.wave_drive(n, f0, f1, period, seed, phase)` (onda de saludo con periodo y tamaño de cada vaivén
  distintos, entra en ~5 cuadros y muere en ~8). Un saludo real mueve todo el brazo: codo que guía
  (`c.elbow(s, k * delay(w, -2))`), antebrazo que se mece, muñeca en lado y flexión a un cuarto de vuelta de fase
  (elipse), palma que gira unos grados por vaivén y dedos en cascada tras la muñeca (ver `wave()`).
- Pulgar: oposición natural en las formas (`thumb_out`); nunca dejarlo dentro de la palma.
- Una mano de reposo (no tocada por el clip) basta con `c.life(...)`: no escribir `c.curl` igual en todos los
  dedos; un `c.curl` suma encima y es un movimiento de todos a la vez (úsalo solo como pulso corto).
- En clips con contactos (`contacts`/`supports`), la forma de mano del toque va como forma exacta (`tap`, `hold_flat`).
- Después de hornear: `python scripts/ia3d/…` métricas, `check_props.py` en clips de contacto y
  `check_sleeves.py --action <clips>` (columnas `x_thumb/x_fingers/x_palm` = mano detrás del puño; en reposo
  quedan ~4.5 mm y hasta ~9 mm con la palma muy girada).

**Pasada de puño** (`anim/cuff_pass.py`): corre sobre un .blend con materiales (look5 o look7; necesita las caras
`Hoodie`/`Skin` de `check_sleeves.py`), lee las acciones ya horneadas de otro archivo y escribe las corregidas en un
tercero que se une con `make_actions.py --merge`. Por cuadro prueba, de lo más barato a lo más fuerte, estirar la
mano 4-12 mm a lo largo del antebrazo y doblar la muñeca menos (`TRIES`) hasta que lo que sobresalga del puño sea
≤ 10 mm; suaviza el cambio (±4 cuadros + difuminado) y deja intactos los cuadros de contacto. Estirar el antebrazo
(`.sy`) no sirve para esto: el puño de la manga va en el extremo del antebrazo y se estira con él.

**Cadena**: `face3 → make_actions (--only por grupos) → cuff_pass (sobre look5) → make_actions --merge → morfi_ia_anim7.blend`
(anim6 = primera pasada de manos; anim7 = segunda, con la mano en reposo viva) y las escenas con `make_scenes.py` → `morfi_ia_scenes3.blend`.

## 4. Verificación (obligatoria antes de publicar)

Los scripts de Blender se corren como el resto: `$B -b work/ia3d/morfi_ia_look7.blend --python scripts/ia3d/<script>.py -- <args>`.

| script | qué mide |
|---|---|
| `check_sleeves.py --action all --step 3 [--actions-from work/ia3d/morfi_ia_scenes3.blend]` | la mano y el antebrazo contra la manga y el puño (mm que sobresale / atraviesa, por mano y cuadro; `--raw` cuenta también puntos en el aire junto a la abertura) |
| `check_props.py --action Tablet,Calculator` | traslape de manos y cuerpo con los objetos (≤ 1 mm), cada toque (≤ 1.5 mm), apoyo de la palma, manos y mangas contra cabeza y torso |
| `check_clearance.py --action X` | distancia con signo de cada mano a la cabeza y al torso, cuadro por cuadro |
| `check_feet.py [--actions A,B]` | pies que se hunden o resbalan al caminar |
| `reach_map.py --side L --orient palm_up --out …` | mapa de posiciones alcanzables sin estirar ni chocar |
| `pose_probe.py --poses …` | poses estáticas del motor con su reporte de contactos |
| `preview_anim.py --action A,B,… --out carpeta` | vista previa en Eevee (cuadros + mp4) de varias acciones en una sola sesión |

Estado al 18-oct-2026 (`morfi_ia_anim7.blend` -> `morfi_ia_look7.blend`, 40 clips publicados: 11 básicos, 8 emociones, 7 de trabajo, 14 movimientos):

- **Contactos** (13 clips con contacto, todos ok): Think 0.3 mm, Laugh 0.5, Surprised 0.6, Facepalm 0.3,
  Blow_Kiss 0.0; Tablet y Calculator: traslape 0.6 mm, presión 0.2, apoyo 0.6.
- **`check_props`**: pasan 38 de 41 (medido antes de quitar Scratch_Head). Think y Laugh salen marcados solo donde una mano descansa en el cuerpo (Think:
  falso positivo probable por el forro interior de la sudadera abierta, que `check_props` cuenta como torso;
  `check_clearance` da +1.7 cm; Laugh: la palma en la panza es a propósito). `Scratch_Head` tenía un problema
  real de manga y se quitó del conjunto publicado.
- **Mano contra cabeza** fuera de los toques: ≥ 0.42 cm. Las lecturas de −5.0 cm contra el torso en
  `check_clearance` (Tablet, Calculator, Dance_2, Blow_Kiss) son errores de signo; `check_props` da +0.2 a +3.7 cm.
- **Pies** (`check_feet`): se hunden como máximo 4.7 mm; los pies plantados resbalan < 0.5 mm por cuadro salvo donde
  es a propósito (Walk/Run/Sneak en el sitio, el pivote de Spin, el choque de rodillas de Scared/Shiver, el
  arrastre de Sad, el paso de Bow). Sus cifras de velocidad para `Run` y `Sneak` no valen: usa la de `Walk`.
- **Bucles**: el salto en el punto de unión ≤ 1.5× el mayor paso por cuadro.
- **Squash y stretch**: `head.sy` 0.89–1.11; columna, pecho y cadera dentro de ±3 %; estirón de brazo ≤ 1.13 con la
  mano contraescalada para que los dedos no se alarguen.
- **Alcance**: el tope por omisión es 1.08 (los clips que tocan la cara piden 1.10–1.12).
- Tablet y calculadora: índice a ≤ 0.1 mm de cada tecla o punto de la pantalla (IK) y la mano que teclea no toca la
  barbilla ni el pecho. Los toques al propio cuerpo toleran `BODY_TOL` 3 mm (piel blanda).
- Vistas previas de los clips y hojas de contacto: se revisaron todas a ojo (Eevee, tres cuartos frontal).

**Integración final de la ronda 2 (`anim7` → `look7`, `scenes3`, 18-oct-2026; `--step 3` en los 40 clips + 6 escenas).**
- `look7`: 65 511 vértices, 123 162 caras (122 874 triángulos y 288 cuadrados), 0 sin peso, 0 caras degeneradas, 0 giros de UV; muñecas con
  Copy Rotation + Limit Rotation; marcas `brows_fix`, `body_fix_orig`, `glasses_fix_orig`; `Glasses_Frame` y `Lens_L/R`; 40 clips.
- `check_sleeves`: cruces de pulgar, dedos y palma de la pared del puño y piel fuera de la manga = **0 mm** en los 46; mano fuera de la manga:
  `Blow_Kiss` (D) 10.0 mm, `Sneak` (I) 6.0, `Shiver` (I) 4.9, todos los demás (incluidas las 6 escenas) 0.0.
- `check_props` (paso 2): `Count_123`, `Point_Side`, `Present`, `Idea`, `Surprised` y `Thumbs_Up` pasan; `Tablet` y `Calculator` traslape 0.5-0.6 mm,
  presión 0.2, apoyo 0.5-0.6 (los −2.0 cm contra el torso son el error de signo conocido); `Think`, `Laugh`, `Facepalm` y
  `Blow_Kiss` salen `ok=False` solo donde la mano toca la cara o el cuerpo a propósito (mano-cabeza ≈ 0 cm).
- Cuello: tubo liso, sin dientes azules en Idle, `Look_Around` ni `Shake_No`; quedan unas pocas facetas pequeñas en la parte baja de la cabeza
  en giros fuertes (visibles desde abajo, junto al borde de la capucha).

**Limitaciones conocidas.**
- `Scratch_Head` no se publica: con brazos de 20 cm no alcanza la parte alta de la cabeza y no se leía como
  rascarse (la función sigue en `actions_moves.py`, sin registrar).
- Los toques a la cara caen en la mandíbula o debajo de la cara, porque el frente de la cara está a más de 1.12 del
  largo del brazo. De frente, `Facepalm` se lee como "la cabeza descansa en la mano".
- La pasada de cuerpo cambia visiblemente algunas poses: manos que estaban dentro del borde de la cabeza quedan más
  abajo o más abiertas (cuadros corregidos: Shiver 160, Wave_Both 136, Dance_2 100; el punto de disco de Dance_2 va
  ahora hacia afuera y abajo, no arriba).
- `check_feet.py` y `check_props.py` (ver arriba) tienen esas dos imprecisiones conocidas.

## 5. Acciones disponibles (40)

Cada clip tiene etiqueta y grupo en `anim/catalog.py` (`CATALOG`, función `entry(nombre)`; un clip sin entrada es un
error): `export_face_anims.py` los escribe en `morfi_live_anims.json` y el visor arma sus botones con ellos.

| Grupo | Clips (etiqueta) |
|---|---|
| `actions` (11) | `Idle` (Reposo), `Wave` (Saludar), `Talk` (Hablar), `Nod_Yes` (Sí), `Shake_No` (No), `Look_Around` (Curioso), `Present` (Presentar), `Jump_Happy` (¡Feliz!), `Walk` (Caminar), `Run` (Correr), `Dance` (Bailar) |
| `emotions` (8) | `Laugh` (Reír), `Surprised` (Sorpresa), `Sad` (Triste), `Angry` (Enojado), `Scared` (Miedo), `Calm` (Tranquilo), `Celebrate` (Festejar), `Shrug` (No sé) |
| `work` (7) | `Tablet` (Tablet (tutorial): toca tres puntos de la pantalla y voltea a la cámara), `Calculator` (Calculadora: teclea cinco teclas y pulgar arriba), `Count_123` (Contar 1-2-3), `Point_Side` (Señalar), `Thumbs_Up` (Pulgar arriba), `Idea` (¡Idea!), `Think` (Pensar) |
| `moves` (14, `anim/actions_moves.py`) | `Spin` (Giro con brinco), `Hop_Steps` (Saltitos), `Dance_2` (Baile con brazos, bucle), `Bow` (Reverencia), `Yawn_Stretch` (Bostezo y estirón), `Victory` (¡Vamos!), `Wave_Both` (Saludo a dos manos), `Peek` (Asomarse), `Shiver` (Tiritar de frío), `Sneak` (De puntitas), `Sleepy` (Cabeceo de sueño), `Tap_Foot` (Impaciente), `Facepalm` (¡Ay, no!), `Blow_Kiss` (Mandar un beso) |

Los clips están en `actions.py` (básicos), `actions_social.py`, `actions_expressive.py`, `actions_props.py` y
`actions_moves.py`; todos suben a `ACTIONS` (`actions.py`). Los bucles son `Idle`, `Walk`, `Run`, `Dance`,
`Dance_2`, `Sneak`; `Walk`, `Run` y `Sneak` avanzan en el sitio. Cada clip termina cerca del reposo: el visor
vuelve a `Idle` con una mezcla de 0.35 s que no se nota. `Victory` es el clip del gesto `fist` de las frases con voz.

## 6. En el visor web

El visor ("Morfi en vivo") tiene su propio documento: [laboratorio.md](laboratorio.md) (paneles, parámetros de URL,
archivos publicados, cómo publicar). La API, en corto:

```js
morfi.play('Calculator')                // cualquier clip de morfi.actions
morfi.expression('surprised')           // expresión de cara encima del cuerpo ('neutral' la quita)
morfi.speak('Toca aquí para cobrar')    // solo texto, sin audio
morfi.say('hola')                       // frase con la voz real y la boca sincronizada con el audio
await morfi.scene('Scene_Idea')         // una escena completa con voz y cámara de cine
morfi.stop()
iframe.contentWindow.postMessage({ type: 'say', key: 'gracias' }, '*')
// tipos de mensaje: play (name), speak (text), say (key, voice?), expression (name), scene (name), stop
window.morfiStyle.outline(false)        // el contorno; window.morfiStyle.fx(false) apaga los efectos de movimiento
```

El skinning del visor es de cuaterniones duales **con escala por hueso** (`web/src/dqskin.ts`): separa la parte
rígida y la escala de cada hueso, como el "Preserve Volume" de Blender, así el estirón de los brazos (`.sy`) se ve
igual en la web (error medio < 0.2 mm contra Blender con las poses de prueba).

## 7. Contactos finales y brazo estirado

Orden de `make_actions.py` por clip (`bake_one` y luego `main`):

1. **Bake** de los canales a huesos (`rigmap.bake`), con `contacts.set_max_reach(clip.max_reach)`.
2. **IK:** `clamp_reach` → `resolve_body` (salvo clips con objeto en la mano) → `solve` (presiones, apoyos de palma,
   toques al propio cuerpo) → `clamp_reach`, con `hands_keep_size` (las manos no heredan el estirón del IK).
3. **Brazos a FK** con `rebake_arms`: el brazo evaluado de cada cuadro (IK y contactos incluidos) se pasa a FK y se
   anima cada hueso para que su eje caiga exactamente donde estaba (mismo codo, misma muñeca), **estirado con su
   volumen** (más largo y más delgado); la mano recupera su tamaño. Estadística por brazo: error de muñeca (mm),
   de dirección (grados), estirón máximo y cizalla que queda.
4. **Giro de la manga** (`clear_sleeves_fk`): cuando una mano descansa en la cabeza, el brazo gira sobre la línea
   hombro-muñeca (el codo sale, la muñeca queda quieta y la mano conserva su orientación). Se prueban 10 ángulos
   (±6° a ±40°) en el primer cuadro, el de en medio y el último del toque; gana el que más despega la manga; se
   mantiene durante el toque y entra y sale con su rampa.
5. **Refinar contactos** (`refine_contacts_fk`, tolerancia 0.6 mm): vuelve a cerrar los toques de la cara y los
   apoyos de palma sobre el brazo FK final; la conversión a FK más el límite de muñeca los había abierto 2-5 mm.
6. **Pasada de cuerpo** (`resolve_body_fk`): si una mano o manga entra en la cabeza o el torso, todo el brazo gira
   sobre el hombro hasta quedar a 4 mm (`FK_MARGIN`); la corrección entra y sale en 7 cuadros (`FK_FADE`), da la
   vuelta en los bucles y se salta los cuadros que son de un contacto. Un clip con objeto en la mano no la lleva
   (`_skip`: giraría el brazo contra el objeto).
7. **Verificación** de contactos sobre la acción final (`contacts.verify`).

**Cómo llega a la cara un brazo de 20 cm** (la técnica, y por qué se ve bien):
- El clip pide `c.max_reach = 1.10`–`1.12` (el tope normal es 1.08) y un objetivo IK en la piel; el estirón es
  de caricatura, hasta 1.13 a lo largo del hueso y ~0.94 a lo ancho (volumen conservado), con la mano
  contraescalada: **no se alargan los dedos ni se ve un brazo de chicle**.
- Aun así el frente de la cara queda más allá de 1.12 veces el brazo: los toques caen en la mandíbula o debajo de
  la cara (ver Limitaciones). Para tocar algo más arriba hay que inclinar la cabeza hacia la mano (la cabeza baja
  como máximo ~7° al mirar, ver `look_at`).
- Los demás clips no estiran más allá de ~1.10 para no pasar de la caricatura.

## 8. Escenas

Una escena es una toma continua con varias líneas de voz (voz oficial Super VM), el cuerpo completo actuando y los
cortes de cámara pensados para el visor. Código: `anim/scenes.py` (Python puro, sin Blender: el exportador
reconstruye de él las curvas de cara) y `make_scenes.py`.

**Escenas** (`SCENES` en `scenes.py`; título y `solo` salen de `voice/scenes.json`):

| clave | título | `solo` | acción | duración |
|---|---|---|---|---|
| `presentacion` | ¡Hola, soy Morfi! | no | `Scene_Presentacion` | 349 cuadros (11.6 s) |
| `calculadora` | ¿Dónde quedó mi calculadora? | sí | `Scene_Calculadora` | 428 (14.3 s) |
| `idea` | ¡Ya sé! | sí | `Scene_Idea` | 359 (12.0 s) |
| `ventas` | Qué día de ventas | no | `Scene_Ventas` | 422 (14.1 s) |
| `susto` | ¿Qué fue eso? | sí | `Scene_Susto` | 346 (11.5 s) |
| `sueno` | Cinco minutitos | sí | `Scene_Sueno` | 386 (12.9 s) |

`solo` = habla solito (no le habla a la cámara; el visor lo ve de lado). Se suma `POS_Video` (el video del punto
de venta, tal cual del proyecto del video; `export_scenes.py` convierte su cámara en cortes gruesos).

**`PLAN`** (`scenes.py`): por escena, `starts` (segundo en que entra cada línea), `tail` (silencio tras la
última palabra), `sfx` (`[["bell", 0.55], …]`; tipos: `bell`, `bell2`, `chime`, `pop`, sintetizados en
`make_scenes.py`) y `cams` (`[[t, "wide"|"medium"|"close"|"face"], …]`, los cortes de cámara del visor). Las
líneas son las de `voice/scenes.json` con clave `sc_<escena>_<n>`, en orden. Funciones: `timeline(key)` (líneas
sobre la línea de tiempo, con cada palabra ajustada a los cuadros con voz de su propio audio), `build(key, tl)`
(el `Performance`), `finish(p)` (el `Clip`), `meta(tl)` (lo que usan la exportación y el reproductor).

**Pasos**:

```bash
B=/d/tools/bl.sh
# 0. la voz de las líneas (ElevenLabs; la llave solo en el comando) -> web/public/voice/supervm/sc_*.mp3
XI_KEY=<llave> python voice/gen.py lines voice/scenes.json --voice supervm
# 1. el audio de cada escena (Python + ffmpeg): líneas con sus pausas + efectos, nivelado -> web/public/voice/scenes/<clave>.mp3 y .json
python scripts/ia3d/make_scenes.py audio [--only susto,sueno]
# 2. hornear (un Blender por escena puede correr a la vez); acción Scene_<Clave> en el rig
$B -b work/ia3d/morfi_ia_face3.blend --python scripts/ia3d/make_scenes.py -- bake --only susto --out <dir>/scene_susto.blend [--fast]
# 3. juntar todas en un archivo
$B -b work/ia3d/morfi_ia_face3.blend --python scripts/ia3d/make_scenes.py -- merge --parts <dir>/scene_*.blend --out work/ia3d/morfi_ia_scenes.blend
# 4. verificar y ver vistas previas con audio (look3 tiene los materiales; las acciones se agregan)
$B -b work/ia3d/morfi_ia_scenes.blend --python scripts/ia3d/make_scenes.py -- verify [--only susto]
$B -b work/ia3d/morfi_ia_look3.blend --python scripts/ia3d/make_scenes.py -- preview --src work/ia3d/morfi_ia_scenes.blend --only susto --out <dir>/preview [--res 50 --step 1]
# 5. exportar al visor (ver §1: export_scenes.py sobre look7, escenas de scenes3) y sync-live
```

`--fast` hornea sin los solucionadores de contactos (revisar poses). `merge` se niega a unir una escena cuya
cantidad de cuadros no coincide con su línea de tiempo (hay que hornearla de nuevo) y refresca los cortes de
cámara. `make_scenes.py` también tiene `sketch` (hornea en memoria y renderiza, sin guardar), `faces` y `dump`.
La estructura de `bake_scene`: bake → tope de alcance → manos fuera del cuerpo → `smooth_ik` → toques
(`contacts.solve`) → `smooth_touches` → manos fuera del cuerpo otra vez → tope → `smooth_ik` → `smooth_touches` ancho
(`REST_WIN` 15 cuadros: una sola posición de reposo por toque) → `rest_on_skin` (cada cuadro de toque se mueve solo
por la normal de la piel hasta quedar a ±1 mm) → `smooth_ik` → `rebake_arms` → objeto en la mano (`hold_prop`, al
final) → verificación. **No** corre todavía las pasadas FK de `make_actions.py` (giro de manga, refinar, pasada de
cuerpo): es una mejora pendiente (`make_scenes.py` podría llamarlas tras `rebake_arms`). La corrección de escala de
`rigmap.bake` sí aplica a las escenas.

Cada acción `Scene_*` lleva dos propiedades JSON: `scene` (título, `solo`, `audio`, cortes de cámara, líneas) y
`contacts`. Al exportar, el visor recibe `models/morfi_live_scenes.json` y `.glb` (ver [laboratorio.md](laboratorio.md) §5-6).
Vistas previas de una escena: `make_scenes.py preview` pone la cámara en sus cortes (`wide` z 0.55 a 3.5 m,
`medium` 0.58 a 2.6, `close` 0.66 a 1.95, `face` 0.72 a 1.4, lente de 50 mm) y arma un mp4 con el audio.

## 9. Para el skill de tutoriales (pendiente, no creado)

Lo que el skill necesitará, ya disponible: acciones parametrizables por código, toques exactos sobre puntos de una
pantalla (`contacts`), expresiones y habla por texto, verificación automática y render (`render_showcase.py`).
Para tutoriales sobre una pantalla grande del POS, el siguiente paso es una pantalla fija en la escena (un objeto
más con su propio hueso) y una acción "señalar punto (x, y) de la pantalla" que reutilice `contacts` sin tocarla.

# Motor de animación de Morfi

Base para producir animaciones nuevas de Morfi (y, más adelante, el skill que armará videos tutoriales de
punto de venta). Todo es código: una acción es una función de Python que llena canales cuadro por cuadro;
el motor la hornea al rig, resuelve los contactos con los objetos, impide que el cuerpo se atraviese y lo
verifica. Nada se ajusta a mano en Blender.

Archivos: `scripts/ia3d/anim/` (`clip.py`, `motor.py`, `contacts.py`, `rigmap.py`, `curves.py`, acciones en
`actions*.py`) y los scripts de verificación en `scripts/ia3d/`.

## 1. Cadena de construcción

```bash
B=/d/tools/bl.sh     # Blender 4.5 portátil en D:, temporales en D:
# (pasos 1-3 de docs/ia3d.md §7: malla, regiones, rig del cuerpo -> work/ia3d/morfi_ia_rig_nohands.blend)
$B -b work/ia3d/morfi_ia_rig_nohands.blend --python scripts/ia3d/build_hands.py -- --out work/ia3d/morfi_ia_rig_hands.blend
$B -b work/ia3d/morfi_ia_rig_hands.blend --python scripts/ia3d/build_controls.py -- --out work/ia3d/morfi_ia_rig_full.blend
$B -b work/ia3d/morfi_ia_rig_full.blend --python scripts/ia3d/build_face.py -- --features work/ia3d/face/face_features.json --out work/ia3d/morfi_ia_face2.blend
$B -b work/ia3d/morfi_ia_face2.blend --python scripts/ia3d/make_actions.py -- --out work/ia3d/morfi_ia_anim3.blend
$B -b work/ia3d/morfi_ia_anim3.blend --python scripts/ia3d/build_look.py -- --regions work/ia3d/regions/regions.npz --face work/ia3d/face --out work/ia3d/morfi_ia_look2.blend
# visor web
$B -b work/ia3d/morfi_ia_look2.blend --python scripts/ia3d/export_web.py -- --out work/ia3d/web/morfi_live.glb --face-json work/ia3d/web/morfi_live_face.json
python scripts/ia3d/export_face_anims.py --out work/ia3d/web/morfi_live_anims.json
cd web && npm run sync-live && npm run build && npm run test:live
```

`make_actions.py --only Tablet,Calculator` re-hornea solo esas acciones (y conserva las demás del archivo).
`build_controls.py --props-only` reconstruye solo la tablet y la calculadora.

## 2. El esqueleto

- **Cuerpo**: `root`, `hips`, `spine`, `chest`, `neck`, `head`, `hood`, `pixels` (los cubos), hombros, brazos,
  piernas con IK (`foot_ik.<L|R>`, `knee_pole.<L|R>`). Morfi mira hacia −Y; su izquierda es +X; mide 1.14 m
  con los cubos.
- **Manos** (`build_hands.py`): pulgar y tres dedos (índice, medio, anular), tres falanges cada uno
  (`index.01-.03.<s>`, …, `thumb.<s>`, `thumb.02/.03.<s>`). Malla propia, pesos suaves por falange.
- **Controles** (`build_controls.py`):
  - IK de brazo (`hand_ik.<s>`, `elbow_pole.<s>`), apagado salvo cuando una acción lo pide (canal `ik.<s>`).
    El IK de Blender estira sin límite; el motor **topa el alcance a 1.08× el largo del brazo**
    (`contacts.MAX_REACH`): estiramiento de caricatura, nunca brazo de chicle.
  - Objetos: hueso `prop` frente al pecho, con `prop_tablet` y `prop_calc` (escala 0 = oculto). Los objetivos de
    las manos cuelgan de `prop`, así una mano que sostiene algo lo sigue a donde vaya.
- **Cara** (`build_face.py`, propiedades del rig de −1 a 1 o de 0 a 1): `blink_L/R`, `gaze_x/y`, `mouth_open`,
  `smile` (−1 = boca triste), `mouth_round`, `mouth_side`, `teeth`, `brow_L/R` (sube/baja, recorrido 1.6 cm),
  `brow_in_L/R` (extremo interior: +1 preocupado, −1 enojado), `squint`, `lid_drop`, `lid_angle`
  (+1 enojado, −1 triste), `pupil` (−1 miedo, +1 ternura), `eye_calm` (ojos cerrados tranquilos).

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
| `<hueso>.s` / `.sy` | escala uniforme (objetos: 0/1) / estirar con volumen |
| `ik.<L/R>` | 0..1, IK del brazo |
| `prop.<cara>` | propiedad de la cara (`prop.smile`…); `prop.rx`, `prop.lx`… son del hueso `prop` |

Cada acción guarda **todos** los huesos y gestos (en reposo si no los usa): las acciones se encadenan sin saltos.

### Ayudas del motor (`clip.py`, `motor.py`)

- Cuerpo: `arm_raise`, `arm_fwd`, `arm_swing`, `elbow`, `forearm_lift`, `forearm_in`, `palm`, `wrist`, `shrug`,
  `foot`, `life`, `secondary`, `plant_feet`.
- Manos (`c.hand(lado, [(cuadro, forma)])`): `rest`, `relaxed`, `fist`, `open`, `stop`, `point`, `tap`, `count1`…`count4`,
  `thumbs_up`, `grip`, `pinch`, `hold_flat`, `claw`, o un diccionario propio de ángulos por falange.
- Cara (`c.expr([(cuadro, expresión[, peso])])`): `neutral`, `happy`, `joy`, `laugh`, `sad`, `angry`, `scared`,
  `surprised`, `calm`, `thinking`, `skeptical`, `smug`, `love`, `wink`, `determined`, `confused`, `shy`, `sleepy`.
  Los canales `c.prop(...)` se suman encima (habla, miradas).
- Alcanzar: `c.reach(lado, [(cuadro, punto_muñeca | None[, peso])])` con orientación
  `orient_keys(lado, [(cuadro, dirección_dedos, dirección_palma)], prop_rot=...)` → `c.reach_rot(...)`.
  Con un objeto girado, los puntos se convierten con `prop_space()` / `prop_world()`.
- Objetos: `c.show("prop_tablet", [(0, 1)])`, `c.place_prop(loc=[...], rot=[...])`.

### Contactos (`contacts.py`)

- `clip.supports = [{"side": "L", "prop": "Prop_Calc", "frames": (a, b)}]`: el objeto descansa en la palma; el motor
  mueve la mano hasta que toca la cara trasera del objeto, sin atravesarla (también cuenta el puño de la manga).
- `clip.contacts = [{"side": "R", "tip": "index.03.R", "target": "Prop_Calc_Key_21" | "Prop_Tablet_Screen",
  "local": (x, z) | None, "frames": (f0, f1), "ramp": 6}]`: el índice toca exactamente ese punto de f0 a f1,
  baja en línea recta desde 2 cm y vuelve a subir; entre toques flota sobre la superficie.
- `resolve_body()`: en todas las acciones con IK, una mano que entra en la cabeza o el torso se empuja hacia afuera
  por la normal de la superficie hasta apenas tocar (un puño en la barbilla, una palma en la panza).
- `clamp_reach()`: el tope de alcance.

Ver `anim/actions_props.py` (`Tablet`, `Calculator`): son la plantilla para acciones con objetos.

## 4. Verificación (obligatoria antes de publicar)

| script | qué mide |
|---|---|
| `check_props.py --action Tablet,Calculator` | traslape de manos y cuerpo con los objetos (≤ 1 mm), cada toque (≤ 1.5 mm), apoyo de la palma, manos y mangas contra cabeza y torso |
| `check_clearance.py --action X` | distancia con signo de cada mano a la cabeza y al torso, cuadro por cuadro |
| `check_feet.py` | pies que se hunden o resbalan al caminar |
| `reach_map.py --side L --orient palm_up` | mapa de posiciones alcanzables sin estirar ni chocar |
| `pose_probe.py --poses …` | poses estáticas del motor con su reporte de contactos |
| `preview_anim.py --action A,B,…` | vista previa en Eevee (cuadros + mp4) de varias acciones en una sola sesión |

Estado al 16-oct-2026: las 26 acciones respetan el tope de alcance. Tablet y calculadora: índice a ≤ 0.3 mm de
cada tecla o punto de la pantalla, palma a ≤ 0.3 mm del objeto, sin traslapes. La manga roza la chamarra
(tela contra tela) al llevar el brazo al frente; no se ve de frente ni de tres cuartos.

## 5. Acciones disponibles

Básicas: `Idle`, `Wave`, `Talk`, `Nod_Yes`, `Shake_No`, `Look_Around`, `Present`, `Jump_Happy`, `Walk`, `Run`, `Dance`.
Emociones: `Laugh`, `Surprised`, `Sad`, `Angry`, `Scared`, `Calm`, `Celebrate`, `Shrug`.
Gestos y trabajo: `Count_123`, `Thumbs_Up`, `Point_Side`, `Idea`, `Think`, `Tablet` (tutorial: toca tres puntos de la
pantalla y voltea a la cámara), `Calculator` (teclea cinco teclas y pulgar arriba).

## 6. En el visor web

```js
morfi.play('Calculator')          // cualquier acción de la lista
morfi.expression('surprised')     // expresión de cara encima de lo que haga el cuerpo ('neutral' la quita)
morfi.speak('Toca aquí para cobrar')
iframe.contentWindow.postMessage({ type: 'expression', name: 'happy' }, '*')
```

## 7. Para el skill de tutoriales (pendiente, no creado)

Lo que el skill necesitará, ya disponible: acciones parametrizables por código, toques exactos sobre puntos de una
pantalla (`contacts`), expresiones y habla por texto, verificación automática y render (`render_showcase.py`).
Para tutoriales sobre una pantalla grande del POS, el siguiente paso es una pantalla fija en la escena (un objeto
más con su propio hueso) y una acción "señalar punto (x, y) de la pantalla" que reutilice `contacts` sin tocarla.

#!/bin/bash
# Fast face loop: draft build -> rig (per-shot poses) -> front render with the
# calibrated camera, then compare with scripts/face_landmarks.py.
#   scripts/iterate_face.sh <tag> [config.json]
cd "$(dirname "$0")/.." || exit 1
t=$1; cfgp=${2:-config/morfi.json}
mkdir -p work/fl
blender -b --python scripts/build_model.py -- --out "$PWD/work/fl/$t.blend" --quality draft --config "$cfgp" --tex-dir "$PWD/work/fl/tex_$t" > "work/fl/$t.build.log" 2>&1 || { echo BUILD_FAIL; exit 1; }
blender -b "work/fl/$t.blend" --python scripts/rig_model.py -- --out "$PWD/work/fl/${t}_rig.blend" > "work/fl/$t.rig.log" 2>&1 || { echo RIG_FAIL; exit 1; }
blender -b "work/fl/${t}_rig.blend" --python scripts/render_views.py -- --views front --out "work/fl/render_$t" --samples 24 --hide Laptop > "work/fl/$t.render.log" 2>&1 || { echo RENDER_FAIL; exit 1; }
python3 scripts/face_landmarks.py references/02_Morfi_frente.png "work/fl/render_$t/front.png"

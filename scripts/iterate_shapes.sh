#!/bin/bash
# Fast shape loop: draft build -> dense point cloud -> silhouette IoU per view
# with the calibrated cameras (no rendering). Textures go to work/fl so the
# master files are not touched.
#   scripts/iterate_shapes.sh <tag> [config.json]
cd "$(dirname "$0")/.." || exit 1
tag=$1; cfgp=${2:-config/morfi.json}
mkdir -p work/fl
blender -b --python scripts/build_model.py -- --out "$PWD/work/fl/$tag.blend" --quality draft --config "$cfgp" --tex-dir "$PWD/work/fl/tex_$tag" > "work/fl/$tag.build.log" 2>&1 || { echo BUILD_FAIL; exit 1; }
blender -b "work/fl/$tag.blend" --python scripts/dump_points.py -- --pose neutral --out "work/fl/$tag.npz" > "work/fl/$tag.dump.log" 2>&1 || { echo DUMP_FAIL; exit 1; }
python3 scripts/eval_silhouettes.py "work/fl/$tag.npz" "work/fl/ov_${tag}_"

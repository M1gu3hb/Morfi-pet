// Runs the Khronos glTF validator on every exported GLB and writes a JSON report.
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import validator from 'gltf-validator';
const here = dirname(fileURLToPath(import.meta.url));
const exp = join(here, '..', '..', 'exports');
const files = [];
for (const f of readdirSync(exp)) if (f.endsWith('.glb')) files.push(join(exp, f));
if (existsSync(join(exp, 'parts'))) for (const f of readdirSync(join(exp, 'parts'))) if (f.endsWith('.glb')) files.push(join(exp, 'parts', f));
const out = {};
let failed = false;
for (const f of files) {
  const r = await validator.validateBytes(new Uint8Array(readFileSync(f)), { maxIssues: 200 });
  const name = f.split('/exports/')[1];
  out[name] = {
    errors: r.issues.numErrors, warnings: r.issues.numWarnings, infos: r.issues.numInfos, hints: r.issues.numHints,
    info: { triangles: r.info?.totalTriangleCount, vertices: r.info?.totalVertexCount, materials: r.info?.materialCount,
            animations: r.info?.animationCount, extensionsUsed: r.info?.extensionsUsed },
    messages: r.issues.messages.filter((m) => m.severity <= 1).slice(0, 30).map((m) => `${['ERROR','WARNING'][m.severity]} ${m.code}: ${m.message} @ ${m.pointer ?? ''}`),
  };
  if (r.issues.numErrors) failed = true;
  console.log(`${name}: ${r.issues.numErrors} errors, ${r.issues.numWarnings} warnings, ${r.info?.totalTriangleCount} tris`);
}
writeFileSync(join(here, '..', '..', 'docs', 'gltf-validation.json'), JSON.stringify(out, null, 1));
process.exit(failed ? 1 : 0);

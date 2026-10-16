// Copy Monaco's AMD bundle into `public/monaco/vs` so the editor is served from
// this app instead of a CDN. Without this, `@monaco-editor/react` would fetch
// Monaco from jsDelivr and the Dev Studio would break offline.
//
// Runs automatically via the `predev` / `prebuild` npm scripts. The copy is
// skipped when it already matches the installed monaco-editor version.

import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const publicDir = resolve(here, "..", "public");
const monacoDir = join(publicDir, "monaco");
const target = join(monacoDir, "vs");
const marker = join(monacoDir, ".version");

let pkgPath;
try {
  pkgPath = require.resolve("monaco-editor/package.json");
} catch {
  console.error(
    "[monaco] `monaco-editor` is not installed. Run `npm install` in the repo root first."
  );
  process.exit(1);
}

const pkg = JSON.parse(await readFile(pkgPath, "utf8"));

try {
  const current = (await readFile(marker, "utf8")).trim();
  if (current === pkg.version) {
    console.log(`[monaco] assets already current (v${pkg.version})`);
    process.exit(0);
  }
} catch {
  // no marker yet — copy below
}

const source = join(dirname(pkgPath), "min", "vs");
await rm(monacoDir, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
await writeFile(marker, pkg.version);
console.log(`[monaco] copied v${pkg.version} -> public/monaco/vs`);

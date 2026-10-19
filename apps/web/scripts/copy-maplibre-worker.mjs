// Copies MapLibre's worker module (and the shared chunk it imports) from the installed package into
// public/vendor/maplibre so the app can self-host them at a stable same-origin URL.
// MapLibre 6 derives the worker URL from its own script URL, which is not a plain http(s) URL inside the
// Next.js production bundle; without this copy the map never finishes loading. Runs as `prebuild`.
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const source = join(root, "node_modules", "maplibre-gl", "dist");
const target = join(root, "public", "vendor", "maplibre");
const files = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];

mkdirSync(target, { recursive: true });
for (const file of files) {
  const from = join(source, file);
  if (!existsSync(from)) {
    console.error(`copy-maplibre-worker: missing ${from}`);
    process.exit(1);
  }
  copyFileSync(from, join(target, file));
}
const version = JSON.parse(readFileSync(join(root, "node_modules", "maplibre-gl", "package.json"), "utf8")).version;
writeFileSync(join(target, "VERSION.txt"), `maplibre-gl ${version}\n`);
console.log(`copy-maplibre-worker: copied ${files.join(", ")} (maplibre-gl ${version})`);

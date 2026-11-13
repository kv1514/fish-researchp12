// Copy the web client into www/, the folder Capacitor bundles into the app.
// public/play is the single source: the website and the app ship the same files.
import { cpSync, rmSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', 'public', 'play');
const out = join(here, 'www');
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync(src, out, { recursive: true });
console.log(`copied ${src} -> ${out}`);

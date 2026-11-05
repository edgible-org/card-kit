// The newest version of each dependency in the major it is pinned to, as Renovate treats a card's
// images: a new major can change behaviour, so a person takes it. Run it in the image's directory.
import { execSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';

const pkg = JSON.parse(readFileSync('package.json', 'utf8'));
for (const [name, pinned] of Object.entries(pkg.dependencies ?? {})) {
  const major = pinned.replace(/^[^0-9]*/, '').split('.')[0];
  const found = JSON.parse(execSync(`npm view ${name}@^${major} version --json`).toString());
  const newest = Array.isArray(found) ? found[found.length - 1] : found;
  if (newest !== pinned) {
    console.log(`${name}: ${pinned} -> ${newest}`);
    pkg.dependencies[name] = newest;
  }
}
writeFileSync('package.json', JSON.stringify(pkg, null, 2) + '\n');

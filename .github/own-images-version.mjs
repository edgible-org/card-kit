// Raise an image's patch version in package.json and server.mjs, the two places mcp-image.yml
// checks agree. Run it in the image's directory. It prints the new version.
import { readFileSync, writeFileSync } from 'node:fs';

const pkg = JSON.parse(readFileSync('package.json', 'utf8'));
const [major, minor, patch] = pkg.version.split('.').map(Number);
const version = `${major}.${minor}.${patch + 1}`;
const server = readFileSync('server.mjs', 'utf8');
const line = new RegExp(`(version ?[:=] ')${pkg.version.replaceAll('.', '\\.')}'`, 'i');
if (!line.test(server)) throw new Error(`server.mjs does not say version ${pkg.version}`);
writeFileSync('server.mjs', server.replace(line, `$1${version}'`));
pkg.version = version;
writeFileSync('package.json', JSON.stringify(pkg, null, 2) + '\n');
console.log(version);

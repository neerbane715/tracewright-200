const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const root = path.resolve(__dirname, '..');
const dist = path.join(root, 'dist');
const uiDir = path.join(root, 'ui');
const webDir = path.join(root, 'web');

console.log('--- Checking & Installing Dependencies ---');
if (!fs.existsSync(path.join(uiDir, 'node_modules'))) {
  console.log('Installing dependencies for UI (Tracewright)...');
  execSync('npm install', { cwd: uiDir, stdio: 'inherit' });
}

if (!fs.existsSync(path.join(webDir, 'node_modules'))) {
  console.log('Installing dependencies for Web Console...');
  execSync('npm install', { cwd: webDir, stdio: 'inherit' });
}

console.log('--- Building UI (Tracewright) ---');
execSync('npm run build', { cwd: uiDir, stdio: 'inherit' });

console.log('--- Building Web Console (/console/) ---');
execSync('npm run build', {
  cwd: webDir,
  stdio: 'inherit',
  env: { ...process.env, VITE_BASE: '/console/' },
});

console.log('--- Merging into dist/ ---');
if (fs.existsSync(dist)) {
  fs.rmSync(dist, { recursive: true, force: true });
}
fs.mkdirSync(dist, { recursive: true });

// Copy ui/dist to dist/
fs.cpSync(path.join(uiDir, 'dist'), dist, { recursive: true });

// Copy web/dist to dist/console
const consoleDist = path.join(dist, 'console');
fs.mkdirSync(consoleDist, { recursive: true });
fs.cpSync(path.join(webDir, 'dist'), consoleDist, { recursive: true });

console.log('--- Cleaning up build-time node_modules to keep bundle size small ---');
try {
  fs.rmSync(path.join(uiDir, 'node_modules'), { recursive: true, force: true });
  fs.rmSync(path.join(webDir, 'node_modules'), { recursive: true, force: true });
} catch (e) {
  console.warn('Cleanup warning:', e.message);
}

console.log('Build complete:');
console.log(' - Tracewright walkthrough -> dist/');
console.log(' - Web Console & Wizard   -> dist/console/');

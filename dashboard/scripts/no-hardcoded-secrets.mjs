import fs from 'node:fs';
import path from 'node:path';

const FRONTEND_ROOT = path.resolve('src');
const TARGET_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx']);

const BLOCKED_PATTERNS = [
  { name: 'legacy token prefix', regex: /autobot_token_/i },
  { name: 'hardcoded API_TOKEN assignment', regex: /\bAPI_TOKEN\s*=\s*['"`][^'"`]+['"`]/ },
  { name: 'hardcoded bearer token', regex: /Bearer\s+[A-Za-z0-9_\-]{12,}/ },
  { name: 'raw IP endpoint on :8080', regex: /http:\/\/(?:\d{1,3}\.){3}\d{1,3}:8080/i },
  { name: 'placeholder IP endpoint on :8080', regex: /http:\/\/<ip>:8080/i },
];

const violations = [];

const walk = (dir) => {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name === 'node_modules' || entry.name === 'dist') continue;
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(fullPath);
      continue;
    }

    if (!TARGET_EXTENSIONS.has(path.extname(entry.name))) continue;

    const content = fs.readFileSync(fullPath, 'utf8');
    const lines = content.split(/\r?\n/);

    lines.forEach((line, idx) => {
      for (const pattern of BLOCKED_PATTERNS) {
        if (pattern.regex.test(line)) {
          violations.push({
            file: path.relative(process.cwd(), fullPath),
            line: idx + 1,
            rule: pattern.name,
            snippet: line.trim(),
          });
          break;
        }
      }
    });
  }
};

walk(FRONTEND_ROOT);

if (violations.length > 0) {
  console.error('❌ Hardcoded secret/endpoint policy violations detected:\n');
  for (const item of violations) {
    console.error(`- ${item.file}:${item.line} [${item.rule}]`);
    console.error(`  ${item.snippet}`);
  }
  process.exit(1);
}

console.log('✅ No hardcoded token/API endpoint patterns found in frontend source.');

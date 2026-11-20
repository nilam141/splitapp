/**
 * S6-Q-3: no floating point in money paths (CLAUDE.md rule 3). Complements the ESLint rule in .eslintrc.js.
 * Money code is everything under src/ except theme/, generated/ and the two documented non-money exceptions below.
 * Banned in code (comments and strings are stripped first): parseFloat, toFixed, toPrecision, Math.round/floor/ceil/
 * trunc, Number(<anything>), unary-plus coercion of text, and fractional numeric literals.
 */
import fs from 'fs';
import path from 'path';

const SRC = path.resolve(__dirname, '../src');
const SKIP_DIRS = new Set(['theme', 'generated', '__tests__']);
// Not money: an RFC 4122 random UUID nibble, and the Android API level read from Platform.Version.
const ALLOWED: Record<string, RegExp[]> = {
  'api/helpers.ts': [/Math\.floor\(Math\.random\(\)/],
  'notifications/useOsPermission.ts': [/Number\(Platform\.Version\)/],
};
// Fractional literals are layout values in UI files (font scale, list thresholds, opacity); they are checked everywhere else.
const LAYOUT_DIRS = /^(components|navigation|screens)\//;

const BANNED: [string, RegExp][] = [
  ['parseFloat', /\bparseFloat\s*\(/],
  ['toFixed/toPrecision', /\.(toFixed|toPrecision)\s*\(/],
  ['Math rounding', /\bMath\.(round|floor|ceil|trunc)\s*\(/],
  ['Number() coercion', /\bNumber\s*\(/],
  ['float literal', /(^|[^\w.'"`])\d+\.\d+([^\w.]|$)/],
];

function walk(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
    if (e.isDirectory()) {
      return SKIP_DIRS.has(e.name) ? [] : walk(path.join(dir, e.name));
    }
    return /\.(ts|tsx)$/.test(e.name) ? [path.join(dir, e.name)] : [];
  });
}

/** Removes block comments, line comments and string/template contents so only code is scanned. */
export function stripNonCode(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
    .replace(/'(?:[^'\\\n]|\\.)*'/g, "''")
    .replace(/"(?:[^"\\\n]|\\.)*"/g, '""')
    .replace(/`(?:[^`\\]|\\.)*`/g, m => '`' + m.replace(/[^\n]/g, ' ') + '`');
}

export function findFloatUse(rel: string, source: string): string[] {
  const hits: string[] = [];
  const allowed = ALLOWED[rel] ?? [];
  stripNonCode(source)
    .split('\n')
    .forEach((line, i) => {
      for (const [name, re] of BANNED) {
        if (name === 'float literal' && LAYOUT_DIRS.test(rel)) {
          continue;
        }
        if (re.test(line) && !allowed.some(a => a.test(line))) {
          hits.push(`${rel}:${i + 1}: ${name}: ${line.trim()}`);
        }
      }
    });
  return hits;
}

describe('no floating point in mobile money paths', () => {
  const files = walk(SRC);

  test('the scan sees the money code', () => {
    const rels = files.map(f => path.relative(SRC, f));
    expect(rels).toEqual(
      expect.arrayContaining([
        'money/format.ts',
        'money/parse.ts',
        'expenses/draft.ts',
      ]),
    );
  });

  test('src/ has no parseFloat, toFixed, Math rounding, Number() or float literal outside the allow-list', () => {
    const hits = files.flatMap(f =>
      findFloatUse(path.relative(SRC, f), fs.readFileSync(f, 'utf8')),
    );
    expect(hits).toEqual([]);
  });

  test('negative control: the scanner flags each banned construct', () => {
    for (const bad of [
      'const a = parseFloat(x);',
      'const a = x.toFixed(2);',
      'const a = Math.round(x * 100);',
      'const a = Number(text);',
      'const a = total * 0.5;',
    ]) {
      expect(findFloatUse('money/x.ts', bad)).not.toEqual([]);
    }
    expect(
      findFloatUse(
        'money/x.ts',
        '// parseFloat in a comment\nconst a = "1.50";',
      ),
    ).toEqual([]);
  });
});

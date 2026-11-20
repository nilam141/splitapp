/**
 * Guard for design_system.md rule 7.8: no color literals outside src/theme/ (generated API client excluded).
 * Colors come from theme tokens via useTheme() / useThemedStyles().
 */
import fs from 'fs';
import path from 'path';

const SRC = path.resolve(__dirname, '../src');
const ROOT_FILES = [path.resolve(__dirname, '../App.tsx')];
const SKIP_DIRS = new Set(['theme', 'generated', '__tests__']);

const NAMED =
  'white|black|red|green|blue|gray|grey|yellow|orange|purple|pink|brown|cyan|magenta|teal|navy|transparent';
const PATTERNS: [string, RegExp][] = [
  ['hex literal', /['"`]#[0-9a-fA-F]{3,8}['"`]/],
  ['rgb/rgba/hsl literal', /['"`][^'"`\n]*\b(?:rgba?|hsla?)\(/],
  [
    'named color',
    new RegExp(`[cC]olor['"]?\\s*[:=]\\s*\\{?\\s*['"\`](?:${NAMED})['"\`]`),
  ],
];

function walk(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
    if (e.isDirectory()) {
      return SKIP_DIRS.has(e.name) ? [] : walk(path.join(dir, e.name));
    }
    return /\.(ts|tsx)$/.test(e.name) ? [path.join(dir, e.name)] : [];
  });
}

export function findColorLiterals(source: string): string[] {
  const hits: string[] = [];
  source.split('\n').forEach((line, i) => {
    for (const [name, re] of PATTERNS) {
      if (re.test(line)) {
        hits.push(`line ${i + 1}: ${name}: ${line.trim()}`);
      }
    }
  });
  return hits;
}

describe('no color literals outside src/theme', () => {
  it('detects the literal shapes it guards against', () => {
    expect(findColorLiterals("a: { color: '#1b6e5a' }")).toHaveLength(1);
    expect(findColorLiterals("b: 'rgba(0,0,0,0.4)'")).toHaveLength(1);
    expect(findColorLiterals("c: { backgroundColor: 'white' }")).toHaveLength(
      1,
    );
    expect(findColorLiterals('d: { color: colors.textPrimary }')).toHaveLength(
      0,
    );
    expect(findColorLiterals('// see issue #123')).toHaveLength(0);
  });

  it('finds none in src/ or App.tsx', () => {
    const files = [...walk(SRC), ...ROOT_FILES];
    expect(files.length).toBeGreaterThan(20);
    const offenders = files.flatMap(f =>
      findColorLiterals(fs.readFileSync(f, 'utf8')).map(
        h => `${path.relative(path.resolve(__dirname, '..'), f)} ${h}`,
      ),
    );
    expect(offenders).toEqual([]);
  });
});

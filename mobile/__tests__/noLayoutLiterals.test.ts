/**
 * SUI-Q-1 guard for design_system.md section 5 and UI-DoD 1: no numeric layout literals outside src/theme/.
 * Spacing, radius, font size, line height, font weight and control sizes come from tokens
 * (spacing, radius, typography, layout, touchTarget).
 *
 * Allowed: 0, 1 (hairline), the string '100%', and anything that reads a token. Everything else is a violation.
 *
 * Files that violate today are frozen in __tests__/ui/layoutLiteralBaseline.json (file -> violation count).
 * The suite passes now and fails when (a) a file that is not listed gets a violation, (b) a listed file gets more
 * violations, or (c) a listed file has fewer violations than listed (including clean): lower or delete the entry
 * in the same change. That is how the baseline can only shrink.
 */
import fs from 'fs';
import path from 'path';
import baseline from './ui/layoutLiteralBaseline.json';

const MOBILE = path.resolve(__dirname, '..');
const SRC = path.join(MOBILE, 'src');
const ROOT_FILES = [path.join(MOBILE, 'App.tsx')];
const SKIP_DIRS = new Set(['theme', 'generated', '__tests__']);

const KEYS =
  'padding(?:Top|Bottom|Left|Right|Horizontal|Vertical|Start|End)?|' +
  'margin(?:Top|Bottom|Left|Right|Horizontal|Vertical|Start|End)?|' +
  'gap|rowGap|columnGap|' +
  'borderRadius|border(?:Top|Bottom)(?:Left|Right)Radius|' +
  'fontSize|lineHeight|fontWeight|' +
  '(?:(?:min|max)(?:Width|Height)|width|height)';
// `key: <value up to the next , or } or end of line>` (style objects, inline or multi-line).
const PROP = new RegExp(`\\b(${KEYS})\\s*:\\s*([^,}\\n]*)`, 'g');
// Number not part of an identifier or a member access (so spacing.lg, x2, a.5 are ignored).
const NUMBER = /(?<![\w.$])(\d+(?:\.\d+)?)(%?)(?![\w.])/g;

function isAllowedNumber(n: string, pct: string): boolean {
  if (pct === '%') {
    return n === '100';
  }
  return n === '0' || n === '1';
}

/** Returns one message per violating property on a line. Exported shape is kept small on purpose. */
export function findLayoutLiterals(source: string): string[] {
  const hits: string[] = [];
  source.split('\n').forEach((line, i) => {
    const code = line.replace(/\/\/.*$/, '');
    for (const m of code.matchAll(PROP)) {
      const key = m[1];
      const value = m[2].trim();
      let bad = false;
      if (key === 'fontWeight') {
        // any literal weight ('600', 'bold', 700) must come from typography
        bad = /^(['"`]|\d)/.test(value);
      } else {
        // strip quoted strings that are not numeric-with-unit so 'center' etc. never matter
        const quoted = value.replace(/['"`][A-Za-z-]+['"`]/g, '');
        for (const n of quoted.matchAll(NUMBER)) {
          if (!isAllowedNumber(n[1], n[2])) {
            bad = true;
          }
        }
      }
      if (bad) {
        hits.push(`line ${i + 1}: ${key}: ${line.trim()}`);
      }
    }
  });
  return hits;
}

function walk(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
    if (e.isDirectory()) {
      return SKIP_DIRS.has(e.name) ? [] : walk(path.join(dir, e.name));
    }
    return /\.(ts|tsx)$/.test(e.name) ? [path.join(dir, e.name)] : [];
  });
}

const rel = (f: string) => path.relative(MOBILE, f).split(path.sep).join('/');

export function scanAll(): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const f of [...walk(SRC), ...ROOT_FILES]) {
    const hits = findLayoutLiterals(fs.readFileSync(f, 'utf8'));
    if (hits.length > 0) {
      out[rel(f)] = hits;
    }
  }
  return out;
}

describe('layout literal detector (self-check)', () => {
  it.each([
    ['padding: 24', 'a: { padding: 24 }'],
    ['paddingHorizontal', 'a: { paddingHorizontal: 12, color: x }'],
    ['marginBottom', '  marginBottom: 6,'],
    ['gap', 'row: { flexDirection: "row", gap: 8 },'],
    ['borderRadius', 'b: { borderRadius: 16 }'],
    ['fontSize', 't: { fontSize: 18 }'],
    ['lineHeight', 't: { lineHeight: 24 }'],
    ['fontWeight string', "t: { fontWeight: '600' }"],
    ['fontWeight bold', "t: { fontWeight: 'bold' }"],
    ['width', 'c: { width: 40 }'],
    ['minHeight', 'c: { minHeight: 56 }'],
    ['expression with a literal', 'c: { padding: spacing.lg + 8 }'],
    ['ternary with a literal', 'c: { padding: big ? 20 : spacing.sm }'],
    ['negative', 'c: { marginTop: -4 }'],
    ['non-100 percent', "c: { width: '50%' }"],
  ])('catches %s', (_n, src) => {
    expect(findLayoutLiterals(src)).toHaveLength(1);
  });

  it.each([
    ['token spacing', 'a: { padding: spacing.lg }'],
    ['token typography spread', 'a: { ...typography.label }'],
    ['zero', 'a: { margin: 0, padding: 0 }'],
    ['hairline', 'a: { borderWidth: 1, height: 1 }'],
    ['100 percent', "a: { width: '100%' }"],
    ['token control size', 'a: { height: layout.fabSize, minWidth: touchTarget.min }'],
    ['string alignment', "a: { alignItems: 'center', height: 'auto' }"],
    ['comment', '// padding: 24 was the old value'],
    ['other numeric style (flex, opacity)', 'a: { flex: 2, opacity: 0.5 }'],
  ])('ignores %s', (_n, src) => {
    expect(findLayoutLiterals(src)).toHaveLength(0);
  });
});

describe('layout literal baseline (SUI-Q-1)', () => {
  const current = scanAll();
  const listed = baseline as Record<string, number>;

  it('scans a plausible number of files', () => {
    expect(walk(SRC).length).toBeGreaterThan(20);
  });

  it('flags the known offender StateViews.tsx today', () => {
    expect(current['src/components/StateViews.tsx']?.length).toBeGreaterThan(0);
  });

  it('no file outside the baseline has a violation', () => {
    const fresh = Object.entries(current)
      .filter(([f]) => !(f in listed))
      .map(([f, hits]) => `${f}\n    ${hits.join('\n    ')}`);
    expect(fresh).toEqual([]);
  });

  it('no listed file has more violations than listed', () => {
    const worse = Object.entries(current)
      .filter(([f, hits]) => f in listed && hits.length > listed[f])
      .map(([f, hits]) => `${f}: ${hits.length} > ${listed[f]}`);
    expect(worse).toEqual([]);
  });

  it('every listed file still exists and still has that many violations (shrink the entry, delete it when clean)', () => {
    const stale = Object.entries(listed)
      .filter(([f, n]) => (current[f]?.length ?? 0) !== n)
      .map(([f, n]) => `${f}: baseline ${n}, now ${current[f]?.length ?? 0}`);
    expect(stale).toEqual([]);
  });
});

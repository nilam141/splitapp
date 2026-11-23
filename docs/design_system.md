# Design System

> Owner of the visual layer for `mobile/`. Tokens live in `mobile/src/theme/` and are the only place a color literal may appear. Original work: no palette, icon, string or layout was taken from any other app. Contrast numbers below are computed from the token values and re-checked on every test run (`mobile/src/theme/__tests__/theme.test.ts`).

## 1. Visual direction

Calm and precise, like a well-kept ledger: quiet cool-grey layers, generous space, and one confident blue that appears only where the user can act. Money is the hero, so amounts get the largest, heaviest, tabular type, and status is carried by sign and words first, color second. Light mode is soft layers with faint shadows; dark mode is deep ink with lighter surfaces standing in for shadows.

## 2. Color strategy

About 60% neutral backgrounds, 30% surfaces and text, 10% brand. Brand blue appears on buttons, the active tab, links, focus and key highlights only, never on large text blocks. There is no second brand color. Green and red are reserved for status, and the brand is neither. Owing is orange on purpose: it is a normal state, not an error. Red is for real errors only (failed save, invalid input).

## 3. Palette

### 3.1 Final tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| `background` | `#F7F7FB` | `#0E0F1A` | Screen background |
| `surface` | `#FFFFFF` | `#171828` | Cards, list groups, bottom tabs |
| `surfaceRaised` | `#FFFFFF` | `#1F2035` | Sheets, dialogs, menus *(dark only differs)* |
| `surfaceOverlay` | `#FFFFFF` | `#27283F` | Popovers above a raised surface *(dark only differs)* |
| `fieldBackground` | `#F0F0F7` | `#1F2035` | Inputs, segmented track, settled chip |
| `textPrimary` | `#14142B` | `#F2F2FA` | Main text |
| `textSecondary` | `#6B6B85` | `#9A9AB5` | Supporting text, placeholders, inactive tab |
| `textDisabled` | `#A3A3B8` | `#5E5F7A` | Disabled only (exempt from contrast) |
| `border` | `#E6E6F0` | `#262740` | Decorative dividers and card outlines |
| `borderStrong` | `#80809A` | `#6A6B90` | **New.** Input, checkbox and outlined-button boundaries |
| `brand` | `#2563EB` | `#60A5FA` | Primary button fill, active tab, links, focus |
| `brandPressed` | `#1D4ED8` | `#4B93F0` | Pressed state |
| `textOnBrand` | `#FFFFFF` | `#0E0F1A` | **Changed in dark.** Label on a flat brand fill |
| `brandText` | `#1D4ED8` | `#60A5FA` | **New.** Brand text on `brandSubtle` |
| `brandSubtle` | `#EEF3FD` | `#212C45` | Selected chip / segmented thumb |
| `owed` | `#12A150` | `#4ADE80` | Icons, bars, dots (non-text) |
| `owedText` | `#0D743A` | `#4ADE80` | **New in light.** Text for "owed" |
| `owedSubtle` | `#ECF4EF` | `#1E3434` | Owed chip fill |
| `owe` | `#E8590C` | `#FF9A5C` | Icons, bars, dots (non-text) |
| `oweText` | `#AC4209` | `#FF9A5C` | **New in light.** Text for "owe" |
| `oweSubtle` | `#F8F0EB` | `#372A2F` | Owe chip fill |
| `error` | `#E5484D` | `#FF8A8F` | Error icons and field borders (non-text) |
| `errorText` | `#B3383C` | `#FF8A8F` | **New in light.** Error text |
| `errorSubtle` | `#F9EFEF` | `#372836` | Error banner fill |
| `avatarBackground` / `avatarText` | `#E6E6F0` / `#14142B` | `#2A2B45` / `#F2F2FA` | Neutral initials avatar (no rainbow avatars) |
| `inverseSurface` / `inverseText` / `inverseLink` | `#14142B` / `#F2F2FA` / `#93C5FD` | `#F2F2FA` / `#14142B` / `#2563EB` | Snackbar |
| `gradient` | `#5B5BD6` → `#7C5CE0` | same | Optional, **off by default** (3.4) |

Every value you gave is kept as-is except where listed in 3.2.

### 3.2 What I changed and why

| Change | Why (measured) |
|---|---|
| Light `owed #12A150` kept for icons/bars; added **`owedText #0D743A`** for text | `#12A150` as text is 3.15:1 on background and 3.37:1 on surface. Fails 4.5. |
| Light `owe #E8590C` kept for icons/bars; added **`oweText #AC4209`** | `#E8590C` as text is 3.35:1 on background and 3.58:1 on surface. Fails 4.5. |
| Light `error #E5484D` kept for icons/borders; added **`errorText #B3383C`** | `#E5484D` as text is 3.66:1 on background and 3.91:1 on surface. Fails 4.5. |
| Dark button label is **`#0E0F1A`, not white** (`textOnBrand`) | White on `#60A5FA` is 2.54:1. Dark ink on it is 7.50:1. |
| Added **`borderStrong`** for control boundaries | Your `border` is 1.16:1 (light) and 1.21:1 (dark) against its surface. Fine as a divider, but WCAG 1.4.11 needs 3:1 for an input's edge. `border` stays decorative. |
| Added **`brandText` `#1D4ED8`** (light) for text on `brandSubtle` | `#2563EB` on a 10% blue tint was 4.49:1. An 8% tint plus the darker blue gives 6.02:1. |
| Subtle fills (`*Subtle`) defined as flat hex, not alpha | Flat colors make contrast checkable and stable over any host surface. |

The darker `*Text` variants keep the same hue, so a chip reads as the same green/orange/red family. Dark mode needed no status changes: all of your dark values pass 4.5:1 comfortably (min 7.75:1 on surface).

### 3.3 Contrast results

Computed with the WCAG 2.x relative-luminance formula. Required: 4.5:1 for text, 3:1 for icons, boundaries and focus. **0 failures** in the final palette.

| Pair | Needs | Light | Dark |
|---|---|---|---|
| textPrimary on background | 4.5:1 | 16.87 | 17.11 |
| textSecondary on background | 4.5:1 | 4.83 | 6.95 |
| brand on background (links) | 4.5:1 | 4.84 | 7.50 |
| owedText on background | 4.5:1 | 5.50 | 10.94 |
| oweText on background | 4.5:1 | 5.56 | 9.10 |
| errorText on background | 4.5:1 | 5.54 | 8.43 |
| textPrimary on surface | 4.5:1 | 18.03 | 15.74 |
| textSecondary on surface | 4.5:1 | 5.16 | 6.40 |
| brand on surface | 4.5:1 | 5.17 | 6.90 |
| owedText on surface | 4.5:1 | 5.87 | 10.06 |
| oweText on surface | 4.5:1 | 5.94 | 8.37 |
| errorText on surface | 4.5:1 | 5.92 | 7.75 |
| textPrimary on surfaceRaised | 4.5:1 | 18.03 | 14.33 |
| textSecondary on surfaceRaised | 4.5:1 | 5.16 | 5.82 |
| textPrimary on surfaceOverlay | 4.5:1 | 18.03 | 12.90 |
| textSecondary on surfaceOverlay | 4.5:1 | 5.16 | 5.24 |
| textPrimary on fieldBackground | 4.5:1 | 15.89 | 14.33 |
| textSecondary on fieldBackground (placeholder, settled chip) | 4.5:1 | 4.55 | 5.82 |
| textOnBrand on brand (button label) | 4.5:1 | 5.17 | 7.50 |
| textOnBrand on brandPressed | 4.5:1 | 6.70 | 6.11 |
| brandText on brandSubtle (selected chip) | 4.5:1 | 6.02 | 5.47 |
| owedText on owedSubtle (balance chip) | 4.5:1 | 5.24 | 7.55 |
| oweText on oweSubtle (balance chip) | 4.5:1 | 5.27 | 6.53 |
| errorText on errorSubtle (banner) | 4.5:1 | 5.25 | 6.11 |
| textPrimary on errorSubtle (banner body) | 4.5:1 | 15.99 | 12.41 |
| avatarText on avatarBackground | 4.5:1 | 14.55 | 12.33 |
| inverseText on inverseSurface (toast) | 4.5:1 | 16.19 | 16.19 |
| inverseLink on inverseSurface (toast action) | 4.5:1 | 10.00 | 4.64 |
| White on gradient start `#5B5BD6` / end `#7C5CE0` | 4.5:1 | 5.37 / 4.70 | 5.37 / 4.70 |
| owed icon/bar on surface / background | 3:1 | 3.37 / 3.15 | 10.06 / 10.94 |
| owe icon/bar on surface / background | 3:1 | 3.58 / 3.35 | 8.37 / 9.10 |
| error icon/border on surface / background | 3:1 | 3.91 / 3.66 | 7.75 / 8.43 |
| borderStrong on surface / fieldBackground | 3:1 | 3.84 / 3.38 | 3.44 / 3.13 |
| focusRing on surface / background | 3:1 | 5.17 / 4.84 | 6.90 / 7.50 |

Tightest margins: light `textSecondary` on `fieldBackground` (4.55), dark `inverseLink` (4.64) and light `textSecondary` on background (4.83). Do not lighten these.

### 3.4 The optional gradient (a decision for you)

`#5B5BD6 → #7C5CE0` is indigo to violet. Next to a blue active tab and blue links it reads as a second brand color, which contradicts rule "no second brand color". It passes contrast with a full-opacity white label (4.70:1 minimum), so it is safe to use. The owner decided (2026-11-16) to keep it off. It is shipped as tokens with `brandGradient.enabled = false`, and components must fall back to flat `brand` when it is off. Using it also needs a gradient library (none is installed). Allowed only on the primary button and the screen header, never on cards, chips or tabs. Text on it is full-opacity white only (a 80% white subtitle would fail).

## 4. Typography

System font (Roboto on Android): nothing to bundle or license. Sizes are sp and follow the user's font setting. Money uses tabular figures.

| Variant | Size / line | Weight | Use |
|---|---|---|---|
| `display` | 34 / 40 | 700 | Hero balance on a header |
| `amountLarge` | 28 / 34 | 700 | Amount input, settle-up amount |
| `title1` | 24 / 32 | 700 | Screen titles, empty-state headline |
| `title2` | 20 / 28 | 600 | Section titles, group name in header |
| `headline` | 16 / 24 | 600 | Row title, card title |
| `body` | 16 / 24 | 400 | Default text, input text |
| `bodyStrong` | 16 / 24 | 600 | Emphasis in running text |
| `amount` | 16 / 24 | 600 | Amounts in rows (tabular) |
| `callout` | 14 / 20 | 400 | Secondary text, helper text, row subtitle |
| `label` | 14 / 20 | 600 | Buttons, tabs, chips |
| `caption` | 12 / 16 | 500 | Timestamps, footers. Nothing is smaller than 12sp |

Font scaling: do not disable it. Fixed-height controls (tab bar, chips, buttons) cap at `maxFontScale.fixedControl` (1.3); everything else uses 2.0 and its container grows with it. Test at 1.0, 1.3 and 2.0.

## 5. Spacing, radius, elevation

**Spacing (4dp grid):** `xxs 2`, `xs 4`, `sm 8`, `md 12`, `lg 16` (screen gutter, card padding), `xl 20`, `xxl 24`, `xxxl 32`, `huge 48`, `giant 64`. Layout constants: header 56, tab bar 64, list row min height 64, FAB 56, content max width 640. Avatars: 32 / 40 / 56 / 80.

**Radius:** `xs 6`, `sm 8`, `md 12` (inputs, buttons), `lg 16` (cards), `xl 24` (sheets, dialogs), `pill 999` (chips, balance chips, FAB, segmented control).

**Elevation:**

| Level | Light | Dark | Use |
|---|---|---|---|
| 0 | none | `background` | Screen |
| 1 | shadow 0/1/3, 6%, elev 1 | `surface` + 1dp `border` outline | Cards, list groups |
| 2 | shadow 0/4/10, 8%, elev 3 | `surfaceRaised` | FAB, sticky header while scrolled |
| 3 | shadow 0/10/24, 12%, elev 8 | `surfaceOverlay` | Dialogs, sheets, menus |

Dark mode has no shadows at all; each level steps to a lighter surface. Where two same-level surfaces touch in dark mode, use a 1dp `border`.

## 6. Components

All interactive components: minimum **48 × 48dp** hit area (use `hitSlop` when the visual is smaller), 8dp minimum gap between adjacent targets, a pressed state, a visible focus ring (2dp `focusRing`, 2dp offset) for keyboard and switch access, and an `accessibilityRole` and label.

### 6.1 Buttons

| Variant | Fill | Label | Border | Use |
|---|---|---|---|---|
| Primary | `brand` (gradient only if enabled) | `textOnBrand`, `label` | none | One per screen: Save, Settle up, Log in |
| Secondary | `fieldBackground` | `textPrimary` | none | Alternatives: Remind, Share |
| Outlined | transparent | `textPrimary` | 1dp `borderStrong` | Low emphasis |
| Text / link | none | `brand` | none | Inline actions, "Forgot password" |
| Destructive | transparent | `errorText` | 1dp `error` | Delete, Leave. Never filled red |

Height 52, horizontal padding 20, radius `md`, full width on forms. States: pressed `brandPressed`; disabled fill `fieldBackground`, label `textDisabled`; loading replaces the label with a 20dp spinner and keeps the width, and the button is disabled and announces "loading". Icon + label buttons put the icon 8dp before the label. FAB: 56dp pill, `brand` fill, `textOnBrand` icon, elevation 2, labelled "Add expense", bottom-right, 16dp from the edges and above the tab bar.

### 6.2 Inputs

Height 56 (multiline grows), radius `md`, fill `fieldBackground`, 1dp `borderStrong` outline, 16dp horizontal padding. Visible label above the field (`callout`, `textSecondary`), never placeholder-only. Placeholder uses `textSecondary`. Focus: outline becomes 2dp `brand`. Error: outline 2dp `error`, an `error` icon, and message below in `errorText` (`callout`); the message states the fix ("Password must be at least 8 characters"). Helper text and the error share the same slot below the field. Disabled: `textDisabled`. Money input: `amountLarge`, right-aligned digits, currency code as a fixed prefix chip, decimals limited by the currency exponent (`mobile/src/money/parse.ts`). Password: show/hide toggle, 48dp target, labelled "Show password".

### 6.3 Cards

`surface`, radius `lg`, 16dp padding, elevation 1, no border in light and a 1dp `border` in dark. Pressable cards use the Android ripple; no tinted overlay. Group content with 16dp gaps; dividers inside a card are 1dp `border`, inset 72dp from the left to align after the avatar.

### 6.4 List rows

Min height 64, 16dp horizontal padding. Layout: leading avatar or category icon (40dp) · 12dp · text column (title `headline`, subtitle `callout` `textSecondary`, one line each, ellipsize) · trailing column right-aligned (amount `amount`, caption below). Whole row is the touch target. Pressed: ripple. Unread (activity): title weight 700 plus a 8dp `brand` dot (the dot is decorative; "unread" is also in the accessibility label). Section headers: `caption`, `textSecondary`, uppercase not required, sticky, 32dp high.

### 6.5 Avatars

Circle, sizes 32 / 40 / 56 / 80. Photo when present; otherwise initials (up to 2 letters, `label`) on `avatarBackground` in `avatarText`. All initial avatars are the same neutral so color never competes with the balance colors. Placeholder (invited, not registered) users get a 1dp dashed `borderStrong` ring and the word "invited" is shown where there is room. Groups with no image show a type glyph (home / trip / couple / other) on the same neutral.

### 6.6 Money and balance chips

All money text is produced by the one shared helper (`formatMoney` / `useMoney().format` in `mobile/src/money/format.ts`) from integer minor units; nothing in the theme or a component divides, multiplies or `toFixed`s an amount. Use `balanceStyle(colors, amountMinor)` for colors, sign and word.

| Tone | Sign | Word on a chip | Sentence form (rows, summaries) | Text / fill |
|---|---|---|---|---|
| Owed to you | `+` | owed | "you are owed INR 500.00" / "owes you INR 500.00" | `owedText` / `owedSubtle` |
| You owe | `−` | owe | "you owe INR 500.00" | `oweText` / `oweSubtle` |
| Settled | none | settled up | "settled up" | `textSecondary` / `fieldBackground` |

Chip: pill, height 28 (visual) inside a 48dp row hit area, 10dp horizontal padding, `label`. Content: sign + amount, then the word on wide chips, e.g. "+ INR 500.00 owed", "− INR 500.00 owe". The sign and the word are both required; color is a reinforcement. A color-blind or grayscale reader must be able to tell the tones apart from the text alone. Several currencies stack one chip per currency (never summed, F-43). The accessibility label reads the full sentence ("Ravi owes you 500 rupees"), not the glyph.

### 6.7 Bottom tabs

4 tabs (Friends, Groups, Activity, Account). Height 64 + bottom safe-area inset, `surface` fill, 1dp top `border` (light) or no border (dark, the surface step is enough). Each tab is a 48dp-minimum target (in practice a quarter of the bar width) with a 24dp icon and a 12sp label, always shown, never icon-only. Active: icon and label `brand`, plus a 3dp × 24dp `brand` indicator bar above the icon so the state does not rely on hue alone. Inactive: `textSecondary`. Activity badge: a pill in `inverseSurface` with `inverseText` (neutral, so it does not read as an error or as brand), showing 1 to 99 then "99+", hidden at 0 (SCR-07). The accessibility label includes the count ("Activity, 3 unread"). The FAB sits above the bar, not inside it.

### 6.8 Empty states

Centered in the content area: 96dp line illustration (our own geometric shapes in `textSecondary` and `brandSubtle`), `title2` headline, `body` `textSecondary` one-line explanation, then one primary button. Copy comes from `screens.md` ("add your first friend", "create a group for your home, trip or partner", "no activity yet"). Filter-with-no-results states have no button.

### 6.9 Loading skeletons

Appear within 100 ms; a spinner is added after 300 ms if there is still no data (screens.md). Skeleton blocks use `skeletonBase` with a `skeletonHighlight` shimmer sweep, 1.2 s loop, radius matching the real element, and mimic the real row (avatar circle, two text bars, trailing amount bar). Never show fake amounts. With reduced motion on, the shimmer is replaced by a static `skeletonBase`. The container has `accessibilityLabel="Loading"` and `accessibilityLiveRegion="polite"`; individual skeleton blocks are hidden from the accessibility tree.

### 6.10 Error banners

Inline, above the list, `errorSubtle` fill, 1dp `error` outline, radius `md`, 12dp padding. Content: 20dp `error` alert icon · message in `textPrimary` (`callout`) with the lead phrase in `errorText` bold · a 48dp "Retry" text button in `brand`. Cached data stays visible below (screens.md). Live region `assertive` only for failed saves; `polite` for load failures. Offline is not an error: use a neutral banner (`surfaceRaised`, `textSecondary`, cloud-off icon), never red. Inline field errors are described in 6.2. Toasts use the snackbar tokens (`inverseSurface`), 4 s, one action max.

## 7. Accessibility rules

1. **Contrast:** text 4.5:1 (large text 3:1 is not relied on), icons / boundaries / focus 3:1. Only the tokens listed in 3.3 may be paired; any new pair is added to `testing/contrast.ts` first.
2. **Never color alone:** owed / owing always carries the sign and the word (6.6). Selected states add a shape change (indicator bar, check icon), errors add an icon and text.
3. **Touch targets:** at least 48 × 48dp, 8dp apart, including icon buttons, checkboxes, chips and tab items.
4. **Dynamic type:** support to 200%; fixed-height controls cap at 1.3; no truncation of amounts, so amounts wrap the row to two lines before they ellipsize.
5. **Screen readers (TalkBack):** every pressable has role and label; amounts are read as words ("you owe 500 rupees"), not symbols; decorative icons and dots are hidden; headings use `accessibilityRole="header"`; list rows read as one sentence; the focus order follows the visual order; modal sheets trap focus and restore it on close.
6. **Motion:** respect the system "remove animations" setting (`AccessibilityInfo.isReduceMotionEnabled`). Durations: press 100 ms, transitions 200 to 250 ms, sheets 300 ms, exit faster than enter. Nothing flashes more than 3 times a second.
7. **Brand discipline:** `brand` is for buttons, the active tab, links, focus and small key highlights. Not for body text, headers' large text areas or backgrounds of big areas.
8. **Theme:** follow the system light/dark setting live; every screen is checked in both. No color literals outside `mobile/src/theme/`.
9. **Forms:** visible labels, errors next to the field with the fix, the first invalid field focused and announced on submit, correct `keyboardType` and `autoComplete`.
10. **Destructive actions** use confirm dialogs with the consequence in plain words (screens.md SCR-14, SCR-20), and the destructive button is never the default focus.

## 8. Layout guidance for the five key screens

Gutter 16dp, content max width 640 (centered above that), safe areas respected top and bottom. Header 56dp on `background` (or the gradient if enabled); no header shadow until the list scrolls, then elevation 2.

### 8.1 Home / balances (Friends tab SCR-08, Groups tab SCR-09)

1. Header: title `title1` ("Friends" / "Groups"), search icon (V2) and filter menu as 48dp icon buttons.
2. **Summary card** (`surface`, elevation 1): a one-line overall summary. With balances in two currencies, one chip per currency per direction: "you owe INR 120.00" and "you are owed INR 500.00" as two rows, each with sign and word. `display` size is used only when there is a single figure. "Settled up" is `title2`.
3. Filter chips row (all / outstanding / owe me / I owe), horizontally scrollable, 48dp tall targets, selected = `brandSubtle` + `brandText` + check icon.
4. List of 64dp rows in one card: avatar, name, per-group breakdown as `callout` `textSecondary`, trailing balance chip(s). Group tab: "Non-group expenses" row first or last per screens.md, then groups.
5. "show N settled-up friends" collapse row: `callout`, `brand` link style.
6. FAB "Add expense" bottom-right; empty state when there is nothing.

### 8.2 Group detail (SCR-13)

1. Header: back, group name `title2`, settings icon. Below, a **position card**: group avatar 56dp, name, the user's balance lines (at most 3, then "+N more") as chips with sign and word.
2. Action row: Settle up (primary, 48dp+), then Balances, Totals, Charts, Export as secondary buttons in a horizontal scroll; gated ones show a lock icon and open the paywall.
3. Timeline grouped by month with sticky month headers. Expense row: date block (day number `headline`, month `caption`) · description `headline` · "Ravi paid INR 900.00" `callout` · trailing "you owe INR 300.00" chip. Payment rows use a different leading glyph (arrow) and a neutral `fieldBackground` fill so they are not confused with expenses. Deleted rows are struck through with a "deleted" label.
4. Settled-up marker row: neutral, `callout`.
5. FAB prefilled with the group. All settled: neutral "you are all settled up in this group" state with a check icon.
6. **Members entry (CR-UI-1, 2026-11-20).** There is no inline Members section on this screen. The "N members" text ("1 member" for one) under the group name is a pressable: role `button`, label like "3 members, show list", 48dp target via `minHeight`/`hitSlop`, `callout` `textSecondary` with a trailing chevron so the affordance is not color alone. Tapping opens the members view (bottom sheet or dedicated screen/modal, chosen by Mobile to fit existing navigation) listing every member as a `ListRow` with `Avatar` and balance chip; add people, invite via link and remove member are reachable from there with unchanged rules. Tokens only.

7. **SCR-13 header redesign (CR-UI-2, 2026-11-20; supersedes the position card in item 1 and the per-member lines CR-UI-1 kept).** The top of the screen states each fact once, in this order:
   1. **Title:** the group name appears only in the nav header (`title2`). There is no in-body title.
   2. **Subtitle row:** group type (for example "Trip") and the members entry sit on one compact row: `callout` `textSecondary`, separated by a middle dot. The members entry keeps `testID` `members-entry`, role `button`, label "N members, show list", a trailing chevron, 48dp target via `minHeight`/`hitSlop` (item 6 unchanged).
   3. **"Your balance" card:** one `surface` Card (`radius` `lg`, padding `md`, 8dp rhythm between rows, spacing tokens only). A `caption` `textSecondary` label "Your balance" heads it. Then one row per currency, never summed across currencies, in the existing money formatters (integer minor units):
      - owed to the viewer: up-arrow icon, headline "You are owed", amount;
      - viewer owes: down-arrow icon, headline "You owe", amount;
      - zero in that currency: omitted when another currency is non-zero.
      The headline is `callout` `textSecondary`; the amount uses the largest type token (`display` for one currency, `title1` when two or more rows). Direction is carried by the words and the icon, with the amount color from the existing owed / owing tokens as reinforcement only. Icons are 20dp, decorative (hidden from TalkBack), and meet 3:1 against `surface`; text meets 4.5:1.
   4. **Counterparty context (optional, inside the card):** at most 2 lines of "Dev E2E owes you INR 15,025.00" or "You owe Dev E2E INR 15,025.00", the largest counterparties by amount, only when the data is already loaded on the client (no new request, no contract change). The card has no navigation link: the "See all balances ›" link was removed (user decision 2026-11-20) because it duplicated the Balances button; the Balances button (item 5) is the single route to GroupBalances (SCR-15). If the loaded data does not carry pairwise lines, show no counterparty lines.
   5. **Actions:** below the card, one row with a `spacing.md` gap (12dp): "Settle up" (primary, filled `brand`) and "Balances" (secondary in the normal state, outlined in the settled state; it is the single route to GroupBalances). Each is at least 48dp tall, has visible pressed feedback (state layer, 100 ms) and they never touch. At fontScale 2.0 the row wraps to two stacked full-width buttons with the same gap. Totals, Charts and Export keep their place in the horizontal action row from item 2.
   6. **Settled state:** when the viewer has no non-zero balance in any currency, the card shows a check icon and "You are all settled up in this group", no amounts and no counterparty lines. "Settle up" stays visible but secondary (OQ-48); "Balances" stays.
   7. **Removed:** the per-member net list ("You get back ... in total", "+N more") on this screen. Per-member detail lives in the Members view (GroupMembers) and Balances (SCR-15).
   8. **Accessibility:** the card is one logical group (`accessible` container) with a single spoken label, for example "Your balance in Goa Trip. You are owed INR 15,025.00 and USD 45.00." (settled: "Your balance in Goa Trip. You are all settled up."). Amounts are spoken as words by the existing helpers; icons are hidden; the two buttons remain separate focus stops after the card. There is no "See all balances" link focus stop.
   9. **Verification:** light and dark with an independent contrast check of every text/icon pair used (4.5:1 text, 3:1 icons; new pairs are added to `testing/contrast.ts` first), fontScale 2.0 with no clipped or truncated amounts, and 375dp width. The card has no `see-all-balances` element, and the Balances button navigates to GroupBalances with 0 extra requests.

### 8.3 Add expense (SCR-22)

1. Header: close (X), title "Add expense", Save as a text button in `brand` (disabled until valid), mirrored by a full-width primary Save at the bottom so the thumb reaches it.
2. "With you and" token field (chips, 48dp). Description input with a category button (48dp) beside it.
3. **Amount block**: currency button then `amountLarge` money input, centered, auto-focused with the numeric keypad. Inline error for amount rules below it.
4. Summary sentence as a tappable row: "Paid by **you** and split **equally**" (the two bold parts are brand-colored links with 48dp targets, opening SCR-24 / SCR-23).
5. Chip row: date, group, note/image, repeat (V2). Each chip is `fieldBackground`, 48dp target.
6. Split screens (SCR-23): segmented tabs, one row per person (avatar, name, amount or percent input), and a **sticky footer** showing "X of Y", "Z left" or "over by Z". The footer is neutral while incomplete, `owedText` + check icon when exact, and `errorText` + error icon only after a failed Done. Never red while the user is still typing.
7. Keyboard: the layout must scroll so the focused field stays visible; Save stays reachable.

### 8.4 Settle up (SCR-30, SCR-31)

1. SCR-30: title, payer chooser (avatar row, 48dp), then a card of balance rows: avatar, "you owe Asha" `headline`, trailing `amount` with the `−` sign and "owe" word. Rows that are owed to the user use `+` and "owed". "Settle all balances" is the last row. No balances: check icon and "you are settled up".
2. SCR-31: **From → To** with two 56dp avatars and an arrow (swap button 48dp, labelled). Beneath, a centered `amountLarge` money input prefilled with the balance, a currency chip, then date, group and note rows. One primary button "Save payment" pinned to the bottom.
3. The "more than owed" confirmation is a dialog stating the direction flip in words ("Asha will then owe you INR 36.67"), with a neutral default button. This is a warning, not an error: no red.
4. After save, a snackbar "Payment recorded" with Undo is preferred to a blocking screen.

### 8.5 Activity (SCR-10)

1. Header: title `title1`. Date section headers (Today / Yesterday / date), sticky.
2. Activity row (64dp+, may wrap to 3 lines): 40dp leading icon on `fieldBackground` (our own glyph set, not avatars of the actor), sentence "**Ravi** added **Groceries** in Flat 4B" (`body`, actor and object in `bodyStrong`), effect line "you owe INR 30.00" as a chip with sign and word, relative time `caption`. Unread: bold sentence and the 8dp `brand` dot. Only the sentence and effect are read by TalkBack as one label.
3. Deleted objects show a "deleted" tag in `textSecondary`; Restore lives on the detail screen.
4. Infinite scroll with a 48dp footer spinner; skeleton rows on first load; empty state "no activity yet".
5. Opening the tab clears the badge (SCR-07).

## 9. Implementation notes (`mobile/src/theme/`)

| File | Contents |
|---|---|
| `colors.ts` | `ColorTokens`, `lightColors`, `darkColors`, `brandGradient` (disabled) |
| `typography.ts` | `typography`, `maxFontScale` |
| `spacing.ts` | `spacing`, `touchTarget`, `layout` |
| `radius.ts` | `radius` |
| `elevation.ts` | `elevationFor(scheme)`, `surfaceForLevel` |
| `balance.ts` | `balanceTone`, `balanceStyle`: tone colors plus the required sign and word |
| `ThemeProvider.tsx` | `ThemeProvider` (follows `useColorScheme`), `useTheme()`, `useThemedStyles()` |
| `testing/contrast.ts`, `__tests__/theme.test.ts` | WCAG helper, the pair list, 88 assertions |

Usage: wrap the app in `<ThemeProvider>` once, then `const { colors, typography, spacing, radius } = useTheme()`. Build styles with `useThemedStyles(theme => StyleSheet.create({...}))`. The provider is not yet mounted in `App.tsx` and no screen uses it (out of scope for this task).

**Existing hard-coded colors (migration required; the "no color literals outside `mobile/src/theme/`" rule stands, decided 2026-11-16, not yet done):** `mobile/src/` still contains literals such as `#1b6e5a` (a teal-green brand, which breaks "brand is not green"), `#1b7f3b`, `#c25e00`, `#b00020` and `#bbb` in `expenses/SplitPanel.tsx`, `expenses/PickerPanels.tsx`, `expenses/ExpenseRow.tsx` and `expenses/PayersPanel.tsx`, and possibly more. The mobile agent should replace them with theme tokens in a follow-up task.

**Amount formatting (decided 2026-11-16):** the display form is the one `mobile/src/money/format.ts` already produces, the currency code then the amount (`INR 1,234.50`). Every example in this document uses it. No currency symbols, no change to the helper.

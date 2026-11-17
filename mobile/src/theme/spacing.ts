// 4dp grid. Use named steps, not raw numbers, in layouts.
export const spacing = {
  none: 0,
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16, // default screen gutter and card padding
  xl: 20,
  xxl: 24,
  xxxl: 32,
  huge: 48,
  giant: 64,
} as const;

export type SpacingToken = keyof typeof spacing;

// Minimum interactive size (dp). Visual size may be smaller if hitSlop makes up the difference.
export const touchTarget = {
  min: 48,
  // Gap between adjacent targets so a thumb does not hit the wrong one.
  minGap: 8,
} as const;

// Control sizing (design_system 6.1): button height, focus ring and in-button spinner.
export const control = {
  height: 52,
  textHeight: 40, // compact 'text' variant visual height; hitSlop brings the target to touchTarget.min
  focusRingWidth: 2,
  focusRingOffset: 2, // gap between the control edge and the ring (design_system 6.1)
  spinner: 20,
} as const;

export const layout = {
  screenGutter: spacing.lg,
  maxContentWidth: 640, // keeps lines readable on tablets / large foldables
  tabBarHeight: 64,
  headerHeight: 56,
  fabSize: 56,
  listRowMinHeight: 64,
  avatar: { sm: 32, md: 40, lg: 56, xl: 80 },
} as const;

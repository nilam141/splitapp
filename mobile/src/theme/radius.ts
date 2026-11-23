export const radius = {
  none: 0,
  xs: 6, // chips' inner marks, small thumbnails
  sm: 8, // small tags, skeleton lines
  md: 12, // inputs, buttons
  lg: 16, // cards
  xl: 24, // bottom sheets (top corners), dialogs
  pill: 999, // chips, balance chips, FAB, segmented control
} as const;

export type RadiusToken = keyof typeof radius;

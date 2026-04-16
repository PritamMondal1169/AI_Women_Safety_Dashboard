import { Platform } from 'react-native';

/**
 * SafeSphere Obsidian Design System — Mobile Tokens
 */

export const theme = {
  colors: {
    // Primary palette
    background: '#0b1326',
    surface: '#171f33',
    surfaceVariant: '#222a3d',
    
    // Tonal shades
    surfaceLowest: '#060e20',
    surfaceLow: '#131b2e',
    surfaceHigh: '#2d3449',
    surfaceHighest: '#31394d',

    // Accents
    primary: '#7bd0ff',
    primaryGlow: 'rgba(123, 208, 255, 0.25)',
    secondary: '#ffb95f',
    secondaryGlow: 'rgba(255, 185, 95, 0.2)',
    tertiary: '#4edea3',
    tertiaryGlow: 'rgba(78, 222, 163, 0.2)',
    
    // Feedback
    error: '#ffb4ab',
    errorGlow: 'rgba(255, 180, 171, 0.25)',
    success: '#4edea3',
    warning: '#ffb95f',

    // Text
    textPrimary: '#dae2fd',
    textSecondary: '#c6c6cd',
    textMuted: '#909097',

    // Overlays
    glassBg: 'rgba(23, 31, 51, 0.65)',
    glassBorder: 'rgba(123, 208, 255, 0.08)',
  },
  
  spacing: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 48,
  },
  
  roundness: {
    sm: 4,
    md: 12,
    lg: 20,
    xl: 24,
  },

  fonts: {
    regular: Platform.OS === 'ios' ? 'Inter-Regular' : 'sans-serif',
    medium: Platform.OS === 'ios' ? 'Inter-Medium' : 'sans-serif-medium',
    bold: Platform.OS === 'ios' ? 'Inter-Bold' : 'sans-serif-bold',
    black: Platform.OS === 'ios' ? 'Inter-Black' : 'sans-serif-condensed-light', // approximation or just use Bold
  }
};

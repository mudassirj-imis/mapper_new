import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { CssBaseline } from '@mui/material';
import { ThemeProvider as MuiThemeProvider, alpha, createTheme } from '@mui/material/styles';

const ThemeContext = createContext(null);

const THEME_STORAGE_KEY = 'theme-mode';

const BRAND = {
  blue: '#1976d2',
  violet: '#9c27b0',
};

/**
 * Design tokens for both palettes.
 * Light: porcelain surfaces + ink text.
 * Dark: deep navy console (never pure black).
 */
const getDesignTokens = (mode) => {
  const isLight = mode === 'light';

  return {
    palette: {
      mode,
      primary: isLight
        ? { main: BRAND.blue, light: '#4791db', dark: '#115293', contrastText: '#ffffff' }
        : { main: '#4d9be8', light: '#7ab5ee', dark: BRAND.blue, contrastText: '#06121f' },
      secondary: isLight
        ? { main: BRAND.violet, light: '#ba68c8', dark: '#7b1fa2', contrastText: '#ffffff' }
        : { main: '#ba68c8', light: '#ce93d8', dark: BRAND.violet, contrastText: '#150920' },
      background: isLight
        ? { default: '#f4f7fb', paper: '#ffffff' }
        : { default: '#080f1e', paper: '#101b30' },
      text: isLight
        ? { primary: '#101f33', secondary: '#5c6b81', disabled: '#9aa8bb' }
        : { primary: '#e7eef9', secondary: '#93a4bd', disabled: '#5a6b85' },
      divider: isLight ? 'rgba(16, 31, 51, 0.09)' : 'rgba(147, 164, 189, 0.16)',
      success: isLight
        ? { main: '#2e7d32', light: '#4caf50', dark: '#1b5e20' }
        : { main: '#57c17e', light: '#7fd39c', dark: '#2e7d32' },
      warning: isLight
        ? { main: '#ed6c02', light: '#ff9800', dark: '#e65100' }
        : { main: '#f2a445', light: '#f7bd6f', dark: '#ed6c02' },
      error: isLight
        ? { main: '#d32f2f', light: '#ef5350', dark: '#c62828' }
        : { main: '#ef6f6f', light: '#f39a9a', dark: '#d32f2f' },
      info: isLight
        ? { main: '#0288d1', light: '#03a9f4', dark: '#01579b' }
        : { main: '#4fc3f7', light: '#7fd4f9', dark: '#0288d1' },
    },
    shape: {
      borderRadius: 10,
    },
    typography: {
      fontFamily:
        "'IBM Plex Sans', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
      fontFamilyCode:
        "'IBM Plex Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace",
      h1: { fontWeight: 700, letterSpacing: '-0.02em' },
      h2: { fontWeight: 700, letterSpacing: '-0.02em' },
      h3: { fontWeight: 600, letterSpacing: '-0.015em' },
      h4: { fontWeight: 600, letterSpacing: '-0.015em' },
      h5: { fontWeight: 600, letterSpacing: '-0.01em' },
      h6: { fontWeight: 600, letterSpacing: '-0.01em' },
      subtitle1: { fontWeight: 600 },
      subtitle2: { fontWeight: 600 },
      button: { fontWeight: 600, textTransform: 'none', letterSpacing: 0 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundColor: isLight ? '#f4f7fb' : '#080f1e',
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
          },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
          },
        },
      },
      MuiButton: {
        defaultProps: {
          disableElevation: true,
        },
        styleOverrides: {
          root: {
            borderRadius: 10,
            paddingInline: 18,
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: 8,
          },
          label: {
            fontWeight: 600,
          },
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: {
            backgroundColor: isLight ? '#101f33' : '#e7eef9',
            color: isLight ? '#f4f7fb' : '#0a1120',
            fontSize: '0.72rem',
            fontWeight: 500,
            padding: '6px 10px',
            borderRadius: 8,
          },
          arrow: {
            color: isLight ? '#101f33' : '#e7eef9',
          },
        },
      },
      MuiListItemButton: {
        styleOverrides: {
          root: {
            transition: 'background-color 0.2s ease, color 0.2s ease',
          },
        },
      },
      // Console-style table headers; borders and tints follow the palette so
      // both modes stay legible and hover never fights zebra stripes.
      MuiTableHead: {
        styleOverrides: {
          root: ({ theme }) => {
            // Paper base + tint overlay keeps sticky headers opaque.
            const tint = alpha(
              theme.palette.text.primary,
              theme.palette.mode === 'dark' ? 0.045 : 0.022
            );

            return {
              '& .MuiTableCell-root': {
                backgroundColor: theme.palette.background.paper,
                backgroundImage: `linear-gradient(${tint}, ${tint})`,
                color: theme.palette.text.secondary,
                fontFamily: theme.typography.fontFamilyCode,
                fontSize: '0.68rem',
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                whiteSpace: 'nowrap',
                borderBottom: `1px solid ${theme.palette.divider}`,
              },
            };
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: ({ theme }) => ({
            borderBottomColor: theme.palette.divider,
          }),
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: ({ theme }) => ({
            backgroundImage: 'none',
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: theme.shape.borderRadius * 1.6,
            boxShadow:
              theme.palette.mode === 'dark'
                ? '0 28px 70px rgba(0, 0, 0, 0.6)'
                : '0 28px 70px rgba(16, 31, 51, 0.18)',
          }),
        },
      },
      MuiLink: {
        defaultProps: {
          underline: 'hover',
        },
      },
      MuiAlert: {
        styleOverrides: {
          root: {
            borderRadius: 10,
          },
        },
      },
    },
  };
};

const getSystemPreference = () => {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

export function ThemeContextProvider({ children }) {
  const [mode, setMode] = useState(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
    return getSystemPreference();
  });

  // Persist preference.
  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  }, [mode]);

  // Keep the browser chrome color in sync with the active palette.
  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', mode === 'dark' ? '#080f1e' : '#f4f7fb');
    }
  }, [mode]);

  const toggleMode = useCallback(() => {
    setMode((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  const theme = useMemo(() => createTheme(getDesignTokens(mode)), [mode]);

  const contextValue = useMemo(
    () => ({ mode, toggleMode, setMode }),
    [mode, toggleMode]
  );

  return (
    <ThemeContext.Provider value={contextValue}>
      <MuiThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </MuiThemeProvider>
    </ThemeContext.Provider>
  );
}

export function useAppTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useAppTheme must be used within a ThemeContextProvider');
  }
  return context;
}

export default ThemeContext;

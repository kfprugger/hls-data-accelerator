import { createTheme } from '@mui/material/styles';

export function materialTheme(mode: 'light' | 'dark') {
  const dark = mode === 'dark';
  return createTheme({
    palette: {
      mode,
      primary: { main: dark ? '#b7c4ff' : '#465ba8' },
      secondary: { main: dark ? '#c1c5dd' : '#595e77' },
      background: { default: dark ? '#111318' : '#f9f9ff', paper: dark ? '#1b1d24' : '#ffffff' },
      text: { primary: dark ? '#e2e2ec' : '#1b1b23', secondary: dark ? '#c4c5d0' : '#454650' },
    },
    shape: { borderRadius: 20 },
    typography: { fontFamily: 'Roboto, system-ui, -apple-system, sans-serif', h6: { fontWeight: 650 }, button: { textTransform: 'none', fontWeight: 600 } },
    components: {
      MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: { borderRadius: 24, minHeight: 44, paddingInline: 20 } } },
      MuiIconButton: { styleOverrides: { root: { minWidth: 44, minHeight: 44 } } },
      MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
      MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 12 } } },
      MuiDrawer: { styleOverrides: { paper: { borderRadius: '24px 0 0 24px', '@media (max-width:599px)': { borderRadius: 0 } } } },
      MuiCssBaseline: { styleOverrides: {
        'html, body, #root': { minHeight: '100%', margin: 0 },
        '*': { boxSizing: 'border-box' },
        ':focus-visible': { outline: '3px solid #8095ea', outlineOffset: 3 },
        '@media (prefers-reduced-motion: reduce)': { '*, *::before, *::after': { animationDuration: '0.01ms !important', transitionDuration: '0.01ms !important', scrollBehavior: 'auto !important' } },
      } },
    },
  });
}

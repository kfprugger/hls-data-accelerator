import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { App } from './App';
import { materialTheme } from './materialTheme';
import './material.css';

function selectedMode(): 'light' | 'dark' {
  const stored = localStorage.getItem('orchestrator-theme');
  return stored === 'dark' || (stored !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
}
function Root() {
    const [mode, setMode] = useState(selectedMode);
    const theme = useMemo(() => materialTheme(mode), [mode]);
    useEffect(() => { document.documentElement.dataset.materialMode = mode; }, [mode]);
    useEffect(() => {
        const update = () => setMode(selectedMode());
        const query = matchMedia('(prefers-color-scheme: dark)');
        window.addEventListener('orchestrator-theme-change', update);
        query.addEventListener('change', update);
        return () => { window.removeEventListener('orchestrator-theme-change', update); query.removeEventListener('change', update); };
    }, []);
    return <ThemeProvider theme={theme}><CssBaseline /><div data-material-mode={mode}><App /></div></ThemeProvider>;
}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Root /></React.StrictMode>);

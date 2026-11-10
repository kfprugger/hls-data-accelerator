import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';
export type ThemeVariant = 'source' | 'daylight';

const STORAGE_KEY = 'atlas.theme';
const THEME_COLOR: Record<Theme, string> = { light: '#faf9f5', dark: '#1d1c1a' };
const DAYLIGHT_THEME_COLOR = '#f4f1ea';

/**
 * Committed deployment-scoped theme map.
 * med-1109 (workspace 8be8f60c-dae7-4c79-9307-683c5794dcf7, origin elite-otter-03514eba33-westus2.webapp.fabricapps.net)
 * renders the Daylight theme; all other deployments keep the default source theme.
 */
export const DEPLOYMENT_WORKSPACE_THEMES: Readonly<Record<string, ThemeVariant>> = {
  '8be8f60c-dae7-4c79-9307-683c5794dcf7': 'daylight',
};

export const DEPLOYMENT_ORIGIN_THEMES: Readonly<Record<string, ThemeVariant>> = {
  'https://elite-otter-03514eba33-westus2.webapp.fabricapps.net': 'daylight',
};

export function resolveThemeVariant(options?: {
  search?: string;
  origin?: string;
  workspaceId?: string;
}): ThemeVariant {
  const search = options?.search ?? (typeof window !== 'undefined' ? window.location.search : '');
  const origin = options?.origin ?? (typeof window !== 'undefined' ? window.location.origin : '');
  const workspaceId =
    (options?.workspaceId ?? (import.meta.env.VITE_FABRIC_WORKSPACE_ID as string | undefined) ?? '')
      .trim()
      .toLowerCase();

  try {
    const qTheme = new URLSearchParams(search).get('theme')?.trim().toLowerCase();
    if (qTheme === 'daylight' || qTheme === 'source') {
      return qTheme;
    }
  } catch {
    // Ignore malformed query string.
  }

  const normalizedOrigin = origin.replace(/\/$/, '').toLowerCase();
  if (DEPLOYMENT_ORIGIN_THEMES[normalizedOrigin]) {
    return DEPLOYMENT_ORIGIN_THEMES[normalizedOrigin];
  }
  if (workspaceId && DEPLOYMENT_WORKSPACE_THEMES[workspaceId]) {
    return DEPLOYMENT_WORKSPACE_THEMES[workspaceId];
  }
  return 'source';
}

function currentTheme(variant: ThemeVariant): Theme {
  if (variant === 'daylight') return 'light';
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

export function applyThemeVariant(): ThemeVariant {
  const variant = resolveThemeVariant();
  const root = document.documentElement;
  root.dataset.themeVariant = variant;
  if (variant === 'daylight') {
    root.dataset.theme = 'light';
    root.classList.remove('dark');
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', DAYLIGHT_THEME_COLOR);
  }
  return variant;
}

function applyTheme(theme: Theme, variant: ThemeVariant): void {
  const root = document.documentElement;
  root.dataset.themeVariant = variant;
  if (variant === 'daylight') {
    root.dataset.theme = 'light';
    root.classList.remove('dark');
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', DAYLIGHT_THEME_COLOR);
    return;
  }
  root.dataset.theme = theme;
  root.classList.toggle('dark', theme === 'dark');
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme]);
}

/** Light/dark theme, initialised by public/theme-init.js and persisted in localStorage. */
export function useTheme() {
  const variant = resolveThemeVariant();
  const [theme, setThemeState] = useState<Theme>(() => currentTheme(variant));

  useEffect(() => {
    applyTheme(theme, variant);
  }, [theme, variant]);

  // Follow the OS setting until the user picks a theme explicitly (source theme only).
  useEffect(() => {
    if (variant === 'daylight') return;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem(STORAGE_KEY)) setThemeState(e.matches ? 'dark' : 'light');
    };
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [variant]);

  const setTheme = useCallback(
    (next: Theme) => {
      if (variant === 'daylight') return;
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // Storage unavailable: the choice lasts for this page only.
      }
      setThemeState(next);
    },
    [variant]
  );

  return { theme: variant === 'daylight' ? ('light' as Theme) : theme, setTheme, variant };
}

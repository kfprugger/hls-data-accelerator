// Applies the saved (or system) colour theme and deployment theme variant before first paint.
(function () {
  var DAYLIGHT_ORIGINS = {
    'https://elite-otter-03514eba33-westus2.webapp.fabricapps.net': 'daylight',
  };
  var variant = 'source';
  try {
    var params = new URLSearchParams(window.location.search);
    var qTheme = (params.get('theme') || '').toLowerCase();
    if (qTheme === 'daylight' || qTheme === 'source') {
      variant = qTheme;
    } else if (DAYLIGHT_ORIGINS[window.location.origin]) {
      variant = DAYLIGHT_ORIGINS[window.location.origin];
    }
  } catch (e) {
    // Keep default variant.
  }
  var root = document.documentElement;
  root.dataset.themeVariant = variant;
  if (variant === 'daylight') {
    root.dataset.theme = 'light';
    root.classList.remove('dark');
    return;
  }
  var theme = 'light';
  try {
    var saved = localStorage.getItem('atlas.theme');
    theme =
      saved === 'light' || saved === 'dark'
        ? saved
        : window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light';
  } catch (e) {
    // Storage unavailable: keep light.
  }
  root.dataset.theme = theme;
  root.classList.toggle('dark', theme === 'dark');
})();

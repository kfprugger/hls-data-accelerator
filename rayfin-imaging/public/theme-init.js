// Applies the saved (or system) colour theme before first paint to avoid a light/dark flash.
(function () {
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
  var root = document.documentElement;
  root.dataset.theme = theme;
  root.classList.toggle('dark', theme === 'dark');
})();

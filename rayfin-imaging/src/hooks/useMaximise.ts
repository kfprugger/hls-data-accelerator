import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Full screen for a workspace. The element is always maximised inside the window with CSS, which works in every
 * host; the browser's native full screen is attempted on top of that and simply skipped where it is blocked
 * (embedded browsers and iframes without the fullscreen permission never resolve or reject the request).
 */
export function useMaximise<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [on, setOn] = useState(false);

  const exit = useCallback(() => {
    setOn(false);
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
  }, []);

  const enter = useCallback(() => {
    setOn(true);
    const el = ref.current;
    if (el && document.fullscreenEnabled && !document.fullscreenElement) {
      void el.requestFullscreen?.().catch(() => undefined);
    }
  }, []);

  const toggle = useCallback(() => (on ? exit() : enter()), [on, enter, exit]);

  useEffect(() => {
    if (!on) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') exit();
    };
    // Leaving native full screen (Esc is handled by the browser there) also leaves the maximised view.
    let wasNative = false;
    const onChange = () => {
      if (document.fullscreenElement) wasNative = true;
      else if (wasNative) setOn(false);
    };
    window.addEventListener('keydown', onKey);
    document.addEventListener('fullscreenchange', onChange);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('fullscreenchange', onChange);
    };
  }, [on, exit]);

  return { ref, on, toggle };
}

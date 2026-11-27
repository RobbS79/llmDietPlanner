// Shared modal behaviour for the bottom sheets: Escape closes, focus moves into
// the dialog on open and back to the opener on close, Tab stays inside.
import { useEffect, useRef } from 'react';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const focusables = (root: HTMLElement) => Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));

/** Attach the returned ref to the dialog panel. `active=false` hands control to a
 *  nested sheet that replaced this one (PlanSheet → SignupSheet). */
export function useDialog<T extends HTMLElement = HTMLDivElement>(onClose: () => void, active = true) {
  const ref = useRef<T>(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    if (!active) return;
    const opener = document.activeElement as HTMLElement | null;
    const root = ref.current;
    if (root) (focusables(root)[0] ?? root).focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { close.current(); return; }
      const node = ref.current;
      if (e.key !== 'Tab' || !node) return;
      const items = focusables(node);
      if (!items.length) { e.preventDefault(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      const at = document.activeElement;
      const outside = !node.contains(at);
      if (e.shiftKey && (at === first || outside)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (at === last || outside)) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); opener?.focus?.(); };
  }, [active]);

  return ref;
}

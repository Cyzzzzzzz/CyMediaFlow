import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "@phosphor-icons/react";

type Props = { title: string; children: ReactNode; footer?: ReactNode; onClose: () => void; busy?: boolean };

export function AutomationDialog({ title, children, footer, onClose, busy = false }: Props) {
  const ref = useRef<HTMLElement>(null);
  const titleId = useId();
  const close = useRef(onClose);
  const pending = useRef(busy);
  close.current = onClose;
  pending.current = busy;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    const handle = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pending.current) { event.preventDefault(); close.current(); }
      if (event.key !== "Tab") return;
      const elements = Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary, a[href], [tabindex="0"]') ?? [])
        .filter((el) => !el.closest("details:not([open])") || el.tagName === "SUMMARY");
      if (!elements.length) { event.preventDefault(); return; }
      const first = elements[0], last = elements[elements.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === ref.current)) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", handle);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener("keydown", handle); previous?.focus(); };
  }, []);
  return createPortal(<div className="automation-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section ref={ref} className="subscription-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-busy={busy} tabIndex={-1}>
      <header><div><span className="eyebrow">AutoBangumi</span><h2 id={titleId}>{title}</h2></div><button type="button" className="icon-button" aria-label="关闭弹窗" onClick={onClose} disabled={busy}><X size={20} /></button></header>
      <div className="subscription-dialog-body">{children}</div>
      {footer ? <footer>{footer}</footer> : null}
    </section>
  </div>, document.body);
}

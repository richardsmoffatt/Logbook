import { useEffect, useState } from "react";

const ROW = 1.1; // digit row height in em; matches .roll-digit in styles.css

/**
 * Odometer: counts up from `from` to `to` (decimal hours, one decimal place). The tenths wheel turns
 * continuously; each higher wheel moves only while the wheel to its right passes from 9 back to 0,
 * as on a mechanical counter. The count slows towards the end, so the last tenths creep in.
 */
export default function RollingNumber({ from, to }: { from: number; to: number }) {
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const start = Math.round(from * 10), end = Math.round(to * 10);   // in tenths
  const [value, setValue] = useState(reduced ? end : start);

  useEffect(() => {
    if (reduced || start === end) { setValue(end); return; }
    const steps = Math.abs(end - start);
    const duration = Math.min(11000, 2000 + steps * 85);          // ~10.5 s for 10 hours
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);            // decelerate into the final value
    let frame = 0;
    const t0 = performance.now() + 400;                            // brief pause so the old total registers
    const tick = (now: number) => {
      const t = Math.min(1, Math.max(0, (now - t0) / duration));
      setValue(start + (end - start) * ease(t));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    setValue(start);
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [start, end, reduced]);

  const text = (end / 10).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const digitCount = [...text].filter((c) => /\d/.test(c)).length;
  let p = digitCount;          // wheel position: 0 = tenths, 1 = units, 2 = tens ...
  return (
    <span className="roll-number" aria-label={text} role="img">
      {[...text].map((c, i) => {
        if (!/\d/.test(c)) {
          // separators of digits not yet reached (e.g. the comma when rolling 999.9 -> 1,000.0) stay hidden
          const hidden = c !== "." && value < Math.pow(10, p);
          return <span key={i} className="roll-static" style={{ opacity: hidden ? 0 : 1 }} aria-hidden>{c}</span>;
        }
        p -= 1;
        const unit = Math.pow(10, p);
        const digit = Math.floor(value / unit) % 10;
        // Carry: a higher wheel turns only during the last tenth of travel of everything below it
        const below = value % unit;
        const frac = p === 0 ? value - Math.floor(value) : Math.max(0, below - (unit - 1));
        const offset = digit + frac;                                 // 0..10 on a 0-9,0 strip
        const leading = p > 1 && value < unit;                       // not yet reached: blank, not 0
        return (
          <span key={i} className="roll-digit" aria-hidden style={{ opacity: leading ? 0 : 1 }}>
            <span className="roll-strip" style={{ transform: `translateY(${-offset * ROW}em)` }}>
              {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0].map((n, k) => <span key={k}>{n}</span>)}
            </span>
          </span>
        );
      })}
    </span>
  );
}

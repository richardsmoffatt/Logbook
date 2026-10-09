import { useEffect, useState } from "react";

const ROW = 1.1; // digit row height in em; matches .roll-digit in styles.css

/**
 * Odometer-style number: each digit spins down to its value. Digits start in turn from the left;
 * each digit further right spins more and settles more slowly, so the last digit lands last.
 */
export default function RollingNumber({ text }: { text: string }) {
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [go, setGo] = useState(false);

  useEffect(() => {
    if (reduced) return;
    // Two frames so the start position is painted before the transition begins
    let inner = 0;
    const outer = requestAnimationFrame(() => { inner = requestAnimationFrame(() => setGo(true)); });
    return () => { cancelAnimationFrame(outer); cancelAnimationFrame(inner); };
  }, [text, reduced]);

  if (reduced) return <span className="roll-number">{text}</span>;

  const digits = [...text].filter((c) => /\d/.test(c)).length;
  let d = -1;
  return (
    <span className="roll-number" aria-label={text} role="img">
      {[...text].map((c, i) => {
        if (!/\d/.test(c)) return <span key={i} className="roll-static" aria-hidden>{c}</span>;
        d += 1;
        const target = Number(c);
        const spins = 1 + d;                                  // rightmost digits spin the most
        const last = d === digits - 1;
        const strip = [...Array(spins * 10 + target + 1).keys()].map((n) => n % 10);
        const duration = 1.0 + d * 0.55 + (last ? 0.9 : 0);    // ...and take longest to settle
        const delay = d * 0.12;                                // start in turn, left to right
        return (
          <span key={i} className="roll-digit" aria-hidden>
            <span
              className="roll-strip"
              style={{
                transform: `translateY(${go ? -(strip.length - 1) * ROW : 0}em)`,
                transition: go ? `transform ${duration}s cubic-bezier(0.12, 0.7, 0.18, 1) ${delay}s` : "none",
              }}
            >
              {strip.map((n, k) => <span key={k}>{n}</span>)}
            </span>
          </span>
        );
      })}
    </span>
  );
}

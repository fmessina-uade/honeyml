import { useEffect, useState } from 'react';
import { useInView } from '../lib/useInView';

interface CountUpProps {
  end: number;
  decimals?: number;
  suffix?: string;
  duration?: number;
  className?: string;
}

/**
 * Animated counter. Same easing as the public site, with thousands separators: the dashboard
 * shows figures in the millions and they are unreadable without them.
 */
export default function CountUp({
  end,
  decimals = 0,
  suffix = '',
  duration = 1800,
  className,
}: CountUpProps) {
  const { ref, inView } = useInView<HTMLSpanElement>(0.4);
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      setValue(end);
      return;
    }
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      // clamp both ends: requestAnimationFrame can hand back a timestamp from before the
      // performance.now() captured just above, and a negative t renders a negative figure
      const t = Math.min(1, Math.max(0, (now - start) / duration));
      setValue(end * (1 - Math.pow(1 - t, 3)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, end, duration]);

  return (
    <span ref={ref} className={className}>
      {value.toLocaleString('es-AR', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  );
}

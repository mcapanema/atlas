/**
 * Dependency-free inline-SVG sparkline. Decorative by contract: always
 * aria-hidden — the caller must render a text equivalent beside it.
 * Stroke follows currentColor so it inherits the surrounding semantic tone.
 */
// Min–max scaling stretches any wiggle to full height: a 3% drift labeled
// "steady" drew as a steep diagonal. Floor the visible span at 20% of the
// series' magnitude so the slope agrees with the trend word beside it.
const MIN_RELATIVE_SPAN = 0.2;

export function Sparkline({
  points,
  width = 96,
  height = 20,
}: {
  points: number[];
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const mid = (min + max) / 2;
  const span = Math.max(max - min, Math.abs(mid) * MIN_RELATIVE_SPAN) || 1;
  const low = mid - span / 2;
  const pad = 2;
  const coords = points
    .map((value, index) => {
      const x = pad + (index / (points.length - 1)) * (width - pad * 2);
      const y = pad + (1 - (value - low) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="sparkline"
    >
      <polyline
        points={coords}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

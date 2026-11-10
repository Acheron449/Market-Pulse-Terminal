import { normalise, type Tone, toneClasses } from "../lib/format";

const STROKE: Record<Tone, string> = {
  up: "#00E676",
  down: "#FF5252",
  flat: "#8B96A8",
};

interface Props {
  values: number[];
  tone: Tone;
  label: string;
}

/** Inline SVG sparkline: no library, no extra request (docs/tradingview.md §8). */
export function Sparkline({ values, tone, label }: Props) {
  if (values.length < 2) {
    return <div className="h-8" aria-hidden="true" />;
  }
  const points = normalise(values)
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 100;
      const y = 26 - value * 22;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      viewBox="0 0 100 28"
      preserveAspectRatio="none"
      className={`h-8 w-full ${toneClasses[tone]}`}
      role="img"
      aria-label={label}
    >
      <polyline
        points={points}
        fill="none"
        stroke={STROKE[tone]}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

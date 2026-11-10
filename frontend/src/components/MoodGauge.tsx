import type { Verdict } from "../types/market-snapshot";

const CENTER_X = 120;
const CENTER_Y = 118;
const RADIUS = 96;

function polar(angleDegrees: number): { x: number; y: number } {
  const radians = ((angleDegrees - 90) * Math.PI) / 180;
  return {
    x: CENTER_X + RADIUS * Math.cos(radians),
    y: CENTER_Y + RADIUS * Math.sin(radians),
  };
}

function arc(from: number, to: number): string {
  const start = polar(from);
  const end = polar(to);
  const largeArc = Math.abs(to - from) > 180 ? 1 : 0;
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${RADIUS} ${RADIUS} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

const VERDICT_TONE: Record<Verdict, string> = {
  BEARISH: "text-down",
  UNCERTAIN: "text-caution",
  NEUTRAL: "text-ink",
  BULLISH: "text-up",
  UNKNOWN: "text-muted",
};

interface Props {
  position: number;
  verdict: Verdict;
}

/** Gradient gauge with a needle, clamped to 2–98 like the reference (FR-19, FR-22). */
export function MoodGauge({ position, verdict }: Props) {
  const clamped = Math.max(2, Math.min(98, position));
  const angle = -90 + (clamped / 100) * 180;
  const needle = polar(angle);
  const unknown = verdict === "UNKNOWN";

  return (
    <svg
      viewBox="0 0 240 136"
      className="h-36 w-full max-w-[280px]"
      role="img"
      aria-label={`Market mood ${position} out of 100, verdict ${verdict}`}
    >
      <defs>
        <linearGradient id="mood-gradient" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#FF5252" />
          <stop offset="50%" stopColor="#F0B429" />
          <stop offset="100%" stopColor="#00E676" />
        </linearGradient>
      </defs>

      <path d={arc(-90, 90)} fill="none" stroke="#232A36" strokeWidth="14" strokeLinecap="round" />
      <path
        d={arc(-90, 90)}
        fill="none"
        stroke={unknown ? "#3A4252" : "url(#mood-gradient)"}
        strokeWidth="14"
        strokeLinecap="round"
        opacity={unknown ? 0.5 : 1}
      />

      {/* Band boundaries: 25, 44 and 60 (docs/sentiment.md §4). */}
      {[25, 44, 60].map((mark) => {
        const point = polar(-90 + (mark / 100) * 180);
        return <circle key={mark} cx={point.x} cy={point.y} r="1.4" fill="#0E1116" aria-hidden="true" />;
      })}

      <line
        x1={CENTER_X}
        y1={CENTER_Y}
        x2={needle.x}
        y2={needle.y}
        stroke={unknown ? "#8B96A8" : "#E6EAF2"}
        strokeWidth="3"
        strokeLinecap="round"
      />
      <circle cx={CENTER_X} cy={CENTER_Y} r="6" fill="#E6EAF2" />

      <text
        x={CENTER_X}
        y={CENTER_Y - 28}
        textAnchor="middle"
        className={`tabular fill-current font-mono text-2xl ${VERDICT_TONE[verdict]}`}
      >
        {position}
      </text>
      <text x="26" y="132" className="fill-current text-[9px] text-muted">
        BEARISH
      </text>
      <text x="182" y="132" className="fill-current text-[9px] text-muted">
        BULLISH
      </text>
    </svg>
  );
}

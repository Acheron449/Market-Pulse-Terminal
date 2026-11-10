import { formatTime } from "../lib/format";
import type { SectionStatus, Sentiment } from "../types/market-snapshot";
import { StatusChip, StaleBadge } from "./Badges";
import { MoodGauge } from "./MoodGauge";

const COMPONENT_LABEL: Record<string, string> = {
  volatility: "Volatility",
  trend: "Trend",
  momentum: "Day momentum",
  riskAppetite: "Risk appetite",
  headlineTone: "Headline tone",
};

interface Props {
  sentiment: Sentiment;
  status?: SectionStatus;
}

export function MoodPanel({ sentiment, status }: Props) {
  const components = sentiment.components ?? [];
  const directionless = sentiment.verdict === "UNKNOWN";

  return (
    <section className="panel p-5" aria-label="Market mood">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-[11px] font-semibold tracking-widest text-muted">MARKET MOOD</h2>
          {status === "stale" ? <StaleBadge /> : null}
        </div>
        <StatusChip status={sentiment.marketStatus} />
      </div>

      <div className="mt-3 grid gap-5 lg:grid-cols-[280px_1fr]">
        <div className="flex flex-col items-center">
          <MoodGauge position={sentiment.position} verdict={sentiment.verdict} />
          <p
            className={`mt-1 text-sm font-semibold tracking-[0.2em] ${
              directionless ? "text-muted" : "text-ink"
            }`}
          >
            {sentiment.verdict}
          </p>
          {directionless ? (
            <p className="mt-1 text-center text-xs text-muted">
              Not enough signals to call a direction.
            </p>
          ) : null}
        </div>

        <div className="space-y-4">
          <p className="text-sm leading-relaxed text-ink/90">
            {sentiment.summary || "Mood summary unavailable for this snapshot."}
          </p>

          {components.length > 0 ? (
            <ul className="grid gap-2 sm:grid-cols-2" aria-label="Mood components">
              {components.map((component) => (
                <li key={component.name} className="space-y-1">
                  <div className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="text-muted">{COMPONENT_LABEL[component.name] ?? component.name}</span>
                    <span className="tabular font-mono text-ink">
                      {component.score}
                      <span className="ml-1 text-muted">{(component.weight * 100).toFixed(0)}%</span>
                    </span>
                  </div>
                  <div className="h-1 rounded bg-edge" aria-hidden="true">
                    <div
                      className="h-1 rounded bg-volume/70"
                      style={{ width: `${Math.max(2, Math.min(100, component.score))}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          ) : null}

          {sentiment.headlines.length > 0 ? (
            <ul className="space-y-1.5" aria-label="Headlines">
              {sentiment.headlines.map((headline) => (
                <li key={headline.url} className="text-xs">
                  <a
                    href={headline.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-ink/90 underline-offset-2 hover:text-volume hover:underline"
                  >
                    {headline.title}
                  </a>
                  <span className="ml-2 text-muted">
                    {headline.source} · {formatTime(headline.publishedAt)}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}

          <p className="text-[11px] text-muted">
            Heuristic composite of public data, not a prediction and not investment advice.
          </p>
        </div>
      </div>
    </section>
  );
}

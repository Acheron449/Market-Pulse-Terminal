import { formatPercent, formatPrice, formatVolume, toneClasses, toneFor, truncate } from "../lib/format";
import type { MostActiveRow, Mover, SectionStatus } from "../types/market-snapshot";
import { StaleBadge } from "./Badges";

type Kind = "gainers" | "losers" | "mostActive";

const TITLES: Record<Kind, string> = {
  gainers: "TOP GAINERS",
  losers: "TOP LOSERS",
  mostActive: "MOST ACTIVE",
};

interface Props {
  kind: Kind;
  rows: Array<Mover | MostActiveRow>;
  status?: SectionStatus;
  onOpen?: (symbol: string) => void;
}

function hasVolume(row: Mover | MostActiveRow): row is MostActiveRow {
  return "volume" in row;
}

export function MoversTable({ kind, rows, status, onOpen }: Props) {
  const maxMove = rows.reduce(
    (max, row) => Math.max(max, Math.abs(row.changePercent) || 0),
    0.01,
  );

  return (
    <section className="panel p-4" aria-label={TITLES[kind]}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[11px] font-semibold tracking-widest text-muted">{TITLES[kind]}</h2>
        {status === "stale" ? <StaleBadge /> : null}
      </div>

      {rows.length === 0 ? (
        <p className="mt-4 text-xs text-muted">No qualifying symbols in this snapshot.</p>
      ) : (
        <ol className="mt-3 space-y-1">
          {rows.map((row, index) => {
            const tone = toneFor(row.changePercent);
            const width = Math.min(100, (Math.abs(row.changePercent) / maxMove) * 100);
            const secondary = hasVolume(row)
              ? formatVolume(row.volume)
              : formatPercent(row.changePercent);
            const tooltip = hasVolume(row)
              ? `${row.symbol} · day range ${formatPrice(row.dayLow)}–${formatPrice(row.dayHigh)} · volume ${formatVolume(row.volume)}`
              : `${row.symbol} · ${formatPercent(row.changePercent)}`;

            return (
              <li key={`${row.symbol}-${index}`} className="group relative">
                {/* Row content stays plain text so screen readers hear it as written; a
                    separate labelled button makes the whole row the click target, the
                    same pattern as the index cards (WCAG 2.5.3). */}
                <div className="grid w-full grid-cols-[16px_52px_1fr_auto] items-baseline gap-2 rounded px-1 py-1.5 group-hover:bg-edge/40">
                  <span className="tabular font-mono text-[10px] text-muted">{index + 1}</span>
                  <span className="font-mono text-xs font-semibold text-ink">{row.symbol}</span>
                  <span className="truncate text-[11px] text-muted">{truncate(row.name, 20)}</span>
                  <span className="tabular flex flex-col items-end font-mono text-[11px]">
                    <span className="text-ink">{formatPrice(row.price)}</span>
                    <span className={toneClasses[tone]}>{secondary}</span>
                  </span>
                  <span
                    className="pointer-events-none absolute inset-x-1 bottom-0 h-px bg-edge"
                    aria-hidden="true"
                  >
                    <span
                      className={`block h-px ${tone === "up" ? "bg-up/60" : tone === "down" ? "bg-down/60" : "bg-muted/40"}`}
                      style={{ width: `${width}%` }}
                    />
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => onOpen?.(row.symbol)}
                  title={tooltip}
                  aria-label={`Open the ${row.symbol} chart`}
                  className="absolute inset-0 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-volume"
                />
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

import {
  arrowFor,
  formatPercent,
  formatPrice,
  formatSigned,
  toneClasses,
  toneFor,
} from "../lib/format";
import type { IndexCard as IndexCardModel } from "../types/market-snapshot";
import { ProxyBadge, StaleBadge } from "./Badges";
import { Sparkline } from "./Sparkline";

interface Props {
  card: IndexCardModel;
  stale?: boolean;
  onOpen?: (symbol: string) => void;
}

export function IndexCard({ card, stale = false, onOpen }: Props) {
  const tone = toneFor(card.changePercent, card.invert);

  return (
    <article
      className="panel group relative flex flex-col gap-3 p-4 text-left transition-colors hover:border-edge/80 hover:bg-panel"
      aria-label={`${card.label}, ${formatPrice(card.price)}, ${formatPercent(card.changePercent)}`}
    >
      <header className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-[11px] font-semibold tracking-widest text-muted">{card.label}</h2>
          <p className="mt-0.5 font-mono text-[10px] text-muted">{card.symbol}</p>
        </div>
        <div className="flex items-center gap-1">
          {card.isProxy ? <ProxyBadge /> : null}
          {stale ? <StaleBadge /> : null}
        </div>
      </header>

      <div>
        <p className={`tabular font-mono text-2xl font-semibold ${toneClasses[tone]}`}>
          {formatPrice(card.price)}
        </p>
        <p className={`tabular mt-1 flex items-center gap-1.5 font-mono text-xs ${toneClasses[tone]}`}>
          <span aria-hidden="true">{arrowFor(card.changePercent)}</span>
          <span>{formatSigned(card.change)}</span>
          <span className="text-muted">·</span>
          <span>{formatPercent(card.changePercent)}</span>
        </p>
      </div>

      <Sparkline
        values={card.sparkline}
        tone={tone}
        label={`${card.label} intraday trend, ${card.sparkline.length} points`}
      />

      <button
        type="button"
        onClick={() => onOpen?.(card.symbol)}
        className="absolute inset-0 rounded-2xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-volume"
        aria-label={`Open the ${card.label} chart`}
      />
    </article>
  );
}

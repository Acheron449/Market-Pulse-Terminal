import {
  AreaSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { useUiConfig } from "../hooks/useUiConfig";
import { formatPrice } from "../lib/format";
import { useChartHistory, useChartSymbol } from "./useChartData";

const RESOLUTION_LABEL: Record<string, string> = {
  "1": "1m",
  "5": "5m",
  "15": "15m",
  "60": "1h",
  "1D": "1D",
};

interface Props {
  symbol: string;
  onClose: () => void;
}

export default function ChartPanel({ symbol, onClose }: Props) {
  const config = useUiConfig();
  const [resolution, setResolution] = useState(config.chartResolutions.includes("5") ? "5" : "1");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  const info = useChartSymbol(symbol);
  const history = useChartHistory(symbol, resolution);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height: 380,
      layout: {
        background: { color: "transparent" },
        textColor: "#8B96A8",
      },
      grid: {
        vertLines: { color: "rgba(35,42,54,0.6)" },
        horzLines: { color: "rgba(35,42,54,0.6)" },
      },
      rightPriceScale: { borderColor: "#232A36" },
      timeScale: { borderColor: "#232A36", timeVisible: true, secondsVisible: false },
    });
    const series = chart.addSeries(AreaSeries, {
      lineColor: "#22D3EE",
      lineWidth: 2,
      topColor: "rgba(34,211,238,0.28)",
      bottomColor: "rgba(34,211,238,0.02)",
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: containerRef.current?.clientWidth ?? 0 });
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !history.data) return;
    seriesRef.current.setData(
      history.data.bars.map((bar) => ({
        time: Math.floor(bar.time / 1000) as UTCTimestamp,
        value: bar.close,
      })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [history.data]);

  const lastBar = history.data?.bars.at(-1);
  const symbolInfo = info.data;
  // A descriptor can legitimately be missing (movers are not curated); say so instead
  // of showing a loading label forever.
  const detail = symbolInfo
    ? `${symbolInfo.description} · ${symbolInfo.session} ET${symbolInfo.isProxy ? " · ETF proxy" : ""}`
    : info.isError
      ? "Symbol details unavailable."
      : "Loading symbol…";
  const feedLabel = !symbolInfo
    ? info.isError
      ? "Unavailable"
      : "Loading"
    : symbolInfo.mode === "replay"
      ? "Replay"
      : symbolInfo.dataStatus === "delayed_streaming" && symbolInfo.delay > 0
      ? `Delayed ${Math.round(symbolInfo.delay / 60)} min`
      : symbolInfo.dataStatus === "endofday"
        ? "End of day"
        : "Streaming";

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 p-4 sm:p-8"
      role="dialog"
      aria-modal="true"
      aria-label={`${symbol} chart`}
    >
      <div className="panel w-full max-w-4xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-mono text-sm font-semibold text-ink">{symbol}</h2>
            <p className="text-[11px] text-muted">{detail}</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-volume/40 px-2 py-0.5 text-[10px] font-semibold tracking-wider text-volume">
              {feedLabel.toUpperCase()}
            </span>
            {config.chartResolutions.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setResolution(option)}
                aria-pressed={option === resolution}
                className={`rounded px-2 py-1 font-mono text-[11px] ${
                  option === resolution
                    ? "bg-volume/20 text-volume"
                    : "text-muted hover:bg-edge/60 hover:text-ink"
                }`}
              >
                {RESOLUTION_LABEL[option] ?? option}
              </button>
            ))}
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-edge px-2 py-1 text-[11px] text-ink hover:bg-edge/60"
            >
              Close
            </button>
          </div>
        </div>

        {lastBar ? (
          <p className="tabular mt-2 font-mono text-xs text-muted">
            Last close <span className="text-ink">{formatPrice(lastBar.close)}</span> ·{" "}
            {history.data?.source} · {history.data?.status}
          </p>
        ) : null}

        {history.isPending ? (
          <div className="mt-3 h-[380px] animate-pulse rounded-xl bg-edge/40" aria-busy="true" />
        ) : history.isError ? (
          <div className="mt-3 flex h-[380px] flex-col items-center justify-center gap-3 rounded-xl border border-edge text-xs text-muted">
            <p>Chart data unavailable.</p>
            <button
              type="button"
              onClick={history.refetch}
              className="rounded border border-edge px-3 py-1.5 text-ink hover:bg-edge/60"
            >
              Retry
            </button>
          </div>
        ) : history.data?.noData ? (
          <div className="mt-3 flex h-[380px] items-center justify-center rounded-xl border border-edge text-xs text-muted">
            No bars for this resolution.
          </div>
        ) : (
          <div ref={containerRef} className="mt-3 w-full" />
        )}

        <p className="mt-3 text-[10px] text-muted">
          Charting by{" "}
          <a
            href="https://www.tradingview.com/"
            target="_blank"
            rel="noreferrer noopener"
            className="underline-offset-2 hover:text-volume hover:underline"
          >
            TradingView Lightweight Charts
          </a>
          . Data comes from our backend providers, not TradingView.
        </p>
      </div>
    </div>
  );
}

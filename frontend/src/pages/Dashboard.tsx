import { Suspense, lazy, useCallback } from "react";
import { useLocation } from "wouter";

import { ErrorBanner, DashboardSkeleton, ErrorCard } from "../components/Feedback";
import { Footer } from "../components/Footer";
import { Header } from "../components/Header";
import { IndexCard } from "../components/IndexCard";
import { MoodPanel } from "../components/MoodPanel";
import { MoversTable } from "../components/MoversTable";
import { useRefresh } from "../hooks/useRefresh";
import { useSnapshot } from "../hooks/useSnapshot";
import { useUiConfig } from "../hooks/useUiConfig";

const ChartPanel = lazy(() => import("../chart/ChartPanel"));

interface Props {
  chartSymbol?: string;
}

export function Dashboard({ chartSymbol }: Props) {
  const [, navigate] = useLocation();
  const config = useUiConfig();
  const { snapshot, isInitialLoading, error, streamConnected, refetch } = useSnapshot();
  const refresh = useRefresh(config.refreshCooldownSeconds);

  const openChart = useCallback(
    (symbol: string) => navigate(`/chart/${encodeURIComponent(symbol)}`),
    [navigate],
  );
  const closeChart = useCallback(() => navigate("/"), [navigate]);

  return (
    <div className="mx-auto flex min-h-screen max-w-terminal flex-col gap-5 px-4 py-6 sm:px-6">
      <Header
        snapshot={snapshot}
        streamConnected={streamConnected}
        onRefresh={refresh.refresh}
        isRefreshing={refresh.isRefreshing}
        cooldownSeconds={refresh.cooldownSeconds}
      />

      {refresh.error ? (
        <div className="rounded-xl border border-down/30 bg-down/10 px-4 py-2 text-xs text-down" role="alert">
          Refresh failed: {refresh.error.message}
        </div>
      ) : null}

      {isInitialLoading && !snapshot ? (
        <DashboardSkeleton />
      ) : !snapshot ? (
        <ErrorCard
          message={error?.message ?? "The snapshot could not be loaded."}
          onRetry={refetch}
        />
      ) : (
        <>
          <ErrorBanner errors={snapshot.errors} />

          <section aria-label="Index cards" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {snapshot.indexes.map((card) => (
              <IndexCard
                key={card.symbol}
                card={card}
                stale={snapshot.status.indexes === "stale"}
                onOpen={openChart}
              />
            ))}
          </section>

          <MoodPanel sentiment={snapshot.sentiment} status={snapshot.status.sentiment} />

          <section aria-label="Movers" className="grid gap-3 lg:grid-cols-3">
            <MoversTable
              kind="gainers"
              rows={snapshot.gainers}
              status={snapshot.status.movers}
              onOpen={openChart}
            />
            <MoversTable
              kind="losers"
              rows={snapshot.losers}
              status={snapshot.status.movers}
              onOpen={openChart}
            />
            <MoversTable
              kind="mostActive"
              rows={snapshot.mostActive}
              status={snapshot.status.movers}
              onOpen={openChart}
            />
          </section>

          <Footer snapshot={snapshot} disclaimer={config.disclaimer} />
        </>
      )}

      {chartSymbol ? (
        <Suspense
          fallback={
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
              <p className="text-xs text-muted">Loading chart…</p>
            </div>
          }
        >
          <ChartPanel symbol={chartSymbol} onClose={closeChart} />
        </Suspense>
      ) : null}
    </div>
  );
}

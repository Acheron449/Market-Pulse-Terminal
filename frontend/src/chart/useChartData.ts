/**
 * Chart data hook (FR-28). Matches the snapshot hooks: a plain fetch with an abort
 * signal and explicit loading/error state, instead of a query cache. The chart is a
 * single on-demand request, so a cache adds states we do not control and cannot test.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import type { UiConfig } from "../lib/api";

/** Five days of history covers a long weekend plus holidays at every resolution. */
const HISTORY_WINDOW_SECONDS = 60 * 60 * 24 * 5;

export interface ChartBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface ChartHistory {
  symbol: string;
  resolution: string;
  bars: ChartBar[];
  noData: boolean;
  source: string;
  status: string;
  asOf: string;
}

export interface ChartSymbolInfo {
  symbol: string;
  description: string;
  type: string;
  session: string;
  visiblePlotsSet: string;
  dataStatus: string;
  /** "live" once providers are enabled; "replay" for the recorded fixture. */
  mode: string;
  delay: number;
  isProxy: boolean;
  source: string;
}

export interface ChartResource<T> {
  data: T | undefined;
  isPending: boolean;
  isError: boolean;
  refetch: () => void;
}

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" }, signal });
  if (!response.ok) {
    throw new Error(`${path} failed (${response.status})`);
  }
  return (await response.json()) as T;
}

function useChartResource<T>(path: string | null): ChartResource<T> {
  const [nonce, setNonce] = useState(0);
  const [data, setData] = useState<T>();
  const [isPending, setIsPending] = useState(true);
  const [isError, setIsError] = useState(false);

  const refetch = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    let active = true;
    setIsPending(true);
    setIsError(false);
    getJson<T>(path, controller.signal)
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setIsPending(false);
      })
      .catch(() => {
        // An abort is a navigation, not a failure: leave the state for the next mount.
        if (!active || controller.signal.aborted) return;
        setIsError(true);
        setIsPending(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, nonce]);

  return { data, isPending, isError, refetch };
}

export function useChartHistory(
  symbol: string,
  resolution: string,
  enabled = true,
): ChartResource<ChartHistory> {
  const path = useMemo(() => {
    const to = Math.floor(Date.now() / 1000);
    const from = to - HISTORY_WINDOW_SECONDS;
    return `/api/chart/history?symbol=${encodeURIComponent(symbol)}&resolution=${resolution}&from=${from}&to=${to}&countBack=300`;
  }, [symbol, resolution]);
  return useChartResource<ChartHistory>(enabled ? path : null);
}

export function useChartSymbol(symbol: string): ChartResource<ChartSymbolInfo> {
  const path = useMemo(
    () => `/api/chart/symbols/${encodeURIComponent(symbol)}`,
    [symbol],
  );
  return useChartResource<ChartSymbolInfo>(path);
}

export function resolutionsFrom(config: UiConfig): string[] {
  return config.chartResolutions.length > 0 ? config.chartResolutions : ["5"];
}

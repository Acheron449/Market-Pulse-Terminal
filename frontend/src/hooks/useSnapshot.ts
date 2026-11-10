import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchSnapshot } from "../lib/api";
import type { MarketSnapshot } from "../types/market-snapshot";

const POLL_INTERVAL_MS = 30_000;

export interface SnapshotState {
  snapshot: MarketSnapshot | undefined;
  isInitialLoading: boolean;
  error: Error | null;
  streamConnected: boolean;
  refetch: () => void;
}

/**
 * Snapshot transport (FR-14, FR-15): SSE pushes new snapshots, polling every 30 s is the
 * fallback and is paused while the tab is hidden.
 */
export function useSnapshot(): SnapshotState {
  const queryClient = useQueryClient();
  const [streamConnected, setStreamConnected] = useState(false);

  const query = useQuery<MarketSnapshot>({
    queryKey: ["snapshot"],
    queryFn: ({ signal }) => fetchSnapshot(signal),
    refetchInterval: () => (typeof document !== "undefined" && document.hidden ? false : POLL_INTERVAL_MS),
    staleTime: 15_000,
  });

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/stream");

    const onSnapshot = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as MarketSnapshot;
        if (payload?.schemaVersion === 1) {
          queryClient.setQueryData(["snapshot"], payload);
          setStreamConnected(true);
        }
      } catch {
        // A malformed frame is ignored; the next one or the poll will recover.
      }
    };

    source.addEventListener("snapshot", onSnapshot as EventListener);
    source.onopen = () => setStreamConnected(true);
    source.onerror = () => {
      setStreamConnected(false);
      // EventSource retries on its own; polling keeps the UI current meanwhile.
    };

    return () => {
      source.removeEventListener("snapshot", onSnapshot as EventListener);
      source.close();
      setStreamConnected(false);
    };
  }, [queryClient]);

  return {
    snapshot: query.data,
    isInitialLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
    streamConnected,
    refetch: () => void query.refetch(),
  };
}

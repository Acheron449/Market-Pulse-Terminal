import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";

import { RefreshCooldownError, triggerRefresh } from "../lib/api";
import type { MarketSnapshot } from "../types/market-snapshot";

export interface RefreshState {
  refresh: () => void;
  isRefreshing: boolean;
  cooldownSeconds: number;
  error: Error | null;
}

/**
 * Manual refresh with the server's cooldown (FR-16). The button is disabled while the
 * cooldown runs, and a 429 from the server resynchronises the countdown.
 */
export function useRefresh(fallbackCooldownSeconds = 10): RefreshState {
  const queryClient = useQueryClient();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [cooldownUntil, setCooldownUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (cooldownUntil <= Date.now()) return;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [cooldownUntil]);

  const refresh = useCallback(() => {
    setIsRefreshing(true);
    setError(null);
    triggerRefresh()
      .then((snapshot: MarketSnapshot) => {
        queryClient.setQueryData(["snapshot"], snapshot);
        setCooldownUntil(Date.now() + fallbackCooldownSeconds * 1000);
      })
      .catch((cause: unknown) => {
        if (cause instanceof RefreshCooldownError) {
          setCooldownUntil(Date.now() + cause.retryAfterSeconds * 1000);
        } else {
          setError(cause instanceof Error ? cause : new Error("refresh failed"));
        }
      })
      .finally(() => setIsRefreshing(false));
  }, [fallbackCooldownSeconds, queryClient]);

  const cooldownSeconds = useMemo(() => {
    const remaining = cooldownUntil - now;
    return remaining > 0 ? Math.ceil(remaining / 1000) : 0;
  }, [cooldownUntil, now]);

  return {
    refresh,
    isRefreshing,
    cooldownSeconds,
    error,
  };
}

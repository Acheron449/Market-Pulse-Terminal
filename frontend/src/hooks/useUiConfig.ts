import { useQuery } from "@tanstack/react-query";

import { fetchUiConfig, type UiConfig } from "../lib/api";

const FALLBACK: UiConfig = {
  schemaVersion: 1,
  refreshCooldownSeconds: 10,
  pollingFallbackSeconds: 30,
  chartEngine: "lightweight",
  chartResolutions: ["1", "5", "15", "60", "1D"],
  enableTradingViewWidget: false,
  liveDataEnabled: false,
  disclaimer:
    "Informational only. Not investment advice. Data may be delayed; check the feed disclosure in the footer.",
};

/**
 * Non-secret UI flags (SRS §7.1). A failure is not fatal: safe defaults keep the
 * dashboard working when /api/config is unavailable.
 */
export function useUiConfig(): UiConfig {
  const query = useQuery<UiConfig>({
    queryKey: ["config"],
    queryFn: fetchUiConfig,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });
  return query.data ?? FALLBACK;
}

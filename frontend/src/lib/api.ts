/**
 * Typed access to the backend. The browser never talks to a provider (AGENTS.md rule 1).
 */

import type { MarketSnapshot } from "../types/market-snapshot";

/** SRS §1.3: the reference build times out after six seconds. */
export const REQUEST_TIMEOUT_MS = 6000;

export class RefreshCooldownError extends Error {
  constructor(readonly retryAfterSeconds: number) {
    super(`refresh cooldown: retry in ${retryAfterSeconds}s`);
    this.name = "RefreshCooldownError";
  }
}

async function request(path: string, signal?: AbortSignal): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort);
  try {
    return await fetch(path, { signal: controller.signal, headers: { Accept: "application/json" } });
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}

export async function fetchSnapshot(signal?: AbortSignal): Promise<MarketSnapshot> {
  const response = await request("/api/market", signal);
  if (!response.ok) {
    throw new Error(`market request failed (${response.status})`);
  }
  return (await response.json()) as MarketSnapshot;
}

/** FR-16: force a rebuild; a 429 carries the remaining cooldown. */
export async function triggerRefresh(): Promise<MarketSnapshot> {
  const response = await request("/api/market?refresh=1");
  if (response.status === 429) {
    const retryAfter = Number.parseInt(response.headers.get("Retry-After") ?? "10", 10);
    throw new RefreshCooldownError(Number.isFinite(retryAfter) ? retryAfter : 10);
  }
  if (!response.ok) {
    throw new Error(`refresh failed (${response.status})`);
  }
  return (await response.json()) as MarketSnapshot;
}

export interface UiConfig {
  schemaVersion: number;
  refreshCooldownSeconds: number;
  pollingFallbackSeconds: number;
  chartEngine: "lightweight" | "advanced";
  chartResolutions: string[];
  enableTradingViewWidget: boolean;
  liveDataEnabled: boolean;
  disclaimer: string;
}

export async function fetchUiConfig(): Promise<UiConfig> {
  const response = await request("/api/config");
  if (!response.ok) {
    throw new Error(`config request failed (${response.status})`);
  }
  return (await response.json()) as UiConfig;
}

import { expect, test } from "@playwright/test";

/**
 * Chart drill-down (FR-28, docs/tradingview.md §3).
 *
 * In replay mode there is no chart data: the fixture records the snapshot only, so
 * `/api/chart/history` answers 502. That is the documented behaviour, and the dialog has
 * to show it honestly: a loading state that ends, an error with a Retry, and a Close that
 * returns to the dashboard. A slow route lets the loading state be observed instead of
 * raced against the error.
 */

test("opens a chart, shows loading, then the replay error state, then closes", async ({
  page,
}) => {
  await page.route(/\/api\/chart\/history\?/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.continue();
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Open the S&P 500 chart" }).click();

  const dialog = page.getByRole("dialog", { name: "^GSPC chart" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "^GSPC" })).toBeVisible();
  // Replay must never claim a live feed (AGENTS.md rule 9).
  await expect(dialog.getByText("REPLAY", { exact: true })).toBeVisible();
  await expect(dialog.getByText(/S&P 500 · \d{4}-\d{4} ET/)).toBeVisible();

  await expect(dialog.locator('[aria-busy="true"]')).toBeVisible();
  await expect(dialog.getByText("Chart data unavailable.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Retry" })).toBeVisible();

  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("region", { name: "Index cards" })).toBeVisible();
});

test("switching resolution refetches and keeps an honest error state", async ({ page }) => {
  const historyRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/chart/history")) historyRequests.push(request.url());
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Open the VIX chart" }).click();
  const dialog = page.getByRole("dialog", { name: "^VIX chart" });
  await expect(dialog.getByText("Chart data unavailable.")).toBeVisible();

  await dialog.getByRole("button", { name: "1D" }).click();
  await expect(dialog.getByRole("button", { name: "1D" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect
    .poll(() => historyRequests.filter((url) => url.includes("resolution=1D")).length)
    .toBe(1);
  await expect(dialog.getByText("Chart data unavailable.")).toBeVisible();
});

test("opens a chart from a mover row and degrades for symbols outside the curated list", async ({
  page,
}) => {
  await page.goto("/");
  const row = page.getByRole("region", { name: "TOP GAINERS" }).getByRole("button").first();
  const label = (await row.getAttribute("aria-label")) ?? "";
  // "Open the NVDA chart"
  const symbol = /^Open the ([A-Z.]{1,8}) chart$/.exec(label)?.[1] ?? "";
  expect(symbol, `row label was "${label}"`).not.toBe("");

  await row.click();
  const dialog = page.getByRole("dialog", { name: `${symbol} chart` });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: symbol })).toBeVisible();
  // Not every mover has a curated descriptor; the panel must say so rather than spin.
  await expect(dialog.getByText("Symbol details unavailable.")).toBeVisible();
  await expect(dialog.getByText("Loading symbol…")).toHaveCount(0);
  await expect(dialog.getByText("Chart data unavailable.")).toBeVisible();
});

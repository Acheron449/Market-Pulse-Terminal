import { expect, test } from "@playwright/test";

import { escapeRegExp } from "./helpers";

/**
 * Replay-mode contract (docs/SRS.md §5, §7.2; README "Quick start").
 *
 * The backend serves the recorded provider payload in flow: every section is populated but
 * marked stale, and the banner says so. These are the states the docs promise, asserted
 * against the real app rather than a component harness.
 */

const LABELS = ["S&P 500", "NASDAQ", "DOW JONES", "RUSSELL 2000", "VIX"];

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Index cards" })).toBeVisible();
});

test("renders the five index cards with a price, change and sparkline", async ({ page }) => {
  const cards = page.getByRole("region", { name: "Index cards" }).getByRole("article");
  await expect(cards).toHaveCount(5);

  for (const label of LABELS) {
    const name = new RegExp(`^${escapeRegExp(label)},`);
    const card = page.getByRole("article", { name });
    await expect(card, `${label} card is visible`).toBeVisible();
    // price and signed percentage, e.g. "7,475.46, -0.33%".
    await expect(
      card,
      `${label} card exposes price and change`,
    ).toHaveAccessibleName(
      new RegExp(`^${escapeRegExp(label)}, [\\d,]+\\.\\d{2}, [+-]\\d+\\.\\d{2}%$`),
    );
    await expect(
      card.getByRole("img", {
        name: new RegExp(`${escapeRegExp(label)} intraday trend, \\d+ points`),
      }),
      `${label} sparkline is exposed as an image with a label`,
    ).toBeVisible();
  }
});

test("shows the mood gauge value, its verdict and the after-hours market status", async ({
  page,
}) => {
  const mood = page.getByRole("region", { name: "Market mood" });
  const gauge = mood.getByRole("img", {
    name: /Market mood \d+ out of 100, verdict (BEARISH|UNCERTAIN|NEUTRAL|BULLISH|UNKNOWN)/,
  });
  await expect(gauge).toBeVisible();

  const label = (await gauge.getAttribute("aria-label")) ?? "";
  const match = /Market mood (\d+) out of 100, verdict ([A-Z]+)/.exec(label);
  expect(match, `gauge label was "${label}"`).not.toBeNull();

  const position = Number(match?.[1]);
  expect(position).toBeGreaterThanOrEqual(0);
  expect(position).toBeLessThanOrEqual(100);

  const verdict = match?.[2] ?? "";
  await expect(mood.getByText(verdict, { exact: true }).first()).toBeVisible();
  // The recorded fixture is an after-hours capture, so the status chip must say so.
  await expect(mood.getByText("AFTER HOURS", { exact: true })).toBeVisible();
});

test("lists gainers, losers and most active rows with the promised fields", async ({ page }) => {
  for (const name of ["TOP GAINERS", "TOP LOSERS"]) {
    const table = page.getByRole("region", { name });
    const firstRow = table.getByRole("listitem").first();
    await expect(firstRow, `${name} has a row`).toBeVisible();
    // Rank, symbol, name, price and signed change are visible row text.
    await expect(firstRow).toContainText(/^\d+[A-Z.]{1,6}/);
    await expect(firstRow).toContainText(/[+-]\d+\.\d{2}%/);
    await expect(firstRow.getByRole("button")).toHaveAccessibleName(
      /^Open the [A-Z.]{1,6} chart$/,
    );
  }

  const mostActive = page.getByRole("region", { name: "MOST ACTIVE" });
  const activeRow = mostActive.getByRole("listitem").first();
  await expect(activeRow).toBeVisible();
  await expect(activeRow).toContainText(/[\d.]+[KMB]/);
  // FR-10: the most-active rows carry volume plus day low/high in the tooltip.
  await expect(activeRow.getByRole("button")).toHaveAttribute(
    "title",
    /day range .+–.+ · volume /,
  );
});

test("discloses that the data is a replay, not a live feed", async ({ page }) => {
  const banner = page.getByRole("status").filter({ hasText: "Some sections couldn't load" });
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("replaying recorded provider data captured at");
  await expect(banner).toContainText("no live provider is configured");
});

test("keeps the disclaimer and feed disclosure in the footer", async ({ page }) => {
  const footer = page.getByRole("contentinfo");
  await expect(footer).toContainText("Informational only. Not investment advice.");
  await expect(footer).toContainText(/Data as of/);
  await expect(footer).toContainText(/delayed up to \d+ minutes|real-time where the feed allows/);
  await expect(footer.getByRole("link", { name: "TradingView" })).toHaveAttribute(
    "href",
    "https://www.tradingview.com/",
  );
});

test("enforces the manual refresh cooldown in the UI and on the API", async ({ page }) => {
  await page.getByRole("button", { name: "Refresh", exact: true }).click();

  const coolingDown = page.getByRole("button", { name: /^Refresh in \d+s$/ });
  await expect(coolingDown).toBeVisible();
  await expect(coolingDown).toBeDisabled();

  // FR-16: the server owns the cooldown, so a second forced refresh must be refused.
  const response = await page.request.get("/api/market?refresh=1");
  expect(response.status()).toBe(429);
  expect(response.headers()["retry-after"]).toMatch(/^\d+$/);
});

test("resynchronises the countdown when the server answers 429", async ({ page }) => {
  await page.route(/\/api\/market\?refresh=1$/, (route) =>
    route.fulfill({
      status: 429,
      headers: { "Retry-After": "4" },
      contentType: "application/json",
      body: JSON.stringify({ detail: "cooldown" }),
    }),
  );

  await page.getByRole("button", { name: "Refresh", exact: true }).click();

  // 4s becomes 3s within the first second; accept either reading.
  await expect(page.getByRole("button", { name: /^Refresh in [34]s$/ })).toBeDisabled();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

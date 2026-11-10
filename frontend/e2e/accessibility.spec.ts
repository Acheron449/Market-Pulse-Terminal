import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { WCAG_TAGS, blockingViolations, describeViolations } from "./helpers";

/**
 * Accessibility gate (timeline Phase 5: "Accessibility pass").
 *
 * Runs axe-core against the same served pages the behaviour suite drives and fails on
 * serious or critical WCAG 2.1/2.2 A/AA violations. Advisory findings stay visible in the
 * output without blocking, so a reviewer can see the difference.
 */

test("dashboard has no serious or critical accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Index cards" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Market mood" })).toBeVisible();

  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  const blocking = blockingViolations(results);

  expect(describeViolations(blocking)).toEqual([]);
  test.info().annotations.push({
    type: "axe",
    description: `${results.violations.length} total violation(s), ${blocking.length} blocking`,
  });
});

test("chart dialog has no serious or critical accessibility violations", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open the S&P 500 chart" }).click();

  const dialog = page.getByRole("dialog", { name: "^GSPC chart" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Chart data unavailable.")).toBeVisible();

  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  const blocking = blockingViolations(results);

  expect(describeViolations(blocking)).toEqual([]);
});

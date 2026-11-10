import type { AxeResults, Result } from "axe-core";

/** WCAG 2.1 and 2.2 A/AA: the rules a public dashboard is expected to meet. */
export const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** The bar we enforce: everything blocking, nothing merely advisory. */
export function blockingViolations(results: AxeResults): Result[] {
  return results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
}

/** Readable failure output: rule, impact, help text and the offending selectors. */
export function describeViolations(violations: Result[]): string[] {
  return violations.map((violation) => {
    const targets = violation.nodes
      .slice(0, 4)
      .map((node) => node.target.join(" "))
      .join(" | ");
    return `${violation.id} [${violation.impact ?? "unknown"}] ${violation.help} → ${targets}`;
  });
}

/** Escape a literal for use inside a RegExp (card labels contain & and spaces). */
export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

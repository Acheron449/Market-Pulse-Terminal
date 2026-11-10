import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { IndexCard as IndexCardModel } from "../types/market-snapshot";
import { IndexCard } from "./IndexCard";

const card: IndexCardModel = {
  symbol: "SPY",
  label: "S&P 500",
  price: 7475.46,
  change: 25.12,
  changePercent: 0.34,
  invert: false,
  sparkline: [7400, 7450, 7475.46],
  isProxy: true,
};

describe("IndexCard", () => {
  it("renders price, signed change and percent", () => {
    render(<IndexCard card={card} />);

    expect(screen.getByText("S&P 500")).toBeInTheDocument();
    expect(screen.getByText("7,475.46")).toBeInTheDocument();
    expect(screen.getByText("+0.34%")).toBeInTheDocument();
    expect(screen.getByText("+25.12")).toBeInTheDocument();
  });

  it("shows the proxy and stale badges when relevant", () => {
    render(<IndexCard card={card} stale />);

    expect(screen.getByText("PROXY")).toBeInTheDocument();
    expect(screen.getByText("STALE")).toBeInTheDocument();
  });

  it("opens the chart for its symbol", () => {
    const onOpen = vi.fn();
    render(<IndexCard card={card} onOpen={onOpen} />);

    fireEvent.click(screen.getByRole("button", { name: /open the s&p 500 chart/i }));
    expect(onOpen).toHaveBeenCalledWith("SPY");
  });
});

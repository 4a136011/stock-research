import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatusBadge, { type DataStatus } from "./StatusBadge";

describe("StatusBadge", () => {
  const cases: [DataStatus, string][] = [
    ["ok", "資料正常"],
    ["stale", "資料過期"],
    ["partial", "資料不完整"],
    ["error", "取得失敗"],
    ["missing", "無資料"],
  ];

  it.each(cases)("renders %s as %s", (status, label) => {
    render(<StatusBadge status={status} />);
    const badge = screen.getByText(label);
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("data-status", status);
  });
});

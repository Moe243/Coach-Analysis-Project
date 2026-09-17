import { screen } from "@testing-library/react";
import { apiGet } from "../api/client";
import { versions } from "../test/fixtures";
import { renderRoute } from "../test/render";
import { AppShell } from "./AppShell";

vi.mock("../api/client", () => ({ apiGet: vi.fn() }));

describe("public Ask shell", () => {
  beforeEach(() => vi.mocked(apiGet).mockResolvedValue(versions));

  it("hides analytical version metadata on the public Ask route", async () => {
    renderRoute(<AppShell />, "/ask");
    expect(await screen.findByText(/Adjusted associations/)).toBeVisible();
    expect(
      screen.queryByText(/Coach model|Version metadata/),
    ).not.toBeInTheDocument();
  });

  it("preserves version metadata on analytical routes", async () => {
    renderRoute(<AppShell />, "/statistics");
    expect(await screen.findByText(/Coach model/)).toBeVisible();
  });
});

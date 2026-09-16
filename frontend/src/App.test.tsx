import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Outlet, useLocation } from "react-router-dom";
import { App } from "./App";

vi.mock("./components/AppShell", () => ({
  AppShell: () => <Outlet />,
}));

function LocationProbe() {
  return <output aria-label="Current route">{useLocation().pathname}</output>;
}

function renderApp(route: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <LocationProbe />
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Ask route migration", () => {
  it("serves Ask v2 at the primary /ask route", async () => {
    renderApp("/ask");
    expect(
      await screen.findByRole("heading", { name: "Ask Anything" }),
    ).toBeVisible();
    expect(screen.getByText("Evidence-led conversation")).toBeVisible();
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/ask");
  });

  it("preserves the v1 interface at /ask/legacy", async () => {
    renderApp("/ask/legacy");
    expect(
      await screen.findByRole("heading", {
        name: "Query the analytics system",
      }),
    ).toBeVisible();
    expect(screen.getByLabelText("Your football question")).toBeVisible();
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/ask/legacy",
    );
  });

  it("redirects the preview alias to the primary route without a loop", async () => {
    renderApp("/ask/preview");
    await waitFor(() =>
      expect(screen.getByLabelText("Current route")).toHaveTextContent("/ask"),
    );
    expect(
      await screen.findByRole("heading", { name: "Ask Anything" }),
    ).toBeVisible();
  });
});

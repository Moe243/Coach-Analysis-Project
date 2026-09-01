import { Activity, BookOpen, Network, TableProperties } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";
import type { Versions } from "../api/contracts";

export function AppShell() {
  const versions = useQuery({
    queryKey: ["versions"],
    queryFn: ({ signal }) => apiGet<Versions>("/versions", {}, signal),
    staleTime: Infinity,
  });
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="site-header">
        <NavLink
          className="brand"
          to="/statistics"
          aria-label="NFL Coaching Impact home"
        >
          <span className="brand-mark" aria-hidden="true">
            C<span>+</span>
          </span>
          <span>
            <strong>Coaching Impact</strong>
            <small>Quarterback performance lab</small>
          </span>
        </NavLink>
        <nav className="primary-nav" aria-label="Primary">
          <NavLink to="/statistics">
            <TableProperties aria-hidden="true" /> Statistics
          </NavLink>
          <NavLink to="/network">
            <Network aria-hidden="true" /> Relationship Explorer
          </NavLink>
        </nav>
        <NavLink className="method-link" to="/methodology">
          <BookOpen aria-hidden="true" /> How to read this
        </NavLink>
      </header>
      <main id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="site-footer">
        <div>
          <Activity aria-hidden="true" />
          <span>Adjusted associations, not causal estimates.</span>
        </div>
        <p>
          {versions.data
            ? `Data ${versions.data.expected_data_version} · Coach model ${versions.data.coach_model_version}`
            : "Version metadata unavailable"}
        </p>
      </footer>
    </div>
  );
}

import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { LoadingState } from "./components/DataState";
import { StatisticsPage } from "./pages/StatisticsPage";

const CoachDetailPage = lazy(() =>
  import("./pages/CoachDetailPage").then((module) => ({
    default: module.CoachDetailPage,
  })),
);
const MethodologyPage = lazy(() =>
  import("./pages/MethodologyPage").then((module) => ({
    default: module.MethodologyPage,
  })),
);
const NetworkPage = lazy(() =>
  import("./pages/NetworkPage").then((module) => ({
    default: module.NetworkPage,
  })),
);
const QbDetailPage = lazy(() =>
  import("./pages/QbDetailPage").then((module) => ({
    default: module.QbDetailPage,
  })),
);

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/statistics" replace />} />
        <Route path="statistics" element={<StatisticsPage />} />
        <Route
          path="network"
          element={
            <Suspense
              fallback={
                <section className="page">
                  <LoadingState label="Loading Relationship Explorer" />
                </section>
              }
            >
              <NetworkPage />
            </Suspense>
          }
        />
        <Route
          path="qbs/:playerId"
          element={
            <Suspense
              fallback={
                <section className="page">
                  <LoadingState label="Loading quarterback profile" />
                </section>
              }
            >
              <QbDetailPage />
            </Suspense>
          }
        />
        <Route
          path="coaches/:coachId"
          element={
            <Suspense
              fallback={
                <section className="page">
                  <LoadingState label="Loading coach profile" />
                </section>
              }
            >
              <CoachDetailPage />
            </Suspense>
          }
        />
        <Route
          path="methodology"
          element={
            <Suspense
              fallback={
                <section className="page">
                  <LoadingState label="Loading methodology" />
                </section>
              }
            >
              <MethodologyPage />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/statistics" replace />} />
      </Route>
    </Routes>
  );
}

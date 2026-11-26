import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Loading, NotFound } from "./components/ui";
import { Overview } from "./pages/Overview";
import { Workspace } from "./pages/Workspace";

const Studio = lazy(() => import("./pages/Studio").then((m) => ({ default: m.Studio })));
const Benchmark = lazy(() => import("./pages/Benchmark").then((m) => ({ default: m.Benchmark })));
const DataPage = lazy(() => import("./pages/Data").then((m) => ({ default: m.DataPage })));
const HistoryPage = lazy(() => import("./pages/History").then((m) => ({ default: m.HistoryPage })));
const Methodology = lazy(() => import("./pages/Methodology").then((m) => ({ default: m.Methodology })));
export function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="page"><Loading /></div>}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="decisions" element={<Workspace />} />
          <Route path="decisions/:caseId" element={<Workspace />} />
          <Route path="studio" element={<Studio />} />
          <Route path="studio/:caseId" element={<Studio />} />
          <Route path="benchmark" element={<Benchmark />} />
          <Route path="data" element={<DataPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="methodology" element={<Methodology />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

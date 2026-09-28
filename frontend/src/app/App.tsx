import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiError } from "@/api/client";
import { Spinner } from "@/components/ui/primitives";
import { AppLayout } from "@/components/layout/AppLayout";
import { RequireAuth, RequirePermission } from "@/components/layout/guards";

const Landing = lazy(() => import("@/pages/landing/LandingPage"));
const Login = lazy(() => import("@/pages/login/LoginPage"));
const Dashboard = lazy(() => import("@/pages/dashboard/DashboardPage"));
const Patients = lazy(() => import("@/pages/patients/PatientsPage"));
const NewAnalysis = lazy(() => import("@/pages/new-analysis/NewAnalysisPage"));
const AnalysisViewer = lazy(() => import("@/pages/analysis/AnalysisViewerPage"));
const ProgressionPage = lazy(() => import("@/pages/progression/ProgressionPage"));
const ReviewQueue = lazy(() => import("@/pages/review/ReviewQueuePage"));
const ModelTrust = lazy(() => import("@/pages/model-trust/ModelTrustPage"));
const SecurityCenter = lazy(() => import("@/pages/security/SecurityCenterPage"));
const SecurityLab = lazy(() => import("@/pages/security-lab/SecurityLabPage"));
const Reports = lazy(() => import("@/pages/reports/ReportsPage"));
const Admin = lazy(() => import("@/pages/admin/AdminPage"));
const About = lazy(() => import("@/pages/about/AboutPage"));
const Verify = lazy(() => import("@/pages/reports/VerifyPage"));
const PerioChart = lazy(() => import("@/pages/clinical/PerioChartPage"));
const CarePlan = lazy(() => import("@/pages/clinical/CarePlanPage"));
const PatientExplainer = lazy(() => import("@/pages/clinical/PatientExplainerPage"));
const RecallBoard = lazy(() => import("@/pages/clinical/RecallBoardPage"));
const NotFound = lazy(() => import("@/pages/errors/NotFoundPage"));
const AccessDenied = lazy(() => import("@/pages/errors/AccessDeniedPage"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: (count, err) => !(err instanceof ApiError && [401, 403, 404].includes(err.status)) && count < 2,
    },
  },
});

function PageFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <Spinner />
    </div>
  );
}

const guard = (perm: string, el: JSX.Element) => <RequirePermission permission={perm}>{el}</RequirePermission>;

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/verify/:reportId?" element={<Verify />} />
            <Route path="/about" element={<About />} />
            <Route
              path="/app"
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="patients" element={guard("patient:read", <Patients />)} />
              <Route path="patients/:patientId/progression" element={guard("analysis:read", <ProgressionPage />)} />
              <Route path="patients/:patientId/perio-chart" element={guard("chart:read", <PerioChart />)} />
              <Route path="patients/:patientId/care-plan" element={guard("care:read", <CarePlan />)} />
              <Route path="patients/:patientId/explain" element={guard("care:read", <PatientExplainer />)} />
              <Route path="recall" element={guard("care:read", <RecallBoard />)} />
              <Route path="analysis/new" element={guard("analysis:run", <NewAnalysis />)} />
              <Route path="analysis/:analysisId" element={guard("analysis:read", <AnalysisViewer />)} />
              <Route path="review" element={guard("review:read", <ReviewQueue />)} />
              <Route path="model-trust" element={guard("model:read", <ModelTrust />)} />
              <Route path="security" element={<SecurityCenter />} />
              <Route path="security-lab" element={guard("security_lab:run", <SecurityLab />)} />
              <Route path="reports" element={guard("report:read", <Reports />)} />
              <Route path="admin" element={guard("admin:users", <Admin />)} />
              <Route path="about" element={<About embedded />} />
              <Route path="denied" element={<AccessDenied />} />
              <Route path="*" element={<NotFound embedded />} />
            </Route>
            <Route path="/denied" element={<AccessDenied />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

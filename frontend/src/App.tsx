import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "./api/client";
import { keys } from "./api/hooks";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { ToastProvider } from "./components/Toast";
import { Activity } from "./pages/Activity";
import { Connect } from "./pages/Connect";
import { Home } from "./pages/Home";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { ServerDetail } from "./pages/ServerDetail";
import { Servers } from "./pages/Servers";
import { Settings } from "./pages/Settings";

/** Query client: a 401 from any query signs the user out (ProtectedRoute then shows Login). */
export function makeQueryClient({ retry = true }: { retry?: boolean } = {}): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (error instanceof ApiError && error.status === 401 && query.queryKey[0] !== keys.me[0]) {
          client.setQueryData(keys.me, null);
        }
      },
    }),
    defaultOptions: {
      queries: {
        retry: (count, error) =>
          retry && !(error instanceof ApiError && error.status > 0 && error.status < 500) && count < 2,
        refetchOnWindowFocus: true,
      },
    },
  });
  return client;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="connect" element={<Connect />} />
          <Route path="servers" element={<Servers />} />
          <Route path="servers/:serverId" element={<ServerDetail />} />
          <Route path="activity" element={<Activity />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}

export function App({ client = makeQueryClient() }: { client?: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

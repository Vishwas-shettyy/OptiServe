import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useMe } from "../api/hooks";
import { ErrorState } from "./ErrorState";
import { Skeleton } from "./Skeleton";

/** Renders the page only for the signed-in admin; otherwise sends them to /login and back afterwards. */
export function ProtectedRoute() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-10">
        <Skeleton className="h-8 w-1/3" />
      </div>
    );
  }
  if (me.isError) {
    return <ErrorState error={me.error} title="Can't check your sign-in" onRetry={() => void me.refetch()} />;
  }
  if (!me.data) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}

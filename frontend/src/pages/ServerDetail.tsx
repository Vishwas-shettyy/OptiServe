import { ButtonLink } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { ServerIcon } from "../lib/icons";

export function ServerDetail() {
  return (
    <div>
      <PageHeader title="Server" sentence="How busy this server is, and what OptiServe expects next." />
      <Card>
        <EmptyState
          icon={ServerIcon}
          title="No details for this server yet"
          action={
            <ButtonLink to="/servers" variant="secondary">
              Back to servers
            </ButtonLink>
          }
        >
          Busy-ness, memory and the next hour's forecast show here once this server has sent a few minutes of data.
        </EmptyState>
      </Card>
    </div>
  );
}

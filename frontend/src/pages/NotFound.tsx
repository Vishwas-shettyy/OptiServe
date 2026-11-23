import { ButtonLink } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { HomeIcon } from "../lib/icons";

export function NotFound() {
  return (
    <Card>
      <EmptyState icon={HomeIcon} title="This page doesn't exist" action={<ButtonLink to="/">Go to Home</ButtonLink>}>
        The link may be old. Everything OptiServe shows starts from Home.
      </EmptyState>
    </Card>
  );
}

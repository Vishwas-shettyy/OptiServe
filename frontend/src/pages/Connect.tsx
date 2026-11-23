import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import { CloudIcon, ServerIcon, type LucideIcon } from "../lib/icons";

function Choice({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children: string }) {
  return (
    <Card as="article">
      <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent">
        <Icon className="size-6" aria-hidden strokeWidth={1.75} />
      </span>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-soft">{children}</p>
    </Card>
  );
}

export function Connect() {
  return (
    <div>
      <PageHeader title="Connect a server" sentence="Pick how OptiServe should see your servers. Both use real numbers only." />
      <div className="grid gap-6 md:grid-cols-2">
        <Choice icon={ServerIcon} title="Install the agent">
          A small program on each server sends how busy it is every 10 seconds, including memory. Works on any Linux
          server, in any cloud or on your own hardware.
        </Choice>
        <Choice icon={CloudIcon} title="Connect AWS">
          OptiServe reads your EC2 servers and Auto Scaling groups, and brings in the last 14 days of history so
          forecasts work right away.
        </Choice>
      </div>
    </div>
  );
}

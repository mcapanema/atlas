import { Typography } from "antd";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useDora, type DoraBand, type DoraMetrics, type MetricsFilters } from "../api/metrics";
import { ChartCard } from "./ChartCard";
import { StatCard } from "./StatCard";

const BAND_WORD: Record<DoraBand, string> = {
  elite: "Elite",
  high: "High",
  medium: "Medium",
  low: "Low",
};

/** The band as a word with a tint (never color alone); styles in index.css. */
export function DoraBandTag({ band }: { band: DoraBand }) {
  return <span className={`dora-band dora-band--${band}`}>{BAND_WORD[band]}</span>;
}

/** Whole hours under 48 hours, days past that; one decimal either way. */
function formatSpan(seconds: number): string {
  const hours = seconds / 3600;
  return hours < 48 ? `${hours.toFixed(1)} h` : `${(hours / 24).toFixed(1)} d`;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** The band tag, or why there is none; a sampled band shows its sample as well. */
function Detail({
  band,
  sample,
  tooFew,
  min,
  children,
}: {
  band: DoraBand | null;
  sample: number;
  tooFew: string;
  min: number;
  children: ReactNode;
}) {
  if (band === null) {
    return <span className="dora-detail">{`Too few ${tooFew} (${sample} of ${min})`}</span>;
  }
  return (
    <span className="dora-detail">
      <DoraBandTag band={band} /> {children}
    </span>
  );
}

const CARD_HELP =
  "DORA's four keys from the team's mapped repositories over the stats window. Failed changes include deployments that errored and incidents (issues with an incident label).";

/** DORA delivery performance: four tiles, each a value, its band and its sample. */
export function DoraCard({ data }: { data: DoraMetrics }) {
  const min = data.min_sample;
  if (data.codebases === 0) {
    return (
      <ChartCard label="Delivery performance (DORA)" help={CARD_HELP}>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          No repositories are mapped to this team yet.{" "}
          <Link to="/connectors">Map a repository to this team on the Connectors page</Link> to
          measure DORA.
        </Typography.Paragraph>
      </ChartCard>
    );
  }
  const lead = data.lead_time_median_seconds;
  const rate = data.change_failure_rate;
  const restore = data.restore_median_seconds;
  return (
    <ChartCard label="Delivery performance (DORA)" help={CARD_HELP}>
      <div className="stat-grid">
        <StatCard
          title="Deploy frequency"
          value={`${data.deploys_per_week.toFixed(1)} / week`}
          help="Deployments to production per week over the window."
        >
          <Detail
            band={data.deploy_frequency_band}
            sample={data.deployments}
            tooFew="deployments"
            min={min}
          >
            {plural(data.deployments, "deployment")}
          </Detail>
        </StatCard>
        <StatCard
          title="Change lead time"
          value={lead === null || data.lead_time_changes === 0 ? "—" : formatSpan(lead)}
          help="Median time from a change's first commit to its deployment."
        >
          <Detail
            band={data.lead_time_band}
            sample={data.lead_time_changes}
            tooFew="changes"
            min={min}
          >
            {plural(data.lead_time_changes, "change")}
          </Detail>
        </StatCard>
        <StatCard
          title="Change failure rate"
          value={
            rate === null || data.finished_deployments === 0 ? "—" : `${Math.round(rate * 100)}%`
          }
          help="Share of finished deployments that failed or were followed by an incident."
        >
          <Detail
            band={data.change_failure_band}
            sample={data.finished_deployments}
            tooFew="deployments"
            min={min}
          >
            {data.failed_deployments} of {plural(data.finished_deployments, "deployment")} failed
          </Detail>
        </StatCard>
        <StatCard
          title="Time to restore"
          value={restore === null || data.restores === 0 ? "—" : formatSpan(restore)}
          help="Median time from an incident opening to its resolution."
        >
          <Detail band={data.restore_band} sample={data.restores} tooFew="restores" min={min}>
            {plural(data.restores, "restore")}
          </Detail>
        </StatCard>
      </div>
    </ChartCard>
  );
}

/** The card for a team scope; renders nothing for a project (DORA is per team) or while loading. */
export function TeamDoraCard({
  teamId,
  filters,
}: {
  teamId: string | undefined;
  filters: MetricsFilters;
}) {
  const dora = useDora(teamId, filters);
  return dora.data ? <DoraCard data={dora.data} /> : null;
}

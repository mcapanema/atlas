import { Alert, Button, Card, DatePicker, InputNumber, Row, Space, Statistic } from "antd";
import { useMemo, useState } from "react";

import { useForecast, type CompletionForecast } from "../api/forecasts";
import type { MetricsFilters, MetricsScope } from "../api/metrics";
import { useForecastAccuracy, type ForecastAccuracy } from "../api/snapshots";
import { buildForecastOption } from "../lib/charts";
import { DATE_FORMAT, formatDay } from "../lib/dates";
import { useThemeMode } from "../theme/context";
import { EChart } from "./EChart";
import { HelpLabel } from "./HelpLabel";
import { StatCard } from "./StatCard";

const METHOD_HELP =
  "Runs 2,000 simulations of the remaining work. Each simulated day draws a " +
  "completion count from this scope's actual daily throughput over the last 90 " +
  "days (or since its first activity, if more recent), zero-throughput days included. Each bar is how many simulations " +
  "finished on that date; the dashed lines mark P50 and P85.";

function percent(fraction: number | null | undefined): string {
  return fraction != null ? `${Math.round(fraction * 100)}%` : "—";
}

function FinishDates({
  remaining,
  assumed,
  completion,
}: {
  remaining: number;
  assumed: boolean;
  completion: CompletionForecast;
}) {
  return (
    <Row gutter={[16, 16]}>
      <StatCard
        title={assumed ? "Remaining items (assumed)" : "Remaining items"}
        value={remaining}
        help={
          assumed
            ? "A scenario figure you entered, not the measured backlog. Every date below is simulated against it."
            : "Open work items in scope, including backlog items with no activity yet. Follows the page's filters."
        }
      />
      <StatCard
        title="P50 finish"
        value={formatDay(completion.p50_date)}
        help="Half the simulations finished by this date. The coin-flip date — not a commitment."
      />
      <StatCard
        title="P85 finish"
        value={formatDay(completion.p85_date)}
        help="85% of simulations finished by then. The date to commit to externally."
      />
      <StatCard
        title="P95 finish"
        value={formatDay(completion.p95_date)}
        help="95% of simulations finished by then. Only the worst 1 in 20 runs went past it."
      />
    </Row>
  );
}

function AssumedRemainingInput({
  measured,
  draft,
  onDraftChange,
  assumed,
  onAssumedChange,
}: {
  measured: number;
  draft: number | undefined;
  onDraftChange: (value: number | undefined) => void;
  assumed: number | undefined;
  onAssumedChange: (value: number | undefined) => void;
}) {
  return (
    <Space>
      <label htmlFor="assumed-remaining">Assume remaining items</label>
      <InputNumber
        id="assumed-remaining"
        aria-label="Assume remaining items"
        min={0}
        max={100000}
        placeholder={String(measured)}
        value={draft}
        onChange={(value) => onDraftChange(value ?? undefined)}
        onBlur={() => onAssumedChange(draft)}
        onPressEnter={() => onAssumedChange(draft)}
      />
      {assumed !== undefined && (
        <Button
          type="link"
          size="small"
          onClick={() => {
            onDraftChange(undefined);
            onAssumedChange(undefined);
          }}
        >
          Reset
        </Button>
      )}
    </Space>
  );
}

function AccuracyStats({ accuracy }: { accuracy: ForecastAccuracy }) {
  return (
    <Row gutter={[16, 16]}>
      <StatCard
        title="Past forecasts within P85"
        value={percent(accuracy.p85_hit_rate)}
        help="Share of past daily forecasts whose P85 date the scope actually met. Below 85% means this model has been optimistic here."
      />
      <StatCard
        title="Forecasts evaluated"
        value={accuracy.evaluated}
        help="How many past forecasts have a known outcome to score against. A small number means the hit rate is still noisy."
      />
    </Row>
  );
}

export function ForecastCard({
  scope,
  filters,
}: {
  scope: MetricsScope;
  filters?: MetricsFilters;
}) {
  const [targetDate, setTargetDate] = useState<string>();
  const [assumedRemaining, setAssumedRemaining] = useState<number>();
  // Typed digits stay local until blur/Enter commit them to assumedRemaining —
  // committing per keystroke would re-run the backend's 2,000-trial Monte
  // Carlo simulation on every digit and throw away all but the last result.
  const [draftRemaining, setDraftRemaining] = useState<number>();
  const forecast = useForecast(scope, { filters, targetDate, remaining: assumedRemaining });
  const accuracy = useForecastAccuracy(scope);
  const { mode } = useThemeMode();
  const data = forecast.data;
  const completion = data?.completion;
  const outcomesOption = useMemo(
    () =>
      data && completion
        ? buildForecastOption(
            completion.outcomes,
            data.window_end,
            { p50Date: completion.p50_date, p85Date: completion.p85_date },
            mode,
          )
        : null,
    [data, completion, mode],
  );

  if (forecast.isError) {
    return <Alert type="error" message="Failed to load forecast" />;
  }
  if (!data) return null;

  const title = <HelpLabel label="Completion forecast" help={METHOD_HELP} />;

  if (!completion) {
    return (
      <Card title={title}>
        <Alert type="info" message="Not enough delivery history to forecast." />
      </Card>
    );
  }
  return (
    <Card title={title}>
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        <FinishDates
          remaining={data.remaining}
          assumed={assumedRemaining !== undefined}
          completion={completion}
        />
        <Space wrap size="large">
          <AssumedRemainingInput
            measured={data.remaining}
            draft={draftRemaining}
            onDraftChange={setDraftRemaining}
            assumed={assumedRemaining}
            onAssumedChange={setAssumedRemaining}
          />
          <Space>
            <span>Confidence of finishing by</span>
            <DatePicker
              format={DATE_FORMAT}
              onChange={(value) => setTargetDate(value ? value.format("YYYY-MM-DD") : undefined)}
            />
            {data.confidence != null && <Statistic value={percent(data.confidence)} />}
          </Space>
        </Space>
        {outcomesOption && <EChart option={outcomesOption} />}
        {accuracy.data && accuracy.data.evaluated > 0 && <AccuracyStats accuracy={accuracy.data} />}
      </Space>
    </Card>
  );
}

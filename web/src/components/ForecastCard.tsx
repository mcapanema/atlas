import { Alert, Button, Card, DatePicker, InputNumber, Row, Space, Statistic } from "antd";
import { useMemo, useState } from "react";

import { useForecast } from "../api/forecasts";
import type { MetricsFilters, MetricsScope } from "../api/metrics";
import { useForecastAccuracy } from "../api/snapshots";
import { buildForecastOption } from "../lib/charts";
import { DATE_FORMAT, formatDay } from "../lib/dates";
import { useThemeMode } from "../theme/context";
import { EChart } from "./EChart";
import { HelpLabel } from "./HelpLabel";
import { StatCard } from "./StatCard";

const METHOD_HELP =
  "Runs 2,000 simulations of the remaining work. Each simulated day draws a " +
  "completion count from this scope's actual daily throughput over the last 90 " +
  "days, zero-throughput days included. Each bar is how many simulations " +
  "finished on that date; the dashed lines mark P50 and P85.";

export function ForecastCard({
  scope,
  filters,
}: {
  scope: MetricsScope;
  filters?: MetricsFilters;
}) {
  const [targetDate, setTargetDate] = useState<string>();
  const [assumedRemaining, setAssumedRemaining] = useState<number>();
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
        <Row gutter={[16, 16]}>
          <StatCard
            title={assumedRemaining === undefined ? "Remaining items" : "Remaining items (assumed)"}
            value={data.remaining}
            help={
              assumedRemaining === undefined
                ? "Open work items in scope, including backlog items with no activity yet. Follows the page's filters."
                : "A scenario figure you entered, not the measured backlog. Every date below is simulated against it."
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
        <Space wrap size="large">
          <Space>
            <label htmlFor="assumed-remaining">Assume remaining items</label>
            <InputNumber
              id="assumed-remaining"
              aria-label="Assume remaining items"
              min={0}
              max={100000}
              placeholder={String(data.remaining)}
              value={assumedRemaining}
              onChange={(value) => setAssumedRemaining(value ?? undefined)}
            />
            {assumedRemaining !== undefined && (
              <Button type="link" size="small" onClick={() => setAssumedRemaining(undefined)}>
                Reset
              </Button>
            )}
          </Space>
          <Space>
            <span>Confidence of finishing by</span>
            <DatePicker
              format={DATE_FORMAT}
              onChange={(value) => setTargetDate(value ? value.format("YYYY-MM-DD") : undefined)}
            />
            {data.confidence != null && (
              <Statistic value={`${Math.round(data.confidence * 100)}%`} />
            )}
          </Space>
        </Space>
        {outcomesOption && <EChart option={outcomesOption} />}
        {accuracy.data && accuracy.data.evaluated > 0 && (
          <Row gutter={[16, 16]}>
            <StatCard
              title="Past forecasts within P85"
              value={
                accuracy.data.p85_hit_rate != null
                  ? `${Math.round(accuracy.data.p85_hit_rate * 100)}%`
                  : "—"
              }
              help="Share of past daily forecasts whose P85 date the scope actually met. Below 85% means this model has been optimistic here."
            />
            <StatCard
              title="Forecasts evaluated"
              value={accuracy.data.evaluated}
              help="How many past forecasts have a known outcome to score against. A small number means the hit rate is still noisy."
            />
          </Row>
        )}
      </Space>
    </Card>
  );
}

import { Alert, Card, DatePicker, Row, Space, Statistic } from "antd";
import { useMemo, useState } from "react";

import { useForecast } from "../api/forecasts";
import type { MetricsScope } from "../api/metrics";
import { useForecastAccuracy } from "../api/snapshots";
import { buildForecastOption } from "../lib/charts";
import { DATE_FORMAT, formatDay } from "../lib/dates";
import { useThemeMode } from "../theme/context";
import { EChart } from "./EChart";
import { StatCard } from "./StatCard";

export function ForecastCard({ scope }: { scope: MetricsScope }) {
  const [targetDate, setTargetDate] = useState<string>();
  const forecast = useForecast(scope, targetDate);
  const accuracy = useForecastAccuracy(scope);
  const { mode } = useThemeMode();
  const data = forecast.data;
  const outcomesOption = useMemo(
    () =>
      data?.completion
        ? buildForecastOption(data.completion.outcomes, data.window_end, mode)
        : null,
    [data, mode],
  );

  if (forecast.isError) {
    return <Alert type="error" message="Failed to load forecast" />;
  }
  if (!data) return null;
  if (!data.completion) {
    return (
      <Card title="Completion forecast">
        <Alert type="info" message="Not enough delivery history to forecast." />
      </Card>
    );
  }
  return (
    <Card title="Completion forecast">
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        <Row gutter={[16, 16]}>
          <StatCard title="Remaining items" value={data.remaining} />
          <StatCard title="P50 finish" value={formatDay(data.completion.p50_date)} />
          <StatCard title="P85 finish" value={formatDay(data.completion.p85_date)} />
          <StatCard title="P95 finish" value={formatDay(data.completion.p95_date)} />
        </Row>
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
            />
            <StatCard title="Forecasts evaluated" value={accuracy.data.evaluated} />
          </Row>
        )}
      </Space>
    </Card>
  );
}

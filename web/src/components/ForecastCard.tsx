import { Alert, Card, DatePicker, Row, Space, Statistic } from "antd";
import { useMemo, useState } from "react";

import { useForecast } from "../api/forecasts";
import type { MetricsScope } from "../api/metrics";
import { buildForecastOption } from "../lib/charts";
import { EChart } from "./EChart";
import { StatCard } from "./StatCard";

export function ForecastCard({ scope }: { scope: MetricsScope }) {
  const [targetDate, setTargetDate] = useState<string>();
  const forecast = useForecast(scope, targetDate);
  const data = forecast.data;
  const outcomesOption = useMemo(
    () =>
      data?.completion ? buildForecastOption(data.completion.outcomes, data.window_end) : null,
    [data],
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
          <StatCard title="P50 finish" value={data.completion.p50_date.slice(0, 10)} />
          <StatCard title="P85 finish" value={data.completion.p85_date.slice(0, 10)} />
          <StatCard title="P95 finish" value={data.completion.p95_date.slice(0, 10)} />
        </Row>
        <Space>
          <span>Confidence of finishing by</span>
          <DatePicker
            onChange={(value) => setTargetDate(value ? value.format("YYYY-MM-DD") : undefined)}
          />
          {data.confidence != null && (
            <Statistic value={`${Math.round(data.confidence * 100)}%`} />
          )}
        </Space>
        {outcomesOption && <EChart option={outcomesOption} />}
      </Space>
    </Card>
  );
}

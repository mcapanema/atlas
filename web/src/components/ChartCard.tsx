import { Card } from "antd";
import type { ReactNode } from "react";

import { HelpLabel } from "./HelpLabel";

export function ChartCard({
  label,
  help,
  children,
}: {
  label: string;
  help: string;
  children: ReactNode;
}) {
  return <Card title={<HelpLabel label={label} help={help} />}>{children}</Card>;
}

/**
 * Stands in for a chart with nothing to plot — bare axes read as a broken
 * chart. Same height as EChart's default so paired cards stay level.
 */
export function ChartEmpty({ children }: { children: ReactNode }) {
  return <div className="chart-empty">{children}</div>;
}

import { Col } from "antd";

import { HelpLabel } from "./HelpLabel";

/**
 * Instrument stat tile: hairline border, 11px secondary label, mono figure.
 * Deliberately not an AntD Card/Statistic — the stock treatment reads as
 * the admin-template anti-reference PRODUCT.md designs away from.
 */
export function StatCard({
  title,
  value,
  help,
}: {
  title: string;
  value: string | number;
  /** How the figure is computed — surfaced on hover/focus of the label. */
  help?: string;
}) {
  return (
    <Col xs={12} lg={6}>
      <div className="stat">
        <div className="stat__label">
          {help ? <HelpLabel label={title} help={help} /> : title}
        </div>
        <div className="stat__value fig">{value}</div>
      </div>
    </Col>
  );
}

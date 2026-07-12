import { Col } from "antd";

/**
 * Instrument stat tile: hairline border, 11px secondary label, mono figure.
 * Deliberately not an AntD Card/Statistic — the stock treatment reads as
 * the admin-template anti-reference PRODUCT.md designs away from.
 */
export function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <Col xs={12} lg={6}>
      <div className="stat">
        <div className="stat__label">{title}</div>
        <div className="stat__value fig">{value}</div>
      </div>
    </Col>
  );
}

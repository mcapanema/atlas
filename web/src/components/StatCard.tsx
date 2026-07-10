import { Card, Col, Statistic } from "antd";

export function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <Col xs={12} lg={6}>
      <Card>
        <Statistic title={title} value={value} />
      </Card>
    </Col>
  );
}

import { Typography } from "antd";

/** "Evidence:" label + bullet list of the data points behind a claim. */
export function EvidenceList({ items }: { items: string[] }) {
  return (
    <>
      <Typography.Paragraph style={{ marginBottom: 4 }}>
        <b>Evidence:</b>
      </Typography.Paragraph>
      <ul>
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </>
  );
}

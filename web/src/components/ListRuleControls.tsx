import { AutoComplete, Button, Select, Space } from "antd";

import type { OpenStateType, TypeLabel, WorkItemTypeName } from "../api/metricRules";
import { STATE_TYPE_OPTIONS, WORK_ITEM_TYPE_OPTIONS, canonicalStates } from "../lib/metricRules";

function asOptions(labels: string[]) {
  return labels.map((label) => ({ value: label, label }));
}

export function LabelsControl({
  label,
  value,
  labelOptions,
  onChange,
}: {
  label: string;
  value: string[];
  labelOptions: string[];
  onChange: (value: string[]) => void;
}) {
  return (
    <Select
      aria-label={label}
      mode="tags"
      style={{ width: 320 }}
      value={value}
      options={asOptions(labelOptions)}
      onChange={onChange}
    />
  );
}

export function StatesControl({
  label,
  value,
  onChange,
}: {
  label: string;
  value: OpenStateType[];
  onChange: (value: OpenStateType[]) => void;
}) {
  return (
    <Select
      aria-label={label}
      mode="multiple"
      style={{ width: 320 }}
      value={value}
      options={STATE_TYPE_OPTIONS}
      onChange={(next: OpenStateType[]) => onChange(canonicalStates(next))}
    />
  );
}

function moveUp(rows: TypeLabel[], index: number): TypeLabel[] {
  if (index === 0) return rows;
  const next = [...rows];
  [next[index - 1], next[index]] = [next[index], next[index - 1]];
  return next;
}

/** Ordered label → type rows: the first mapped label an item carries sets its type. */
export function TypeLabelsEditor({
  label,
  value,
  labelOptions,
  onChange,
}: {
  label: string;
  value: TypeLabel[];
  labelOptions: string[];
  onChange: (value: TypeLabel[]) => void;
}) {
  const update = (index: number, row: TypeLabel) =>
    onChange(value.map((current, i) => (i === index ? row : current)));
  return (
    <Space direction="vertical" aria-label={label}>
      {value.map((row, index) => (
        // Rows have no identity beyond their position; reordering re-renders them.
        <Space key={index}>
          <AutoComplete
            aria-label={`${label}: label ${index + 1}`}
            style={{ width: 200 }}
            value={row.label}
            options={asOptions(labelOptions)}
            onChange={(next: string) => update(index, { ...row, label: next })}
          />
          <Select
            aria-label={`${label}: type ${index + 1}`}
            style={{ width: 120 }}
            value={row.type}
            options={WORK_ITEM_TYPE_OPTIONS}
            onChange={(next: WorkItemTypeName) => update(index, { ...row, type: next })}
          />
          <Button
            size="small"
            disabled={index === 0}
            onClick={() => onChange(moveUp(value, index))}
          >
            Move up
          </Button>
          <Button size="small" onClick={() => onChange(value.filter((_, i) => i !== index))}>
            Remove
          </Button>
        </Space>
      ))}
      <Button size="small" onClick={() => onChange([...value, { label: "", type: "bug" }])}>
        Add mapping
      </Button>
    </Space>
  );
}

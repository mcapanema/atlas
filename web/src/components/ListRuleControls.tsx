import { AutoComplete, Button, Checkbox, DatePicker, Select, Space } from "antd";
import dayjs, { type Dayjs } from "dayjs";

import type { OpenStateType, RuleValue, TypeLabel, WorkItemTypeName } from "../api/metricRules";
import {
  STATE_TYPE_OPTIONS,
  WORK_ITEM_TYPE_OPTIONS,
  canonicalStates,
  type RuleSpec,
} from "../lib/metricRules";
import { DATE_FORMAT, toHolidayList } from "../lib/dates";
import { WEEKDAY_OPTIONS } from "../lib/syncSchedule";

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
      // Free-typed tags: an empty list means "type a name", not "No data".
      notFoundContent={null}
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

/** The list-valued rule controls: free-text tags, state types, weekdays, dates, label-to-type rows. */
export function ListRuleControl({
  control,
  label,
  value,
  labelOptions,
  onChange,
}: {
  control: Extract<
    RuleSpec["control"],
    { kind: "labels" | "names" | "states" | "typeLabels" | "weekdays" | "dates" }
  >;
  label: string;
  value: RuleValue;
  labelOptions: string[];
  onChange: (value: RuleValue) => void;
}) {
  switch (control.kind) {
    case "labels":
      return (
        <LabelsControl
          label={label}
          value={value as string[]}
          labelOptions={labelOptions}
          onChange={onChange}
        />
      );
    case "names":
      // Free text: workflow state names, so no label suggestions.
      return (
        <LabelsControl
          label={label}
          value={value as string[]}
          labelOptions={[]}
          onChange={onChange}
        />
      );
    case "states":
      return <StatesControl label={label} value={value as OpenStateType[]} onChange={onChange} />;
    case "weekdays":
      return (
        <Checkbox.Group
          aria-label={label}
          options={WEEKDAY_OPTIONS}
          value={value as number[]}
          onChange={(next) => onChange([...next].sort((a, b) => a - b))}
        />
      );
    case "dates":
      return (
        <DatePicker
          multiple
          aria-label={label}
          format={DATE_FORMAT}
          style={{ width: 320 }}
          value={(value as string[]).map((d) => dayjs(d))}
          onChange={(next: Dayjs[] | null) => onChange(toHolidayList(next))}
        />
      );
    case "typeLabels":
      return (
        <TypeLabelsEditor
          label={label}
          value={value as TypeLabel[]}
          labelOptions={labelOptions}
          onChange={onChange}
        />
      );
  }
}

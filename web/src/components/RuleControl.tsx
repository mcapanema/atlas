import { DatePicker, InputNumber, Select, Switch } from "antd";
import dayjs from "dayjs";

import type { RuleValue } from "../api/metricRules";
import { DATE_FORMAT } from "../lib/dates";
import { timeZoneOptions, type RuleSpec } from "../lib/metricRules";
import { ListRuleControl } from "./ListRuleControls";

export function RuleControl({
  spec,
  value,
  labelOptions = [],
  onChange,
}: {
  spec: RuleSpec;
  value: RuleValue;
  labelOptions?: string[];
  onChange: (value: RuleValue) => void;
}) {
  const { control, label } = spec;
  switch (control.kind) {
    case "switch":
      return <Switch aria-label={label} checked={value === true} onChange={onChange} />;
    case "select":
      return (
        <Select
          aria-label={label}
          style={{ width: 220 }}
          value={value as string}
          options={control.options}
          onChange={onChange}
        />
      );
    case "timezone":
      return (
        <Select
          aria-label={label}
          showSearch
          style={{ width: 260 }}
          value={value as string}
          options={timeZoneOptions()}
          onChange={onChange}
        />
      );
    case "date":
      return (
        <DatePicker
          aria-label={label}
          format={DATE_FORMAT}
          value={value ? dayjs(value as string) : null}
          onChange={(next) => onChange(next ? next.format("YYYY-MM-DD") : null)}
        />
      );
    case "number":
      return (
        <InputNumber
          aria-label={label}
          min={control.min}
          max={control.max}
          step={control.step}
          suffix={control.suffix}
          value={Number(value)}
          onChange={(next) => {
            if (next !== null) onChange(next);
          }}
        />
      );
    default:
      return (
        <ListRuleControl
          control={control}
          label={label}
          value={value}
          labelOptions={labelOptions}
          onChange={onChange}
        />
      );
  }
}

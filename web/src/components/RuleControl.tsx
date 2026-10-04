import { InputNumber, Select, Switch } from "antd";

import type { RuleValue } from "../api/metricRules";
import { timeZoneOptions, type RuleSpec } from "../lib/metricRules";

export function RuleControl({
  spec,
  value,
  onChange,
}: {
  spec: RuleSpec;
  value: RuleValue;
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
          value={String(value)}
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
          value={String(value)}
          options={timeZoneOptions()}
          onChange={onChange}
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
  }
}

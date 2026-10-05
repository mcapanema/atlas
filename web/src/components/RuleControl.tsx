import { InputNumber, Select, Switch } from "antd";

import type { OpenStateType, RuleValue, TypeLabel } from "../api/metricRules";
import { timeZoneOptions, type RuleSpec } from "../lib/metricRules";
import { LabelsControl, StatesControl, TypeLabelsEditor } from "./ListRuleControls";

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
    case "labels":
      return (
        <LabelsControl
          label={label}
          value={value as string[]}
          labelOptions={labelOptions}
          onChange={onChange}
        />
      );
    case "states":
      return <StatesControl label={label} value={value as OpenStateType[]} onChange={onChange} />;
    case "typeLabels":
      return (
        <TypeLabelsEditor
          label={label}
          value={value as TypeLabel[]}
          labelOptions={labelOptions}
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

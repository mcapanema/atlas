import { DatePicker, Select, Space } from "antd";
import dayjs from "dayjs";

import type { MetricsFilters, MetricsScope } from "../api/metrics";
import { useWorkItemStates } from "../api/workItems";
import { DATE_FORMAT } from "../lib/dates";

const TYPE_OPTIONS = ["story", "task", "bug", "spike", "other"].map((value) => ({
  value,
  label: value,
}));

const PERIOD_OPTIONS = [
  ...[7, 30, 90, 180].map((days) => ({ value: String(days), label: `Last ${days} days` })),
  { value: "custom", label: "Custom range" },
];

const ISO = "YYYY-MM-DD";

export function MetricsFilterBar({
  filters,
  scope,
  onChange,
}: {
  filters: MetricsFilters;
  /** Omitted on the org-wide Executive Dashboard — states come from every team. */
  scope?: MetricsScope;
  onChange: (filters: MetricsFilters) => void;
}) {
  const states = useWorkItemStates(scope);
  const custom = Boolean(filters.start && filters.end);
  const { start, end, windowDays, ...itemFilters } = filters;
  const periodValue = custom ? "custom" : String(windowDays ?? 30);

  return (
    <Space wrap>
      <Select
        aria-label="Analysis period"
        style={{ width: 150 }}
        value={periodValue}
        options={PERIOD_OPTIONS}
        onChange={(value) =>
          onChange(
            value === "custom"
              ? {
                  ...itemFilters,
                  start: dayjs().subtract(30, "day").format(ISO),
                  end: dayjs().format(ISO),
                }
              : { ...itemFilters, windowDays: Number(value) },
          )
        }
      />
      {custom && (
        // AntD forwards `aria-label` onto both the start and end inputs, which makes
        // getByLabelText ambiguous; label the wrapper instead of the picker itself.
        <span role="group" aria-label="Custom date range">
          <DatePicker.RangePicker
            allowClear={false}
            format={DATE_FORMAT}
            value={[dayjs(start), dayjs(end)]}
            // The dates render as DD-MM-YYYY but travel as ISO — format the
            // dayjs values rather than reusing AntD's display strings.
            onChange={(dates) => {
              const [nextStart, nextEnd] = dates ?? [];
              if (nextStart && nextEnd) {
                onChange({
                  ...itemFilters,
                  start: nextStart.format(ISO),
                  end: nextEnd.format(ISO),
                });
              }
            }}
          />
        </span>
      )}
      <Select
        aria-label="Work item types"
        mode="multiple"
        allowClear
        placeholder="All types"
        style={{ minWidth: 160 }}
        value={filters.types ?? []}
        options={TYPE_OPTIONS}
        onChange={(types) =>
          onChange({ ...filters, types: types.length ? types : undefined })
        }
      />
      <Select
        aria-label="Excluded states"
        mode="tags"
        allowClear
        loading={states.isLoading}
        placeholder="Exclude states"
        style={{ minWidth: 170 }}
        value={filters.excludeStates ?? []}
        tokenSeparators={[","]}
        // tags mode: fetched states are suggestions, any typed value still counts
        options={(states.data ?? []).map((state) => ({ value: state, label: state }))}
        onChange={(next) =>
          onChange({ ...filters, excludeStates: next.length ? next : undefined })
        }
      />
    </Space>
  );
}

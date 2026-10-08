import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Select,
  Space,
  Switch,
  TimePicker,
  Typography,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";

import { useSaveSyncSchedule, useSyncSchedule, type SyncScheduleInput } from "../api/syncSchedule";
import {
  WEEKDAY_OPTIONS,
  clockParts,
  defaultSchedule,
  intervalOptions,
  timeZoneOptions,
} from "../lib/syncSchedule";

const CLOCK = "HH:mm";

interface FormValues {
  enabled: boolean;
  days: number[];
  window: [Dayjs, Dayjs];
  interval_minutes: number;
  timezone: string;
}

// Picker values are wall-clock times only, so anchor them to a fixed day no
// zone changes its clocks on: anchored to "today", a 02:30 on the browser's
// own spring-forward day became 03:30. Built from parts, not parsed: dayjs
// needs a plugin to parse "HH:mm".
const ANCHOR_DAY = "2000-01-03";

function toDayjs(clock: string): Dayjs {
  const { hour, minute } = clockParts(clock);
  return dayjs(ANCHOR_DAY).hour(hour).minute(minute).second(0).millisecond(0);
}

function toFormValues(schedule: SyncScheduleInput): FormValues {
  return {
    enabled: schedule.enabled,
    days: schedule.days,
    window: [toDayjs(schedule.window_start), toDayjs(schedule.window_end)],
    interval_minutes: schedule.interval_minutes,
    timezone: schedule.timezone,
  };
}

function toInput(values: FormValues): SyncScheduleInput {
  const [start, end] = values.window;
  return {
    enabled: values.enabled,
    days: [...values.days].sort((a, b) => a - b),
    window_start: start.format(CLOCK),
    window_end: end.format(CLOCK),
    interval_minutes: values.interval_minutes,
    timezone: values.timezone,
  };
}

function ScheduleForm({
  initial,
  saving,
  onSave,
}: {
  initial: SyncScheduleInput;
  saving: boolean;
  onSave: (input: SyncScheduleInput) => void;
}) {
  return (
    <Form<FormValues>
      layout="vertical"
      initialValues={toFormValues(initial)}
      onFinish={(values) => onSave(toInput(values))}
    >
      <Form.Item name="enabled" label="Sync automatically" valuePropName="checked">
        <Switch />
      </Form.Item>
      <Form.Item name="days" label="Days">
        <Checkbox.Group options={WEEKDAY_OPTIONS} />
      </Form.Item>
      <Space wrap align="start">
        <Form.Item name="window" label="Between">
          {/* order={false}: don't silently turn 22:00–02:00 into 02:00–22:00; the
              server rejects an overnight window with a reason instead. */}
          <TimePicker.RangePicker format={CLOCK} minuteStep={15} allowClear={false} order={false} />
        </Form.Item>
        <Form.Item name="interval_minutes" label="Every">
          <Select style={{ width: 110 }} options={intervalOptions(initial.interval_minutes)} />
        </Form.Item>
        <Form.Item name="timezone" label="Timezone">
          <Select showSearch style={{ width: 240 }} options={timeZoneOptions(initial.timezone)} />
        </Form.Item>
      </Space>
      <Button type="primary" htmlType="submit" loading={saving}>
        Save schedule
      </Button>
    </Form>
  );
}

function SaveOutcome({ save }: { save: ReturnType<typeof useSaveSyncSchedule> }) {
  if (save.isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not save the schedule"
        description={save.error.message}
      />
    );
  }
  return save.isSuccess ? <Typography.Text type="success">Schedule saved</Typography.Text> : null;
}

export function AutoSyncCard({ organizationId }: { organizationId: string }) {
  const schedule = useSyncSchedule(organizationId);
  const save = useSaveSyncSchedule(organizationId);
  const current = schedule.data ?? null;

  return (
    <Card title="Auto sync" loading={schedule.isLoading}>
      {schedule.isError ? (
        <Alert
          type="error"
          showIcon
          title="Failed to load the auto-sync schedule"
          description={schedule.error.message}
        />
      ) : (
        <Space orientation="vertical" style={{ width: "100%" }}>
          {/* Keyed so a saved or switched schedule resets the form's values. */}
          <ScheduleForm
            key={`${organizationId}:${current?.updated_at ?? "new"}`}
            initial={current ?? defaultSchedule()}
            saving={save.isPending}
            onSave={(input) => save.mutate(input)}
          />
          <SaveOutcome save={save} />
        </Space>
      )}
    </Card>
  );
}

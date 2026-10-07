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

import {
  useSaveSyncSchedule,
  useSyncSchedule,
  type SyncSchedule,
  type SyncScheduleInput,
} from "../api/syncSchedule";
import { formatDateTime } from "../lib/dates";
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

// Built from parts, not parsed: dayjs needs a plugin to parse "HH:mm".
function toDayjs(clock: string): Dayjs {
  const { hour, minute } = clockParts(clock);
  return dayjs().hour(hour).minute(minute).second(0).millisecond(0);
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

function RunStatus({ schedule }: { schedule: SyncSchedule | null }) {
  if (!schedule) {
    return (
      <Typography.Text type="secondary">
        Not scheduled yet: Atlas syncs only when you click Sync now.
      </Typography.Text>
    );
  }
  const run = schedule.last_run;
  return (
    <Space direction="vertical" size={4} style={{ width: "100%" }}>
      <Typography.Text>
        {schedule.next_run_at
          ? `Next run: ${formatDateTime(schedule.next_run_at)}`
          : "Auto sync is off"}
      </Typography.Text>
      {run?.error && (
        <Alert
          type="error"
          showIcon
          message={`Last auto sync failed (${formatDateTime(run.finished_at)})`}
          description={run.error}
        />
      )}
      {run && !run.error && (
        <Typography.Text type="secondary">
          Last auto sync: {formatDateTime(run.finished_at)}, succeeded
        </Typography.Text>
      )}
    </Space>
  );
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
      <Alert type="error" message="Could not save the schedule" description={save.error.message} />
    );
  }
  return save.isSuccess ? <Typography.Text type="success">Schedule saved</Typography.Text> : null;
}

export function AutoSyncCard({
  organizationId,
  configured,
}: {
  organizationId: string;
  configured: boolean;
}) {
  const schedule = useSyncSchedule(organizationId);
  const save = useSaveSyncSchedule(organizationId);
  const current = schedule.data ?? null;

  return (
    <Card title="Auto sync" loading={schedule.isLoading}>
      <Space direction="vertical" style={{ width: "100%" }}>
        {!configured && (
          <Alert type="warning" message="Scheduled syncs fail until ATLAS_LINEAR_API_KEY is set." />
        )}
        {schedule.isError ? (
          <Alert
            type="error"
            message="Failed to load the auto-sync schedule"
            description={schedule.error.message}
          />
        ) : (
          <>
            <RunStatus schedule={current} />
            {/* Keyed so a saved or switched schedule resets the form's values. */}
            <ScheduleForm
              key={`${organizationId}:${current?.updated_at ?? "new"}`}
              initial={current ?? defaultSchedule()}
              saving={save.isPending}
              onSave={(input) => save.mutate(input)}
            />
            <SaveOutcome save={save} />
          </>
        )}
      </Space>
    </Card>
  );
}

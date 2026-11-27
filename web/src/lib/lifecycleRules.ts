import type { RuleGroup } from "./metricRules";

/** How one item's events fold into its flow sample. Its own module: metricRules.ts is at the file-length ceiling. */
export const LIFECYCLE_RULES: RuleGroup = {
  title: "Lifecycle",
  rules: [
    {
      name: "exclude_born_done",
      label: "Leave out items created already done",
      help: "Items logged straight into a done state (retro-logged records) are excluded from every metric, forecast remaining included.",
      control: { kind: "switch" },
    },
    {
      name: "move_back_ends_wip",
      label: "Moving back to backlog ends WIP",
      help: "An item that leaves an in-progress state for a not-started one stops counting as work in progress.",
      control: { kind: "switch" },
    },
    {
      name: "restart_clock_after_move_back",
      label: "Restart the clock after a move-back",
      help: 'When an item moved back to backlog is started again, cycle time and aging count from the restart; the parked time becomes queue time. Applies after a move-back only while "Moving back to backlog ends WIP" is on, and always after a cancel. A reopen after done never restarts the clock.',
      control: { kind: "switch" },
    },
    {
      name: "reopen_completion",
      label: "Reopened after done: measure to",
      help: "For an item completed, reopened and completed again: its last completion, or its first.",
      control: {
        kind: "select",
        options: [
          { value: "last", label: "Last completion" },
          { value: "first", label: "First completion" },
        ],
      },
    },
    {
      name: "done_then_canceled",
      label: "Done, then canceled",
      help: "Whether an item canceled after reaching done still counts as delivered.",
      control: {
        kind: "select",
        options: [
          { value: "delivered", label: "Stays delivered" },
          { value: "canceled", label: "Counts as canceled" },
        ],
      },
    },
    {
      name: "count_parent_issues",
      label: "Count parent issues",
      help: "Off: an issue with sub-issues leaves every metric, remaining included; only its sub-issues count. Avoids counting the same work twice.",
      control: { kind: "switch" },
    },
    {
      name: "count_sub_issues",
      label: "Count sub-issues",
      help: "Off: only top-level issues count, in every metric. A sub-issue whose parent is in the scope leaves; the parent starts when it or a sub-issue first starts.",
      control: { kind: "switch" },
    },
    {
      name: "lead_time_start",
      label: "Lead time starts",
      help: "At creation, or when the item first leaves Triage. Also where pre-start queue time begins. Items never in Triage start at creation.",
      control: {
        kind: "select",
        options: [
          { value: "created", label: "At creation" },
          { value: "triage_exit", label: "When it leaves Triage" },
        ],
      },
    },
    {
      name: "done_then_reopened",
      label: "Done, then moved back to Todo",
      help: "Moved from done back to a not-started state (Todo, Backlog, Triage) without restarting: stays delivered, or counts as open again (remaining, not WIP). A later start keeps the original clock.",
      control: {
        kind: "select",
        options: [
          { value: "delivered", label: "Stays delivered" },
          { value: "reopened", label: "Counts as reopened" },
        ],
      },
    },
    {
      name: "canceled_then_reopened",
      label: "Canceled, then moved back to Todo",
      help: "Moved from canceled back to a not-started state: stays canceled, or counts as open again (remaining, not WIP).",
      control: {
        kind: "select",
        options: [
          { value: "canceled", label: "Stays canceled" },
          { value: "reopened", label: "Counts as reopened" },
        ],
      },
    },
  ],
};

import { Alert, Button, Card, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import {
  useSaveMetricRules,
  type MetricRulesView,
  type RuleChanges,
  type RulesScope,
  type RuleValue,
} from "../api/metricRules";
import {
  RULE_GROUPS,
  draftValue,
  formatRuleValue,
  pendingChanges,
  type RuleSpec,
} from "../lib/metricRules";
import { RuleControl } from "./RuleControl";

function RuleRow({
  spec,
  view,
  draft,
  inheritedFrom,
  onChange,
}: {
  spec: RuleSpec;
  view: MetricRulesView;
  draft: RuleChanges;
  inheritedFrom: string;
  onChange: (value: RuleValue | null) => void;
}) {
  const own = draft[spec.name];
  const customized = own !== undefined && own !== null;
  const inherited = view.inherited[spec.name];
  return (
    <div className="rule-row">
      <div className="rule-row-text">
        <Space size={8}>
          <Typography.Text strong>{spec.label}</Typography.Text>
          {customized && <Tag>Customized</Tag>}
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          {spec.help}
        </Typography.Paragraph>
        <Typography.Text type="secondary">
          {inheritedFrom}: {formatRuleValue(spec, inherited)}
        </Typography.Text>
      </div>
      <Space>
        <RuleControl spec={spec} value={own ?? inherited} onChange={onChange} />
        {customized && (
          <Button type="link" size="small" onClick={() => onChange(null)}>
            Reset to default
          </Button>
        )}
      </Space>
    </div>
  );
}

/** Edits one scope's overrides; keyed by scope, so switching scopes starts a fresh draft. */
export function MetricRulesForm({
  scope,
  view,
  onDirtyChange,
}: {
  scope: RulesScope;
  view: MetricRulesView;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [draft, setDraft] = useState<RuleChanges>(view.overrides);
  const save = useSaveMetricRules(scope);
  const changes = pendingChanges(view.overrides, draft);
  const dirty = Object.keys(changes).length > 0;
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  const inheritedFrom = scope.kind === "team" ? "Workspace default" : "Built-in";
  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      {save.isError && (
        <Alert
          type="error"
          showIcon
          message="Couldn't save the rules"
          description={save.error.message}
        />
      )}
      {RULE_GROUPS.map((group) => (
        <Card key={group.title} title={group.title} size="small">
          {group.rules.map((spec) => (
            <RuleRow
              key={spec.name}
              spec={spec}
              view={view}
              draft={draft}
              inheritedFrom={inheritedFrom}
              onChange={(value) =>
                setDraft((current) => ({
                  ...current,
                  [spec.name]: draftValue(view, spec.name, value),
                }))
              }
            />
          ))}
        </Card>
      ))}
      <Button
        type="primary"
        disabled={!dirty}
        loading={save.isPending}
        onClick={() => save.mutate(changes, { onSuccess: (saved) => setDraft(saved.overrides) })}
      >
        Save
      </Button>
    </Space>
  );
}

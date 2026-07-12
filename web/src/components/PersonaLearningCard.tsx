import { Alert, Button, Card, List, Space, Typography } from "antd";

import type { Persona } from "../api/advisor";
import { useGuidance, useReflect, useRestoreGuidance } from "../api/personas";

export function PersonaLearningCard({ persona }: { persona: Persona }) {
  const guidance = useGuidance(persona);
  const reflect = useReflect(persona);
  const restore = useRestoreGuidance(persona);
  const versions = guidance.data ?? [];
  const active = versions[0];

  return (
    <Card
      title="Persona learning"
      extra={
        <Button size="small" loading={reflect.isPending} onClick={() => reflect.mutate()}>
          Reflect now
        </Button>
      }
    >
      <Space direction="vertical" style={{ width: "100%" }}>
        {guidance.isError && (
          <Alert
            type="warning"
            message="Failed to load persona guidance"
            description={guidance.error.message}
          />
        )}
        {reflect.isError && (
          <Alert
            type="warning"
            message="Reflection failed"
            description={reflect.error.message}
          />
        )}
        {restore.isError && (
          <Alert
            type="warning"
            message="Restore failed"
            description={restore.error.message}
          />
        )}
        {active ? (
          <>
            <Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
              {active.guidance}
            </Typography.Paragraph>
            <Typography.Text type="secondary">
              v{active.version} · {new Date(active.created_at).toLocaleDateString()}
            </Typography.Text>
          </>
        ) : (
          <Typography.Text type="secondary">
            No learned guidance yet — rate some advice, then reflect.
          </Typography.Text>
        )}
        {versions.length > 1 && (
          <List
            size="small"
            header="History"
            dataSource={versions.slice(1)}
            renderItem={(version) => (
              <List.Item
                actions={[
                  <Button
                    key="restore"
                    size="small"
                    loading={restore.isPending}
                    onClick={() => restore.mutate(version.version)}
                  >
                    Restore
                  </Button>,
                ]}
              >
                <Typography.Text ellipsis style={{ maxWidth: 480 }}>
                  v{version.version}: {version.guidance}
                </Typography.Text>
              </List.Item>
            )}
          />
        )}
      </Space>
    </Card>
  );
}

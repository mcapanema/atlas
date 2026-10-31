import { Alert, Badge, Card, Flex, Typography } from "antd";

import { useOpenRouterStatus } from "../api/connectors";
import { CredentialsSection } from "./CredentialsForm";

function SetupAlert() {
  return (
    <Alert
      type="warning"
      showIcon
      title="OpenRouter isn't configured"
      description="Add an OpenRouter API key below. Until then the Advisor and Meeting prep can't generate advice inside Atlas."
    />
  );
}

export function OpenRouterCard() {
  const query = useOpenRouterStatus();
  const status = query.data;
  // A dot plus a word: the state never rides on color alone.
  const badge = status?.configured ? (
    <Badge status="success" text={`Configured · ${status.hint ?? "…"}`} />
  ) : (
    <Badge status="default" text="Not configured" />
  );
  return (
    <Card title="AI advisor (OpenRouter)" loading={query.isLoading} extra={status ? badge : null}>
      <Flex vertical gap="middle">
        {query.error && (
          <Alert
            type="error"
            showIcon
            title="Failed to load OpenRouter status"
            description={query.error.message}
          />
        )}
        {status?.configured === false && <SetupAlert />}
        <Typography.Text type="secondary">
          Create a key at{" "}
          <Typography.Link href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">
            openrouter.ai/keys
          </Typography.Link>
          ; the model is any OpenRouter model id.
        </Typography.Text>
        {status && (
          <CredentialsSection
            integration="openrouter"
            label="OpenRouter"
            fields={[
              { name: "api_key", label: "OpenRouter API key", secret: true },
              { name: "model", label: "Model" },
            ]}
            initial={{ model: status.model }}
            status={status}
          />
        )}
      </Flex>
    </Card>
  );
}

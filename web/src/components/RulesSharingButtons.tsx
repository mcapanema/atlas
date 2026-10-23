import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Modal, Space, Tooltip } from "antd";
import { useRef, useState } from "react";

import { fetchSharedRules, useImportMetricRules, type RulesImportResult } from "../api/metricRules";
import type { Organization } from "../api/organizations";
import { downloadJson, importSummary, parseRulesFile, rulesFileName } from "../lib/rulesFile";

function SharingOutcome({ error, result }: { error?: string; result?: RulesImportResult }) {
  if (error !== undefined) return <Alert type="error" showIcon message={error} />;
  if (result === undefined) return null;
  return (
    <Alert
      type={result.skipped_teams.length + result.ambiguous_teams.length > 0 ? "warning" : "success"}
      showIcon
      message={importSummary(result)}
    />
  );
}

/** Export the organization's rule layers to a file, or replace them from one (ADR-0019). */
export function RulesSharingButtons({
  organization,
  disabled,
  onImported,
}: {
  organization: Organization;
  disabled: boolean;
  // After a successful import, once the workspace view holds the imported rules.
  onImported: () => void;
}) {
  const [modal, modalContext] = Modal.useModal();
  const [fileError, setFileError] = useState<string>();
  const importRules = useImportMetricRules(organization.id);
  const exportRules = useMutation({
    mutationFn: () => fetchSharedRules(organization.id),
    onSuccess: (shared) =>
      downloadJson(rulesFileName(organization.name, shared.exported_at), shared),
  });

  const fileInput = useRef<HTMLInputElement>(null);
  // Only the latest action's outcome shows.
  const clearOutcome = () => {
    setFileError(undefined);
    importRules.reset();
    exportRules.reset();
  };
  const lockedTitle = disabled ? "Save or discard your edits first" : undefined;

  const chooseFile = async (file: File) => {
    clearOutcome();
    let parsed: unknown;
    try {
      parsed = parseRulesFile(await file.text());
    } catch (error) {
      setFileError((error as Error).message);
      return;
    }
    modal.confirm({
      title: "Import metric rules?",
      content:
        "This replaces the workspace default and the rules of every team the file names. Teams it doesn't name keep their rules.",
      okText: "Import and replace",
      onOk: () => importRules.mutate(parsed, { onSuccess: onImported }),
    });
  };

  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      {modalContext}
      <Space wrap>
        {/* With unsaved edits, Export would quietly save the stored rules. */}
        <Tooltip title={lockedTitle}>
          <Button
            icon={<DownloadOutlined />}
            disabled={disabled}
            onClick={() => {
              clearOutcome();
              exportRules.mutate();
            }}
            loading={exportRules.isPending}
          >
            Export
          </Button>
        </Tooltip>
        <Tooltip title={lockedTitle}>
          <Button
            icon={<UploadOutlined />}
            disabled={disabled}
            onClick={() => fileInput.current?.click()}
            loading={importRules.isPending}
          >
            Import
          </Button>
        </Tooltip>
        <input
          ref={fileInput}
          type="file"
          accept=".json,application/json"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            // Cleared so choosing the same file again still fires a change.
            event.target.value = "";
            if (file) void chooseFile(file);
          }}
        />
      </Space>
      <SharingOutcome
        error={fileError ?? importRules.error?.message ?? exportRules.error?.message}
        result={importRules.data}
      />
    </Space>
  );
}

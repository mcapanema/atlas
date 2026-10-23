import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Modal, Space, Tooltip, Upload } from "antd";
import { useState } from "react";

import { fetchSharedRules, useImportMetricRules, type RulesImportResult } from "../api/metricRules";
import type { Organization } from "../api/organizations";
import { downloadJson, importSummary, parseRulesFile, rulesFileName } from "../lib/rulesFile";

function SharingOutcome({ error, result }: { error?: string; result?: RulesImportResult }) {
  if (error !== undefined) return <Alert type="error" showIcon message={error} />;
  if (result === undefined) return null;
  return (
    <Alert
      type={result.skipped_teams.length > 0 ? "warning" : "success"}
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

  const chooseFile = async (file: File) => {
    setFileError(undefined);
    importRules.reset();
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
        <Button
          icon={<DownloadOutlined />}
          onClick={() => exportRules.mutate()}
          loading={exportRules.isPending}
        >
          Export
        </Button>
        <Tooltip title={disabled ? "Save or discard your edits first" : undefined}>
          <Upload
            accept=".json,application/json"
            showUploadList={false}
            disabled={disabled}
            beforeUpload={(file) => {
              void chooseFile(file);
              return false; // read here; never sent by AntD
            }}
          >
            <Button icon={<UploadOutlined />} disabled={disabled} loading={importRules.isPending}>
              Import
            </Button>
          </Upload>
        </Tooltip>
      </Space>
      <SharingOutcome
        error={fileError ?? importRules.error?.message ?? exportRules.error?.message}
        result={importRules.data}
      />
    </Space>
  );
}

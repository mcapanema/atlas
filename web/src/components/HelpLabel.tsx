import { Tooltip } from "antd";

/**
 * A term with its definition one hover or focus away — recognition over
 * recall, so a reader never has to know what "Flow efficiency" means to
 * read the number next to it.
 */
export function HelpLabel({ label, help }: { label: string; help: string }) {
  return (
    // Explicit focus trigger: hover-only definitions don't exist for
    // keyboard users.
    <Tooltip title={help} trigger={["hover", "focus"]}>
      <span className="th-help" tabIndex={0}>
        {label}
      </span>
    </Tooltip>
  );
}

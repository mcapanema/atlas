import { Popover } from "antd";
import { useState } from "react";

import type { DeliveryHealth } from "../api/metrics";

const KNOWN_BANDS = new Set(["healthy", "warning", "critical"]);

/**
 * The health cell: mono score + band word (never color alone), with a
 * keyboard-accessible popover listing every component score and its reason.
 * Unknown bands fall back to neutral styling instead of an unstyled hole.
 */
export function HealthBadge({ health }: { health: DeliveryHealth | undefined }) {
  const [open, setOpen] = useState(false);
  if (!health || health.score == null || health.band == null) return <>—</>;
  const band = KNOWN_BANDS.has(health.band) ? health.band : "unknown";
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger={["click"]}
      placement="rightTop"
      content={
        <dl className="health-components">
          {health.components.map((component) => (
            <div key={component.name}>
              <dt>
                {/* "/100" spells the scale: a critical "risk 0" must read as
                    0-out-of-100, never as "zero risk". */}
                {component.name} <span className="fig">{component.score}</span>
                <span className="health-components__scale">/100</span>
              </dt>
              <dd>{component.reason}</dd>
            </div>
          ))}
        </dl>
      }
    >
      <button
        type="button"
        className={`health-badge health-badge--${band}`}
        aria-label={`Health ${health.score} of 100 — ${health.band}. Show component reasons`}
        aria-expanded={open}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
      >
        <span className="fig">{health.score}</span>
        <span className="health-badge__band">{health.band}</span>
      </button>
    </Popover>
  );
}

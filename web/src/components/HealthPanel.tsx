import type { ReactNode } from "react";

import type { DeliveryHealth, HealthComponent } from "../api/metrics";
import { componentHelp } from "../lib/health";
import { HelpLabel } from "./HelpLabel";

type Band = HealthComponent["band"];

const OVERALL_HELP =
  "Weighted average of the scored components, 0–100. Weights and the healthy and warning cutoffs are the team's Metric rules; a component with too few items behind it is left out.";

/** One instrument tile: label, mono score out of 100, then the evidence line. */
function HealthTile({
  label,
  help,
  score,
  band,
  detail,
}: {
  label: string;
  help: string | undefined;
  score: number;
  band: Band;
  detail: ReactNode;
}) {
  return (
    <div className={`stat health-tile health-tile--${band}`}>
      <div className="stat__label health-tile__label">
        {help ? <HelpLabel label={label} help={help} /> : label}
      </div>
      {/* "/100" spells the scale: a critical "risk 0" must read as
          0-out-of-100, never as "zero risk". */}
      <div className="stat__value">
        <span className="fig">{score}</span>
        <span className="health-tile__scale">/100</span>
      </div>
      <div className="health-tile__detail">{detail}</div>
    </div>
  );
}

/**
 * Delivery health leads the scope dashboards: the overall score and every
 * component, each with its reason, so a weak component on a healthy team
 * is visible without a click. Warning and critical tiles are tinted and
 * name their band in words; healthy components stay quiet.
 */
export function HealthPanel({
  health,
  periodText,
}: {
  health: DeliveryHealth;
  periodText: string | null;
}) {
  // Destructured so each null check below narrows for TypeScript.
  const { score, band } = health;
  return (
    <section aria-label="Delivery health" className="health-strip">
      <div className="health-strip__row">
        {(score == null || band == null) && (
          // The health floor (health_min_sample) leaves small or idle teams unscored.
          <span className="page-asof">
            Health not scored yet: too few items completed or in progress to score it.
          </span>
        )}
        {periodText && <span className="page-asof">{periodText}</span>}
      </div>
      {score != null && band != null && (
        <div className="health-grid">
          <HealthTile
            label="Health"
            help={OVERALL_HELP}
            score={score}
            band={band}
            detail={<span className="health-tile__band">{band}</span>}
          />
          {health.components.map((component) => (
            <HealthTile
              key={component.name}
              label={component.name}
              help={componentHelp(component.name)}
              score={component.score}
              band={component.band}
              detail={
                <>
                  {component.band !== "healthy" && (
                    <span className="health-tile__band">{component.band} · </span>
                  )}
                  {component.reason}
                </>
              }
            />
          ))}
        </div>
      )}
    </section>
  );
}

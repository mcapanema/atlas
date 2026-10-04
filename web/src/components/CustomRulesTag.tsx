import { Tag } from "antd";
import { Link } from "react-router-dom";

import type { Team } from "../api/teams";

/** Says a team's numbers follow its own metric rules, and links to them. */
export function CustomRulesTag({ team }: { team: Team | undefined }) {
  if (!team?.has_custom_rules) return null;
  return (
    <Tag color="blue">
      <Link to={`/metric-rules?team=${team.id}`}>Custom rules</Link>
    </Tag>
  );
}

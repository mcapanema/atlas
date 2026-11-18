"""Routes the MCP tools deliberately do not call.

`tests/api/test_mcp_coverage.py` fails for any `/api` route that a tool in
`app/api/mcp_*.py` does not call and that is not listed here with a reason.
Keys are exact `(METHOD, route template)` pairs, never wildcards.
"""

from collections.abc import Mapping
from typing import Final

_ADVISOR = (
    "Atlas's own OpenRouter advisor; an MCP client brings its own LLM "
    "and reads `recommendations/context` (meeting_brief)."
)
_SYNC = (
    "run_sync covers the organization; auto sync chains code and Datadog after Linear (ADR-0014)."
)

NOT_FOR_MCP: Final[Mapping[tuple[str, str], str]] = {
    # auth
    ("GET", "/api/auth/session"): ("Browser sign-in and session only."),
    ("POST", "/api/auth/setup"): ("Browser sign-in and session only."),
    ("POST", "/api/auth/sign-in"): ("Browser sign-in and session only."),
    ("POST", "/api/auth/sign-out"): ("Browser sign-in and session only."),
    ("PUT", "/api/auth/password"): ("Browser sign-in and session only."),
    # users
    ("GET", "/api/users"): ("Accounts are managed by admins in the UI (ADR-0032)."),
    ("POST", "/api/users"): ("Accounts are managed by admins in the UI (ADR-0032)."),
    ("DELETE", "/api/users/{user_id}"): ("Accounts are managed by admins in the UI (ADR-0032)."),
    ("PUT", "/api/users/{user_id}/password"): (
        "Accounts are managed by admins in the UI (ADR-0032)."
    ),
    # mcp-tokens
    ("GET", "/api/mcp-tokens"): ("A token must not create or revoke tokens."),
    ("POST", "/api/mcp-tokens"): ("A token must not create or revoke tokens."),
    ("DELETE", "/api/mcp-tokens/{token_id}"): ("A token must not create or revoke tokens."),
    # connector credentials
    ("PUT", "/api/connectors/linear/credentials"): (
        "Secrets never pass through a chat (ADR-0032)."
    ),
    ("DELETE", "/api/connectors/linear/credentials"): (
        "Secrets never pass through a chat (ADR-0032)."
    ),
    ("PUT", "/api/connectors/github/credentials"): (
        "Secrets never pass through a chat (ADR-0032)."
    ),
    ("DELETE", "/api/connectors/github/credentials"): (
        "Secrets never pass through a chat (ADR-0032)."
    ),
    ("PUT", "/api/connectors/datadog/credentials"): (
        "Secrets never pass through a chat (ADR-0032)."
    ),
    ("DELETE", "/api/connectors/datadog/credentials"): (
        "Secrets never pass through a chat (ADR-0032)."
    ),
    ("PUT", "/api/connectors/openrouter/credentials"): (
        "Secrets never pass through a chat (ADR-0032)."
    ),
    ("DELETE", "/api/connectors/openrouter/credentials"): (
        "Secrets never pass through a chat (ADR-0032)."
    ),
    # docs
    ("GET", "/api/docs"): ("API docs for people."),
    ("GET", "/api/openapi.json"): ("API docs for people."),
    # advisor, meeting prep, personas
    ("GET", "/api/recommendations/status"): (_ADVISOR),
    ("POST", "/api/recommendations"): (_ADVISOR),
    ("GET", "/api/recommendations"): (_ADVISOR),
    ("POST", "/api/meetings/prep"): (_ADVISOR),
    ("GET", "/api/meetings/prep"): (_ADVISOR),
    ("GET", "/api/personas/{persona}/guidance"): (_ADVISOR),
    ("POST", "/api/personas/{persona}/feedback"): (_ADVISOR),
    ("POST", "/api/personas/{persona}/guidance/{version}/restore"): (_ADVISOR),
    ("POST", "/api/personas/{persona}/reflect"): (_ADVISOR),
    # metrics
    ("GET", "/api/metrics"): ("The same numbers are in `recommendations/context` (meeting_brief)."),
    ("GET", "/api/metrics/state-times"): (
        "The same numbers are in `recommendations/context` (meeting_brief)."
    ),
    ("GET", "/api/metrics/lead-time-distribution"): (
        "The same numbers are in `recommendations/context` (meeting_brief)."
    ),
    # metrics feeds
    ("GET", "/api/metrics/snapshots"): (
        "Dashboard chart feeds; flow_trend and meeting_brief cover the decisions."
    ),
    ("GET", "/api/metrics/overview"): (
        "Dashboard chart feeds; flow_trend and meeting_brief cover the decisions."
    ),
    # delivery data
    ("GET", "/api/events"): ("Delivery data comes from the tracker sync, not from an agent."),
    ("POST", "/api/events"): ("Delivery data comes from the tracker sync, not from an agent."),
    ("POST", "/api/work-items"): ("Delivery data comes from the tracker sync, not from an agent."),
    ("POST", "/api/organizations"): (
        "Delivery data comes from the tracker sync, not from an agent."
    ),
    ("POST", "/api/teams"): ("Delivery data comes from the tracker sync, not from an agent."),
    ("POST", "/api/projects"): ("Delivery data comes from the tracker sync, not from an agent."),
    # work item filters
    ("GET", "/api/work-items/states"): ("Filter lists for the UI."),
    ("GET", "/api/work-items/labels"): ("Filter lists for the UI."),
    # sync
    ("POST", "/api/connectors/linear/teams/{team_id}/sync"): (_SYNC),
    ("POST", "/api/connectors/github/sync"): (_SYNC),
    ("POST", "/api/connectors/datadog/sync"): (_SYNC),
    ("GET", "/api/connectors/github/jobs/{job_id}"): (_SYNC),
    ("GET", "/api/connectors/datadog/jobs/{job_id}"): (_SYNC),
    # metric rules files
    ("GET", "/api/organizations/{organization_id}/metric-rules/export"): (
        "File exchange between installs (ADR-0019); update_metric_rules covers changes."
    ),
    ("POST", "/api/organizations/{organization_id}/metric-rules/import"): (
        "File exchange between installs (ADR-0019); update_metric_rules covers changes."
    ),
}

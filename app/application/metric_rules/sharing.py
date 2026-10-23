"""Shared rules: the metric-rule layers as one install hands them to another (ADR-0019).

A team travels by its source identity (`external_id`, the Linear team id)
and its name, never by Atlas's own UUID, which differs per install.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.domain.teams.entities import Team


@dataclass(frozen=True)
class SharedTeamRules:
    """One team's override layer, with what identifies the team in another install."""

    name: str
    external_id: str | None
    overrides: Mapping[str, object]


@dataclass(frozen=True)
class SharedRules:
    """An organization's workspace layer and its teams' non-empty layers."""

    workspace: Mapping[str, object]
    teams: tuple[SharedTeamRules, ...] = ()


def _folded(name: str) -> str:
    return name.strip().casefold()


def _match(entry: SharedTeamRules, teams: Sequence[Team]) -> Team | None:
    """The team with the entry's external id, else the one team with its name."""
    if entry.external_id is not None:
        by_id = next((t for t in teams if t.external_id == entry.external_id), None)
        if by_id is not None:
            return by_id
    named = [t for t in teams if _folded(t.name) == _folded(entry.name)]
    return named[0] if len(named) == 1 else None


def match_teams(
    shared: Sequence[SharedTeamRules], teams: Sequence[Team]
) -> tuple[dict[UUID, SharedTeamRules], tuple[str, ...]]:
    """Each matched local team's entry, and the file names of the entries matching none.

    Raises ValueError when two entries match the same local team: which one
    wins would be a guess.
    """
    matched: dict[UUID, SharedTeamRules] = {}
    skipped: list[str] = []
    for entry in shared:
        team = _match(entry, teams)
        if team is None:
            skipped.append(entry.name)
        elif team.id in matched:
            raise ValueError(f"The file names team {team.name} more than once")
        else:
            matched[team.id] = entry
    return matched, tuple(skipped)

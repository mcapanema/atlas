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


@dataclass(frozen=True)
class TeamMatch:
    """How a file's team entries landed on this install's teams."""

    matched: dict[UUID, SharedTeamRules]
    # File names, in file order: no team here has that name...
    missing: tuple[str, ...]
    # ...or several do, and no external id picked one.
    ambiguous: tuple[str, ...]


def _folded(name: str) -> str:
    return name.strip().casefold()


def _candidates(entry: SharedTeamRules, teams: Sequence[Team]) -> list[Team]:
    """The team with the entry's external id, else every team with its name.

    External ids are unique (`teams.external_id`), so only a name can match
    several teams.
    """
    if entry.external_id is not None:
        by_id = next((t for t in teams if t.external_id == entry.external_id), None)
        if by_id is not None:
            return [by_id]
    return [t for t in teams if _folded(t.name) == _folded(entry.name)]


def match_teams(shared: Sequence[SharedTeamRules], teams: Sequence[Team]) -> TeamMatch:
    """Match each entry to a local team; report the entries matching none or several.

    Raises ValueError when two entries match the same local team: which one
    wins would be a guess.
    """
    matched: dict[UUID, SharedTeamRules] = {}
    missing: list[str] = []
    ambiguous: list[str] = []
    for entry in shared:
        found = _candidates(entry, teams)
        if not found:
            missing.append(entry.name)
        elif len(found) > 1:
            ambiguous.append(entry.name)
        elif found[0].id in matched:
            raise ValueError(f"The file names team {found[0].name} more than once")
        else:
            matched[found[0].id] = entry
    return TeamMatch(matched, tuple(missing), tuple(ambiguous))

"""Lead Time: arrival (creation, or Triage exit by rule) -> completion, per completed item."""

from datetime import timedelta

from app.domain.metrics.samples import FlowSample


def lead_times(samples: list[FlowSample]) -> list[timedelta]:
    """Lead time per completed sample, from its arrived_at; others contribute nothing."""
    return [s.completed_at - s.arrived_at for s in samples if s.completed_at is not None]

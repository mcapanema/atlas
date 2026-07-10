"""Lead Time: creation -> completion, one duration per completed work item."""

from datetime import timedelta

from app.domain.metrics.samples import FlowSample


def lead_times(samples: list[FlowSample]) -> list[timedelta]:
    """Lead time per completed sample; uncompleted samples contribute nothing."""
    return [s.completed_at - s.created_at for s in samples if s.completed_at is not None]

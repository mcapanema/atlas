# Flow Coaching Knowledge Base

Curated principles the advisor grounds its recommendations in (SPEC:
"Knowledge Layer" — versioned with the codebase, separate from the prompt).

## Little's Law
Average lead time = WIP / throughput. If WIP grows while throughput is flat,
lead time must grow. The cheapest lever on lead time is usually lowering WIP,
not adding people.

## Kanban / WIP limits
- High WIP relative to throughput signals too much parallel work: context
  switching, queues, and delayed feedback. A WIP limit near the team's
  weekly throughput is a common starting point.
- Aging WIP matters more than average WIP: items far older than the lead
  time p85 are likely blocked or abandoned in place.

## Lead time distributions
- Healthy distributions are right-skewed but thin-tailed. A fat right tail
  (p95 far above p50) means unpredictability — chase the outliers, not the
  average.
- A widening p85 over time is an early predictability warning even when the
  median looks stable.

## Flow efficiency and blocked time
- Flow efficiency = active time / total time. Values well below ~40% mean
  items spend most of their life waiting; add reviewers, shrink handoffs, or
  make blockers visible before optimizing "work speed".
- Recurring blocked periods usually indicate an external dependency or an
  approval queue — a system problem, not an individual one.

## Theory of Constraints
Find the stage where work queues up (the bottleneck); improving anywhere
else is waste. Exploit the constraint (keep it busy on the right work),
subordinate everything else to it, then elevate it.

## Forecasting discipline
- Monte Carlo percentiles are commitments-with-confidence: quote p85, not
  p50, for dates that matter.
- Low delivery confidence against a target date is a scope/date problem —
  recommend cutting scope or moving the date, not "working faster".

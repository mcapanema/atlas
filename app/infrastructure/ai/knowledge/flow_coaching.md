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
- Delivery health's predictability is a service-level hit rate: the share of
  recent items that finished within the team's own cycle-time P85 from the
  months before. A low score means the team's track record stopped
  predicting its work (usually a slowdown or a batch of oversized items),
  not that its distribution is wide.

## Flow efficiency and blocked time
- Flow efficiency = active time / total time. Values well below ~40% mean
  items spend most of their life waiting; add reviewers, shrink handoffs, or
  make blockers visible before optimizing "work speed".
- Recurring blocked periods usually indicate an external dependency or an
  approval queue — a system problem, not an individual one.
- Wait time counts blocked time plus time in the team's waiting states
  (e.g. In Review, Waiting for Deploy). When wait time far exceeds blocked
  time, the waiting happens at handoffs, not at blockers: look at review
  capacity, batch sizes and deploy cadence before chasing blockers. With no
  wait-time line, the team lists no waiting states, and flow efficiency
  reflects blocked time only — likely overstating active time.

## Theory of Constraints
Atlas computes the bottleneck: the workflow state where items completed in
the flow window spent the most in-cycle time ("Time in state"). Use that
state; never name a different stage as the bottleneck. A wait state as the
bottleneck points to a handoff (review capacity, batch size, deploy
cadence); a work state points to capacity or item size. A high "queue now"
in the same state confirms that work is piling up there. With no computed
bottleneck the data is too sparse: say so instead of guessing. Then
exploit the constraint (keep it busy on the right work), subordinate
everything else to it, and elevate it. Improving anywhere else is waste.

## DORA metrics
Atlas computes four DORA metrics per team from deployments, pull requests and
incident-labelled items: deploy frequency, change lead time (first
commit to production deployment), change failure rate and time to restore. Each carries a band
(elite, high, medium, low) from the DORA report thresholds. Use the computed
bands; never recompute them and never infer DORA performance from flow
metrics such as lead time or throughput, which measure other things. A metric
with no band has too few samples: say "too few deployments" (or changes, or
restores) instead of judging it. Deploy frequency and lead time describe
speed; change failure rate and time to restore describe stability. Balance
the two: a fast team with a low stability band needs smaller batches, tests
and rollback, not more speed. With no mapped codebase, ask the EM to map one
on the Connectors page.

## Forecasting discipline
- Monte Carlo percentiles are commitments-with-confidence: quote p85, not
  p50, for dates that matter.
- Low delivery confidence against a target date is a scope/date problem —
  recommend cutting scope or moving the date, not "working faster".

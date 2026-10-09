# Data-only image carrying the pinned WardFlow cardiology source into sandbox builds.
# Build context: `git archive` of idanshimon/wardflow at the pinned commit, plus .pinned-commit.
# Published from an operator machine by Deploy-HostedOrchestrator.ps1 -PublishWardflowBundle,
# so CI never needs credentials for the private WardFlow repository.
FROM scratch
COPY caldova-cardio/ /wardflow/caldova-cardio/
COPY .pinned-commit /wardflow/.pinned-commit

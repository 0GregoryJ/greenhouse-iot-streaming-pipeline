# ADR 0009: GitHub Actions deployment over Tailscale and SSH

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

Deployments were manual: SSH to a host, `git pull`, restart services or rebuild containers. That is repeatable but easy to forget or do out of order. The Pi and the serving host are not reachable from the public internet, and the project avoids opening SSH publicly. The hosts already run from a Git clone of this repository.

## Decision

One workflow ([`.github/workflows/ci-cd.yml`](../../.github/workflows/ci-cd.yml)) runs on every push and pull request: the pytest suite with a Redis service, and the dashboard lint and build. On a push to `main`, after both pass, two deploy jobs run in the `production` environment:

- **Pi.** Join Tailscale as an ephemeral node tagged `tag:ci` (OAuth client and OIDC audience), SSH with a deploy key and a pinned `known_hosts`, then `git pull --ff-only`, install `requirements/gateway.txt`, restart `greenhouse-ingest` and `greenhouse-kafka-producer`, and check that both are active.
- **Serving host.** The same connection, then `git pull --ff-only`, `docker compose up -d --build --no-deps live-consumer api`, `docker compose ps`, and a `/health` check on `127.0.0.1:8000`.

Each host has its own concurrency group so deploys queue instead of overlapping. Secrets and variables are GitHub environment settings; no values are in the repository.

## Consequences

- Merging to `main` after green tests updates the Pi gateway and the serving containers without a manual step.
- No inbound access is opened for CI: the runner joins the tailnet for the duration of the job.
- Rollback is a revert commit on `main`, which the same pipeline deploys.
- The two deploy jobs run in parallel, so changes that need strict order between the Pi and the serving host are split across merges.
- The post-deploy checks are `is-active` and `/health`. Running `verify-deployment.sh` and a data-freshness check after deploy, and automatic rollback, are on the [roadmap](../../README.md#roadmap).
- Deploys build and run from the host's Git clone, not from versioned artifacts, and apply to everything pushed to `main`.
- Systemd unit changes, the SQLite migration, Kafka, Caddy, the dashboard (Netlify), and the firmware are not deployed by this workflow.
- The Pi needs passwordless sudo for the two restart commands and the serving host's deploy user needs Docker access.

## Related

[Deployment: CI/CD](../deployment.md#continuous-integration-and-deployment), [ADR 0008](0008-tailscale-for-private-connectivity.md)

# ADR 0008: Tailscale for private connectivity between sites

**Status:** Accepted
**Recorded:** 2026-10-28

## Context

The Pi sits behind a home network. Kafka and the serving host run on AWS. The Pi must reach Kafka, and the serving host must reach Kafka, without exposing the broker to the public internet and without opening inbound ports on the home network. Kafka's configuration in this project uses `PLAINTEXT` listeners, so the network must protect the traffic.

## Decision

Use Tailscale to connect the Pi, the Kafka host, and the serving host. The Kafka broker listens only on its Tailscale address (and the controller on loopback). The producer and the live consumer use that address as `KAFKA_BOOTSTRAP_SERVERS`. The Pi's producer unit orders after `tailscaled.service`. Public exposure is limited to Caddy on the serving host (ports 80 and 443). Redis has no published port, and the API is bound to `127.0.0.1`.

CI deploy jobs also join the tailnet as an ephemeral node ([ADR 0009](0009-github-actions-deployment-over-tailscale-and-ssh.md)).

## Consequences

- Kafka is reachable only from tailnet members, and traffic between nodes is encrypted by Tailscale, so TLS on Kafka is not needed for transport security today.
- The Pi connects outward to Kafka, so the home network needs no inbound port forwarding for it.
- Tailscale becomes a dependency: if it is down, the Pi buffers in SQLite and the consumer's Kafka access stops until it recovers.
- Tailscale installation, authentication, and ACLs are configured by hand and are not in the repository.
- MQTT is separate: devices connect to Mosquitto on the Pi's LAN address with password authentication.
- Kafka TLS and SASL remain an option for later ([roadmap](../../README.md#roadmap)).

## Related

[Architecture](../architecture.md#communication-and-dependencies), [Infrastructure README](../../infrastructure/README.md#6-networking-and-security)

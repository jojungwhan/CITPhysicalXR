# ADR 0005: Independent scoped CIT authentication and same-origin console

- Status: Accepted
- Date: 2026-08-21

## Context

Loopback location is not authentication, and Agent Mesh identities represent a different authority. The instructor console controls session assignment, arming, and emergency operations.

## Decision

CIT issues independent random credentials, persists only domain-separated hashes, and binds each identity to roles, site/room/session scope, explicit permissions, expiry, and revocation. Fabric routers deny by default. The standalone Fabric service serves its console from the same origin while the upstream classroom runtime retains its own authority and database. Browser bearer material is held only in memory and never in URLs or Web Storage; WebSockets authenticate without query credentials and enforce exact origins.

## Consequences

- Administrator, instructor, student, observer, agent, and adapter credentials are not interchangeable.
- Every privileged mutation is auditable under a stable actor identity.
- Initial token bootstrap needs an operator workflow and protected local secret handling.
- Classroom-runtime tokens and Fabric credentials are intentionally not interchangeable; operators must choose the correct console and port.

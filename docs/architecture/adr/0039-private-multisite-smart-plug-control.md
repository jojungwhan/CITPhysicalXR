# ADR 0039 — Private multi-site smart-plug control

- Status: accepted
- Date: 2026-09-15

## Context

The owner needs one Android phone to control Matter-compatible Tapo plugs at
CIT Coding 학원 and at home while the phone is away from either LAN. Matter
device traffic is local IPv6/mDNS traffic, so a phone on 5G cannot safely act as
the Matter controller for both sites. Publishing the complete Control Tower or
its physical-device API would also expand a narrow power-control requirement
into broad remote actuator access.

## Decision

Each physical site has its own always-on gateway on the same LAN as its plugs.
The gateway owns that site's Matter fabric and connects the plug adapters to a
loopback Control Tower runtime. The academy gateway is the existing Linux host;
home needs a Raspberry Pi, mini PC, NAS, or equivalent always-on Linux host.

The phone and both gateways join one private Tailscale network. Each gateway
uses Tailscale Serve, never Funnel, to mount only
`/api/v1/fabric/remote-plugs/` over tailnet HTTPS. The runtime additionally
returns 404 for every other route when the request Host is the configured
Tailscale name. Tailnet grants should allow only the owner's identity to reach
TCP 443 on gateways tagged `tag:cit-plug-gateway`.

The application boundary remains narrower than the network boundary:

- A site provisions a separate random identity and HMAC secret for each of up
  to eight paired phones. Each phone has an independent replay counter.
- The phone signs a timestamp, UUID, monotonically increasing per-site
  sequence, and an explicit desired boolean state.
- State reads and power writes use separate signing domains, and the desired
  ON/OFF boolean is part of the signed power payload. Changing it or replaying
  a request invalidates the signature.
- The caller cannot submit a Matter node ID. It can affect only the exact group
  selected by the local operator, with a maximum of eight plugs.
- A command is attempted once. It is never queued, retried, or replayed after a
  network outage.
- ON fails closed for the whole saved group when any selected plug is
  unavailable. OFF remains best-effort so every reachable load can still move
  toward the safe state, while the response reports the incomplete group.
- Normal Fabric arming, command lifecycle, adapter authorization, audit, and
  idempotency boundaries still apply.

The Android companion stores up to eight independent site pairings and presents
separate ON and OFF actions for each. Its widget exposes the first two paired
sites. Existing unlock and camera automation remains bound to the primary
site's local Wi-Fi origin and never uses the remote route.

At a gateway, additional paired phones receive only manual remote plug control;
the original primary phone retains the local unlock/camera identity. The local
administrator can revoke all paired phones together.

The Linux runtime receives two unrelated local credentials. The administrator
credential is not inherited by plug-adapter children. A second static bootstrap
identity is restricted to the Matter plug plugin, one site and room, and only
adapter connect/event/node-write permissions. Rotating the environment files
and restarting the runtime invalidates the prior adapter credential.

## Consequences

- Remote control continues to work if TP-Link's cloud is unavailable, but only
  while the site's power, internet, Tailscale, gateway, Matter controller, and
  plug LAN are working.
- There is no command ambiguity after a delayed response: every action says ON
  or OFF and a separate status request can verify the result.
- Each site requires an always-on host and its own commissioning/state backup.
- A phone must be paired once at each site. Removing a site from the phone does
  not silently authorize a replacement phone at that gateway.
- Remote control is intentionally limited to switchable plugs. Robots, drones,
  printers, cameras, the Studio, Fabric credentials, and arbitrary endpoints do
  not become remotely reachable through this decision.

## Rejected alternatives

- Tapo cloud control: convenient, but adds a vendor account/cloud dependency and
  bypasses the existing Matter/Fabric safety and audit boundary.
- Port forwarding or Tailscale Funnel: makes a physical control surface public.
- One controller routed across both LANs: Matter discovery and operational
  traffic belong with each site and become brittle across routed boundaries.
- A generic remote Fabric bearer token: grants much more authority than the
  requested fixed smart-plug group.

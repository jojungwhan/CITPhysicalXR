# ADR 0034: Wearable smart-plug control through exact Fabric roles

- Status: superseded in part by ADR 0035
- Date: 2026-08-26

## Context

The standalone smart-plug panel can operate cloud-independent Matter plugs, but
G2 and Meta device control previously projected only ground robots and the Tello
fleet. Bypassing the Fabric from a wearable would duplicate Matter logic, expose
vendor credentials, and omit the existing electrical safety policy.

## Decision

The `glasses-device-control` course owns up to eight optional
`power_output_N` roles consuming `power.switch.set`. Agent Mesh projects only
assigned, connected roles to the wearable inventory. G2 presents every exact
plug plus an **all smart plugs** selection; the Meta/G2 voice grammar supports
the same all-plug and numbered commands in English and Korean.

Wearables publish only `power_on` or `power_off` structured intents. Declarative
flows map them to the canonical boolean command. A mixed lesson retains its one
session safety profile, while Fabric applies electrical rules from the target
capability and the Matter adapter applies device-level validation. Turning on
requires explicit confirmation and a physically active, armed session. Turning
off needs no second UI confirmation but remains an authenticated, confirmed,
role-scoped intent.

**Activate all** never turns a plug on. **Stop all** includes `power_off` for
every assigned plug. The control path contains no Matter setup code, vendor
account, local key, or proprietary cloud credential.

## Consequences

- Newly created glasses-control lessons auto-assign distinct connected plugs to
  numbered roles and keep later roles available for manual assignment.
- G2, Meta, the instructor console, and Matter adapters share one command and
  safety path.
- Group actions fan out concurrently, while exact selections remain independently
  traceable by role, node, correlation ID, and command lifecycle.
- Existing version 1.0 glasses-control sessions must be replaced by a version
  1.1 session before plug roles can appear.
- Physical G2/Meta-to-plug behavior still requires the hardware checklist; the
  automated suite provides schema, parser, routing, and simulator evidence only.

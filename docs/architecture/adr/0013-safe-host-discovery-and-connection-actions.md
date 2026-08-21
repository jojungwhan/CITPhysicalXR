# ADR-0013: Separate hardware candidates from connected Fabric nodes

Status: accepted, 2026-08-21.

## Context

Tutors need one place to find USB, Bluetooth, Wi-Fi, local-service, robot,
drone, glasses, agent, and smart-device integrations. A LAN or operating-system
match is not proof that a device is authenticated, healthy, or safe to control.
In particular, Tuya/Gosund presence does not provide its local key, a generic
LAN host is not a RoboMaster, a paired Bluetooth name is not fresh MindWave
data, and a visible Tello SSID is not a completed SDK handshake.

## Decision

The same-origin Fabric console exposes a separately modelled discovery report:

```text
not checked → found / ready / setup needed → adapter-connected Fabric node
```

The persistent Windows runtime invokes one fixed repository-owned PowerShell
probe. The probe may inspect PnP state, services, installed commands, loopback
ports, configured encrypted-profile presence, physical Wi-Fi adapters, visible
Tello SSIDs, and incoming RoboMaster STA broadcasts. It reuses the preserved
Brain2Devices Tello radio helper through its result-file boundary. It never
accepts a browser-supplied command, path, address, credential, or arbitrary URL,
and it sends no motor, flight, switch, agent, media, or SDK command.

Discovery candidates are not registered as nodes. Only an authenticated
adapter handshake can create a connected capability node. Tuya/Gosund devices
remain exact-profile-bound; discovery returns neither device IDs, addresses,
local keys, nor tokens.

Connection actions are a second, instructor-only allowlist. It contains the
preserved Brain2Devices operations for a MindWave connection and grounded Tello
SDK/radio handshake, plus fixed repository-owned launchers for Agent Mesh,
configured smart plugs, and the RoboMaster/Leap slice. The physical robot and
plug launchers use a connect-only mode: they register and bind nodes to an
unstarted lesson without arming the session or creating the adapter activation file. A
plug connection performs only its backend state read. Tello actions require an
explicit grounded/propeller confirmation and still cannot take off, land, move,
or stop motors. Actions and denials are audited. There is no arbitrary process,
shell, URL, SDK-text, or datapoint endpoint.

## Consequences

- Tutors can distinguish physical discovery, software readiness, one-time
  setup, and actual Fabric attachment in one screen.
- New physical adapters remain additive; candidate discovery does not change
  command routing or weaken adapter authentication.
- A scan can honestly say that a USB Wi-Fi radio is ready while no powered
  Tello is visible, or that Agent Mesh is running while no glasses are recent.
- Hardware still requires one-time vendor-specific setup where no safe generic
  handshake exists. Once configured, supported adapters can be started from
  their card; the UI shows the exact next step for the remaining cases instead
  of claiming automatic connection.
- Brain2Devices remains the system of record for Tello/MindWave hardware until
  their canonical Fabric adapter slice passes the later safety gate.

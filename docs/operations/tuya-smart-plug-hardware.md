# Tuya-compatible smart-plug hardware runbook

This runbook covers one approved Tuya or Tuya-LAN-compatible Gosund outlet.
Brand alone is not compatibility evidence. The exact model, firmware, protocol
version, boolean switch DPS, private IPv4 address, device ID, and local key must
be known before live startup.

The first implementation is local-only: TinyTuya 1.20.0 talks directly to the
plug on the classroom LAN. No vendor-cloud command, scan result, device ID,
local key, or arbitrary datapoint enters the Fabric.

## Load restrictions

Use a low-risk, nonessential test load such as a small classroom lamp. Do not
connect heaters, kettles, cooking appliances, medical equipment, refrigerators,
network infrastructure, host computers, battery chargers, motors, or any load
whose sudden power loss or unattended activation could cause harm.

The adapter requests off when it starts, stops, loses its Fabric connection, or
receives the instructor stop. A plug that has lost Wi-Fi cannot receive a new
off packet; physical HIL must characterize that limitation before classroom
approval. The UI state is evidence of the last verified LAN response, not a
substitute for observing the actual load.

## 1. Start and test the simulator

```powershell
pnpm hardware:fabric:windows -- -Mode Start
$fabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
pnpm hardware:plug:windows -- -Mode Preflight -SharedFabricRoot $fabricRoot
pnpm hardware:plug:windows -- -Mode Start -SharedFabricRoot $fabricRoot
pnpm hardware:fabric:windows -- -Mode CopyCredential
```

Open <http://127.0.0.1:8766/fabric>, connect, select the created
`smart-plug-control` session, and confirm `classroom_plug` is assigned. Use
**Turn on**, then **Turn off**. Confirm `power.switch.state` and the command
lifecycle appear, then run:

```powershell
pnpm hardware:plug:windows -- -Mode Verify -SharedFabricRoot $fabricRoot
pnpm hardware:plug:windows -- -Mode Stop -SharedFabricRoot $fabricRoot
```

## 2. Obtain and protect the LAN profile

Use the TinyTuya project's documented wizard/device-file procedure to obtain
the exact device ID and 16-character local key. Do not paste a Tuya cloud access
ID/secret into CIT. Reserve the plug's LAN address in the classroom router.

Stop the simulation component, then configure the hardware profile. The script
prompts for the device ID and local key without echo and stores their JSON as a
current-Windows-user DPAPI ciphertext outside the repository:

```powershell
pnpm hardware:plug:windows -- -Mode Configure `
  -Vendor gosund `
  -Model "Exact model printed on outlet" `
  -DeviceAddress 192.168.1.40 `
  -ProtocolVersion 3.3 `
  -SwitchDps 1
```

Use `-Vendor tuya` for a Tuya-branded device. DPS 1 is common but not universal;
never guess or expose an arbitrary DPS through the Fabric.

## 3. Read-only live preflight

Restart the shared Fabric with physical dispatch enabled. This enables the
policy path but does not turn on or arm any outlet by itself:

```powershell
uv sync --all-packages --extra smart-plug-lan --frozen
pnpm hardware:fabric:windows -- -Mode Stop
pnpm hardware:fabric:windows -- -Mode Start -AllowPhysical
pnpm hardware:plug:windows -- -Mode Preflight -Live -SharedFabricRoot $fabricRoot
```

The live preflight only reads the configured boolean switch state. It must
report `PASS read-only Tuya LAN status`. Failure means the exact model is not
approved; check the address, local key, protocol, DPS, LAN isolation, and
firmware without bypassing validation.

The `smart-plug-lan` extra is intentionally absent from default CI because its
native crypto dependency uses a licence family outside this repository's
default allowlist. Restore the ordinary development environment after hardware
work with `uv sync --all-packages --frozen`.

## 4. Live UI test

Place the approved lamp where the instructor can see it and start the adapter:

```powershell
pnpm hardware:plug:windows -- -Mode Start -Live -SharedFabricRoot $fabricRoot
```

Startup drives the outlet off, registers it, binds `classroom_plug`, and creates
the explicit physical session. In the UI confirm the red safety state and exact
device name before selecting **Turn on**. Then:

1. Confirm the lamp and UI both show on.
2. Select **Turn off** and confirm both show off.
3. Turn on once more and use the red **Emergency stop**; confirm off.
4. Repeat, then stop only the component; confirm off and that other Fabric
   nodes remain connected.
5. With a safe observer present, record behavior for Fabric disconnect, plug
   Wi-Fi loss, adapter termination, and power restoration. Never infer safe-off
   where the outlet could not receive the command.

Verify and stop:

```powershell
pnpm hardware:plug:windows -- -Mode Verify -SharedFabricRoot $fabricRoot
pnpm hardware:plug:windows -- -Mode Stop -SharedFabricRoot $fabricRoot
```

Record model, firmware, protocol version, DPS, TinyTuya version, command
latency, failure behavior, operator, date, and observed load. Simulator results
must never be reported as hardware evidence.

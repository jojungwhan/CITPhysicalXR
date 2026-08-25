# Cloud-free Matter smart plugs on Windows

This is the recommended smart-plug setup for a new CIT classroom or business
site. It uses a Matter fabric owned by the local CIT computer. It requires no
proprietary vendor app, account, cloud API, device ID, or local key.

This removes the vendor cloud from CIT's setup and control path. It cannot
guarantee that third-party plug firmware never attempts optional outbound
traffic. A site that requires a network-enforced air gap should place approved
plugs on an IoT VLAN that denies internet egress while permitting the CIT host's
local IPv6 and mDNS Matter traffic.

## Hardware compatibility gate

Use a plug only when its product label or packaging explicitly shows all of the
following:

- Matter support
- a Matter QR code or 11/21-digit manual setup code
- Wi-Fi support (the current Windows reference path does not provision Thread
  plugs)

A product name alone is not enough. The label or packaging must explicitly show
Matter support and a setup code; CIT does not replace proprietary firmware.

## Tapo P110M

The Tapo P110M is supported through its standard Matter interface. CIT does not
use the Tapo app, a TP-Link account, TP-Link's cloud API, a device ID, or a
vendor local key.

For CIT-owned, cloud-independent setup:

1. Find the Matter QR/manual setup code on the plug casing or packaging.
2. If the plug is new or belongs to another Matter fabric, hold **Reset for 10
   seconds** to factory-reset it.
3. Power-cycle the plug. Its Matter setup mode remains available for 15 minutes
   after power-up; power-cycle it again if that window expires.
4. Keep the Windows computer on the classroom LAN with local IPv6 and mDNS.
   Commission the plug onto the configured **2.4 GHz Wi-Fi** from Classroom
   Control.

The generic Matter adapter always exposes bounded on/off and verified state for
a standard `0x010A` endpoint. A P110M with firmware that exposes the standard
Matter 1.3 Electrical Power/Energy Measurement clusters additionally publishes
`telemetry.power.electrical` with W, V, A, kWh, Hz, and power factor fields.
Older firmware or a controller/firmware combination without those clusters
continues to work for on/off; CIT does not invent or retrieve proprietary
telemetry. Firmware availability varies by hardware region, and CIT deliberately
does not run vendor OTA updates.

References: [TP-Link Matter setup guide](https://www.tp-link.com/us/support/faq/3520/),
[P110M user guide](https://www.tp-link.com/us/document/124264/),
[P110M firmware notes](https://www.tp-link.com/us/support/download/tapo-p110m/),
and the [CSA Matter 1.3 announcement](https://csa-iot.org/newsroom/matter-1-3-specification-released/).

## One-time business-site installation

Place the repository in its permanent location. On a normal Windows 11
computer, double-click:

```text
install-cit-business-site.cmd
```

The bootstrap installs PowerShell 7 first when necessary, then opens the fixed
CIT installer. It uses `business-site` and `classroom-a` as the initial logical
site and room names.

For a technician-selected site and room, run this in PowerShell 7 instead:

```powershell
pwsh -NoProfile -STA -File .\tools\hardware\install-business-site.ps1 `
  -Mode Install `
  -SiteId cit-business `
  -RoomId classroom-a `
  -InstallPrerequisites
```

The prerequisite option installs the pinned Node.js runtime, `uv`, and Visual
C++ build tools when they are missing. Windows may show an administrator prompt
for those signed packages. The installer then:

1. creates a non-secret site/room profile under `%LOCALAPPDATA%\CITPhysicalXR`;
2. installs locked Python and JavaScript dependencies;
3. builds the CIT UI and local adapters;
4. starts the controller on loopback only;
5. asks once for the classroom Wi-Fi name and password;
6. sends the password to the controller through process stdin, not a command
   line or Fabric message; and
7. installs **CIT Classroom Control** on the Desktop and Start menu.

Use `-SkipWifiConfiguration` only if commissioning Ethernet devices or if a
technician will configure Wi-Fi later. No Wi-Fi password is stored in the site
profile or repository. The local Matter controller retains the network
commissioning material in its current-user storage.

Check the installation without displaying any secret:

```powershell
pnpm hardware:install-business:windows -- -Mode Status
```

## Add a real plug from the single UI

1. Connect the CIT Windows computer to the business/classroom LAN. Keep Windows
   Bluetooth enabled and allow local IPv6 and mDNS on the private network.
2. Plug in an approved low-risk load, such as a classroom lamp. Start with the
   load's own switch off.
3. Factory-reset the Matter plug if necessary, then hold its pairing button
   until the pairing indicator flashes.
4. Open **CIT Classroom Control** from the Desktop.
5. Choose **Find devices**.
6. On **Matter smart plugs**, complete
   the three numbered steps. If step 1 says **Required**, enter the classroom's
   exact 2.4 GHz Wi-Fi name and password and choose **Save Wi-Fi locally**. The
   password goes only to the loopback controller through stdin and is not
   written to the Fabric audit log.
7. Put the plug in setup mode, choose **Find devices** again, enter the exact
   code printed beside its Matter QR label, and choose **Add plug locally**.
8. Wait up to three minutes. Keep the plug powered and within Bluetooth range
   during commissioning.
9. The plug appears in **Everything connected to this classroom**. Connection
   places the approved endpoint in the off safe state.
10. Choose **Classroom smart plug** and connect the plug. No separate control
    activation step is needed.
11. Test **Turn on**, then **Turn off**. The first direct command prepares the
    local control session automatically. Confirm both the physical load and the
    normalized state shown in CIT.
12. For a compatible P110M firmware, open the sensor area and confirm
    **Electrical telemetry** reports plausible values. Absence of this optional
    card does not invalidate standard on/off support.

The adapter accepts exactly one boolean command. Duplicate command IDs do not
repeat an action, and adapter/Fabric shutdown requests the off safe state.

On Windows, the launcher uses the pinned Python Bleak proxy to bridge the local
Bluetooth radio to the loopback Matter controller. This avoids the less reliable
Windows Noble connection path and does not contact a vendor service. The
launcher also selects the active physical LAN interface for Matter traffic, so
overlay adapters such as VPNs do not take precedence over the classroom LAN.

## Move or extend the setup

For another Windows computer at the business location:

1. install CIT with a new room ID;
2. connect that computer to the same local network;
3. remove each plug from the old Matter fabric or factory-reset it; and
4. add it from the new computer's Classroom Control page.

Do not copy `%LOCALAPPDATA%\CITPhysicalXR\matter`, Fabric DPAPI files, or private
controller keys between Windows accounts/computers. They are machine/operator
security material, not a portable configuration bundle. Matter multi-admin
handoff is not yet exposed in the CIT UI, so recommissioning is the supported
migration path.

The new site can operate its plugs if the internet and vendor services are
unavailable. The Windows host, LAN/Wi-Fi, Matter controller, and plug must still
be powered and reachable.

## Troubleshooting

- **No Matter code on the product:** use different Matter-certified hardware.
  The Matter form accepts only its printed QR or manual setup code.
- **Bluetooth unavailable:** confirm Windows Bluetooth is on and the native
  build prerequisites completed. The Matter status should report **Windows BLE
  proxy: ready**. Check `matter-ble-proxy.stderr.log` and
  `matter-controller.stderr.log` under
  `%LOCALAPPDATA%\CITPhysicalXR\matter\logs`.
- **Wi-Fi commissioning fails:** verify the configured SSID/password, use the
  Wi-Fi band supported by the plug (often 2.4 GHz), and keep local IPv6/mDNS
  enabled.
- **Already commissioned:** remove the old fabric using its current controller
  or factory-reset the plug, then retry.
- **Commissioned but offline:** check power and that Windows and the plug can
  communicate on the local network; client isolation blocks Matter.
- **Adapter failure:** keep the load off and run
  `pnpm hardware:matter:windows -- -Mode Status`. `available=True` confirms the
  commissioned Matter endpoint is reachable; **Running Fabric adapters** is
  the separate count that confirms those endpoints are connected to the CIT
  UI. Inspect the per-node logs under
  `%LOCALAPPDATA%\CITPhysicalXR\matter\logs`. Command diagnostics include the
  node, command, active session, requested/verified boolean state, state-event
  session, and shutdown safe-state result. Fabric rejection diagnostics include
  the exact rejection code, frame type, node, session, and correlation ID, but
  deliberately exclude credentials and event payloads.

Run software-only verification with:

```powershell
uv run pytest tests/adapters/test_matter_smart_plug.py `
  tests/runtime/test_fabric_discovery.py
pnpm exec vitest run apps/studio-web/src/fabric-client.test.ts `
  apps/studio-web/src/fabric-sensors.test.ts
```

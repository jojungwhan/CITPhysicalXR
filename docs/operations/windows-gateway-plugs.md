# Gateway plugs in Windows Control Tower

Windows can show and control plugs owned by a Linux gateway without copying its
Matter controller identity. The **Gateway smart plugs** panel shows each outlet,
individual ON/OFF controls, and controls for the saved group. Local classroom
devices stay in the same Control Tower window.

The gateway and Windows PC must both be connected to Tailscale. The browser
calls the authenticated Windows runtime; only that runtime signs requests to
the gateway's existing private HTTPS plug API. A desktop pairing can operate
only the gateway's saved remote-plug selection. It cannot access phone-unlock
automation. Individual selections are signed and checked against that group.
Existing phone requests continue to control their saved group unchanged.

## Pair a Windows PC

Update the gateway runtime to a version supporting desktop pairings first.
From the Windows checkout, run:

```powershell
pwsh -NoProfile -File tools/hardware/connect-plug-gateway.ps1 `
  -SshTarget sb@172.30.1.10 `
  -IdentityFile "$env:USERPROFILE\.ssh\agentmesh_sb_h410m_ed25519" `
  -GatewayRepository /home/sb/dev/cit-plug-gateway-20260921
```

The script uses an existing authorized SSH login to request a new desktop
pairing from the gateway's loopback administrator API. The gateway administrator
credential stays on Linux. The new pairing is encrypted for the current Windows
user in `interaction-fabric/secrets/plug-gateways.dpapi`. Existing phone pairings
and plug selections are preserved. Rerunning the command reuses an existing
valid desktop pairing and refreshes remembered plug names.

Restart Windows Control Tower to load the pairing. Its launcher passes the
decrypted configuration directly to the runtime process. The replay counter is
committed to `runtime/gateway-sequences.sqlite3` before each signed request and
survives restarts. Do not copy a pairing to another PC or reset its counter;
pair each PC independently. A gateway supports eight paired clients in total.

## Connection and command results

The panel refreshes automatically. When Tailscale or the gateway is unavailable,
remembered outlets remain visible with unknown states and disabled controls.
Opening the panel sends status requests only. Turning on the complete group
requires every saved plug to be available. Turning off the group can report a
partial result when an outlet is unavailable.

A timeout has an unknown result. Control Tower does not retry power requests;
it refreshes status before another explicit action. Command acceptance and
observed outlet state are shown separately. Commands are audited on both PCs.
Desktop controls require an unscoped operator with command permission and
physical device dispatch enabled in Windows.
The main **Stop all devices** button also sends OFF to every configured gateway;
an unreachable gateway makes the stop result partial. Closing Windows Control
Tower leaves the independent gateway and phone controls running.

**Unpair all phones** in the gateway's existing settings also revokes desktop
pairings. Remove the corresponding local pairing or rerun the pairing script
after revocation. Never remove the Windows Matter migration marker to recover
gateway access.

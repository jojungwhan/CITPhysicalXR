# Academy smart-plug gateway

Deployed on 2026-09-21 to the always-on Linux computer:

- SSH: `sb@172.30.1.10`; desktop access: `172.30.1.10:3389`.
- Phone origin: `https://sb-h410m-h.tailde052f.ts.net` through Tailscale.
- Release directory: `/home/sb/dev/cit-plug-gateway-20260921`.
- Gateway state: `/home/sb/.local/share/cit-physical-xr-gateway`.
- Environment files: `/home/sb/.config/citxr/remote-plug-*.env` (private).
- Managed plugs: `matter-13-ep1`, `matter-16-ep1`, `matter-1b-ep1`, `matter-1c-ep1`.
- Separate phone credentials: Galaxy Note10 and Z Flip4.

The existing academy Matter controller state was transferred while the Windows
controller was stopped. The plugs did not need factory resets. This Linux host
has no Bluetooth adapter; its installer uses `--disable-bluetooth`. Bluetooth
is not needed to operate these already commissioned Wi-Fi plugs.

The three user services are enabled, with user lingering enabled for boot:

```bash
systemctl --user status citxr-remote-plug-runtime.service \
  citxr-matter-controller.service citxr-matter-gateway.service
tailscale serve status
```

Only `/api/v1/fabric/remote-plugs/` is published to the private tailnet. The
runtime and Matter controller listen on loopback ports 8766 and 5580. The
existing public simulation service is separate. Phones must keep Tailscale
connected; USB and the Windows computer are not needed after pairing.

The original Windows controller data is retained as a migration backup. A
`controller-migration.json` marker under `%LOCALAPPDATA%\CITPhysicalXR\matter`
prevents the Windows launcher from starting the same Matter identity again.
Do not remove the marker or run both copies of the controller. For rollback,
stop the Linux services first and transfer its latest controller state back;
the original Windows copy becomes stale as the live gateway operates.

Manual ON/OFF control is enabled. Phone-unlock automation is disabled on this
remote gateway. Service startup and shutdown put managed plugs in the OFF state.

Validation: both the Z Flip4 and Galaxy Note10 sent ON and OFF, and each reported
all four plugs ON after ON. The Z Flip4 also successfully requested status with
Wi-Fi disabled. Direct Matter reads after OFF confirmed all four outlets OFF.
Both phones use companion version 2.0.0 with separate request counters. The
runtime restart check preserved both pairings and recovered all four adapters.

The Note10's Tailscale app was installed from the checksum-verified
[official Android APK](https://pkgs.tailscale.com/stable/), version 1.102.4,
because its Play Store required account reauthentication. This APK installation
needs manual Tailscale updates; use the Play Store installation when that phone's
store account is available again.

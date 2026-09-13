# Creality K1 Max from Control Tower

The 3D-printer panel is safe to open during an existing print. Its default
**Current print protected** state performs no network request to
`172.30.1.55`. You may add an STL or 3MF to the local workspace, but all later
steps remain disabled.

## Current safe mode

- Do not change any printer environment setting while the existing job is
  running.
- Do not use **Print finished — verify standby** until the machine has been
  inspected physically.
- The printer is intentionally absent from device **Select all**, lesson and
  demonstration controls.
- Preparing, uploading, and starting are separate actions. Upload never starts
  a job.

If the panel says **Setup required** or **Connection: Not verified**, use
**Download G-code** and finish the transfer manually in Creality Print. Do not
guess a proprietary API port.

## Enable documented status after the current print

Only perform this setup after the printer is physically idle:

1. Confirm the exact K1 Max generation, 0.4 mm nozzle, loaded material, clean
   and empty build plate, and the matching installed Creality Print profile.
2. Confirm that this printer explicitly exposes a documented Moonraker HTTP
   endpoint and record its port. Do not enable the feature based only on an open
   proprietary Creality port.
3. Stop Control Tower normally. In the launcher environment, set:

   ```powershell
   $env:CITXR_CREALITY_ADDRESS = "172.30.1.55"
   $env:CITXR_CREALITY_MOONRAKER_PORT = "<verified-port>"
   $env:CITXR_CREALITY_MONITORING = "true"
   ```

4. Start Control Tower. Inspect the printer physically, then select
   **Print finished — verify standby**. This makes one read-only state check.
   Anything other than Moonraker `standby` keeps the workflow locked.

Monitoring alone cannot upload or start a print.

## Enable upload and start

After read-only status has been accepted with an idle printer, stop the control
center and additionally set:

```powershell
$env:CITXR_CREALITY_REMOTE_WRITES = "true"
```

Physical-actuation mode must also be enabled by the classroom launcher. If the
Moonraker installation requires an API key, set it only in the runtime process:

```powershell
$env:CITXR_CREALITY_API_KEY = "<printer-local-api-key>"
```

Never place the key in browser storage, a site template, or source control.
Restarting restores the current-print lock even when these settings remain.

## Prepare and print

1. Add one `.stl` or `.3mf` model, at most 64 MiB. This copies it locally only.
2. Select the exact K1 Max, nozzle, PLA, and process profile. Prepare G-code.
3. Review the orientation, scale, supports, temperatures, material, plate, and
   generated G-code. Download it if a manual Creality Print handoff is desired.
4. Select **Upload only**. Confirm the panel says it was uploaded and not
   started.
5. When ready, select **Start print**, complete both physical checkboxes, and
   use the one-time confirmation within two minutes.

If start returns an unknown outcome, do not click it again. Inspect the printer
and refresh status first. The control center never retries a print start.

## Optional installation override

The default slicer location is
`C:\Program Files\Creality\Creality Print 7.2\CrealityPrint.exe`. To use another
installed directory, set `CITXR_CREALITY_INSTALL_ROOT` to that absolute folder
before starting the runtime. Only profiles found inside that installation are
shown as available.

# Install another Windows classroom computer

Status: implemented for Windows 11 x64. A clean-machine installation and each
physical device still require their separate hardware acceptance checklists.

## Tutor workflow from the single page

1. On the working tutor computer, open **CIT Classroom Control** from the
   Desktop or Start menu.
2. Choose **Install another PC** in the header.
3. Download **Windows setup ZIP** and **this site template**.
4. Copy both files by USB or another trusted private transfer. The local Fabric
   intentionally does not bind to the classroom LAN merely to distribute a
   large installer.
5. On the new computer, extract the ZIP. Put `cit-site-template.json` beside
   `Install-CIT.cmd`, then double-click `Install-CIT.cmd`.
6. Approve the prerequisite installers. Enter the new classroom Wi-Fi password
   only when the local PowerShell prompt requests it.
7. When Classroom Control opens, choose **Find devices** and follow each card.

The JSON template contains only `schemaVersion`, `siteId`, and `roomId`. It
never contains an access token, network secret, device credential, or path.

## What the transfer package does

The bootstrap verifies the inner `payload.zip` against the SHA-256 value in
`bundle-manifest.json`, then extracts the source to:

```text
%LOCALAPPDATA%\CITPhysicalXR\app\<Git revision>
```

Existing verified revision directories are reused. An existing directory whose
release metadata does not match is rejected; setup never deletes or overwrites
it. The normal business-site installer then:

- installs PowerShell 7.4+, Node.js 22, uv, Git, Python, and the Visual C++ build
  tools when absent;
- restores exact `pnpm` and `uv` locks and builds the local UI/runtime;
- prepares the independent Matter, Brain2Devices, LEGO, Sphero BOLT, and
  Dash/Dot boundaries;
- creates the Desktop and Start-menu **CIT Classroom Control** shortcut;
- starts the local Matter controller and optionally asks for classroom Wi-Fi;
- creates another verified transfer package so that computer can provision the
  next classroom computer.

Installation is network-assisted, not fully offline. Internet access is needed
to obtain pinned Microsoft, OpenJS, Python, npm, PyPI, and Git dependencies.
That dependency download is distinct from classroom operation: CIT does not use
a Tuya, Gosund, Tapo, Sphero, Wonder Workshop, or LEGO cloud account to control
the supported local devices.

## Integrity and credential boundaries

There are three integrity checks:

1. the release builder records the outer ZIP size and SHA-256 in
   `installation-manifest.json`;
2. the Fabric validates that immutable artifact before it starts and the browser
   verifies the downloaded bytes before saving them;
3. `Install-CIT.ps1` verifies the inner payload before extraction.

The authenticated download uses the bearer header. No credential appears in a
URL, browser history, site template, or bundle. Downloads are audited locally.
The HTTP route serves an existing artifact only; it cannot invoke Git,
PowerShell, a package manager, or a build.

The builder uses an explicit source allowlist and excludes at minimum:

- `.env`, local YAML, private keys, certificates, and database files;
- `%LOCALAPPDATA%` site/controller state, recordings, logs, and access tokens;
- Git metadata, dependency caches, virtual environments, build output, and
  downloaded artifacts;
- Brain2Devices and other external checkouts, which the installer obtains at
  their single-source-of-truth pinned revisions.

## New network and device setup

Do not copy `%LOCALAPPDATA%\CITPhysicalXR` state from the old computer.

- **Matter/Tapo P110M plugs:** factory-reset each plug at the new site and
  commission it from its printed Matter QR/manual code. Operational Matter keys
  and controller databases are site-local and are never transferred.
- **Sphero BOLT and Dash/Dot:** do not pre-pair in Windows; wake the exact robot
  and connect it from its CIT card over BLE.
- **LEGO with Pybricks:** do not pair in Windows; install the approved Pybricks
  firmware, use a unique advertised hub name, and select its port profile in
  CIT.
- **Leap Motion:** install/start the supported Ultraleap Tracking service and
  connect the controller by USB before scanning.
- **Tello:** each aircraft needs its normal local Wi-Fi path; multiple aircraft
  need one supported radio per aircraft. Confirm every aircraft is grounded.
- **RoboMaster S1:** reconnect through the documented AP/STA path and keep wheels
  clear until the separate arming step.
- **G2 and Meta:** install/authorize their separate Android companion paths and
  connect the phone by the documented USB or local Wi-Fi route.

Previously remembered connections on the old host are intentionally not copied.
After a successful connection on the new host, CIT can remember that local
connection action and use **Reconnect remembered devices** there.

## Technician build and verification

The page shows an unavailable state until a clean reviewed revision has a
bundle. Build it from the repository root:

```powershell
pnpm release:windows:bundle
```

Output is generated under `artifacts/windows-transfer/`, which is ignored by
Git. Restart Classroom Control so the Fabric validates the new manifest during
startup. A dirty tree is rejected unless a developer explicitly uses
`-AllowDirty`; such a development bundle must not be handed off as a release.

For source-checkout troubleshooting, the original installer remains available:

```powershell
pwsh -NoProfile -STA -File .\tools\hardware\install-business-site.ps1 `
  -SiteId cit-business -RoomId classroom-a -InstallPrerequisites
```

This command is a technician fallback, not a tutor startup requirement.

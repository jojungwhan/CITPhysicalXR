# Remote Matter smart plugs at CIT Coding 학원 and home

This runbook creates two independent, cloud-free plug sites controlled by one
Android phone over Wi-Fi or 5G.

The academy deployment on `172.30.1.10` is recorded in
[the deployment notes](academy-plug-gateway-deployment.md).

```text
Android companion
  ├─ private HTTPS through Tailscale Serve ── CIT Linux gateway ── local Matter ── CIT plugs
  └─ private HTTPS through Tailscale Serve ── home gateway      ── local Matter ── home plugs
```

Only the two signed state/power routes cross Tailscale. The Studio, Fabric
bearer API, Matter controller, adapter WebSocket, and administrator credential
remain on loopback. Do not configure router port forwarding, Cloudflare Tunnel,
or Tailscale Funnel for either physical gateway.

## 1. Prepare the gateways

Use the existing always-on CIT Linux computer at `172.30.1.10` for the academy.
That address remains useful for local RDP (`mstsc /v:172.30.1.10:3389`), but it
is not the phone's remote endpoint. Install a separate always-on Linux device on
the home LAN; a Raspberry Pi 4/5, small x86 PC, or NAS VM with Bluetooth for
first commissioning is sufficient.

On each gateway install:

- Node.js 22, Python 3.11–3.13, `uv`, and `pnpm` 10;
- Tailscale, logged into the same tailnet as the owner's phone;
- BlueZ and a usable Bluetooth LE adapter (`hci0` by default);
- Android platform-tools (`adb`) for the one-time companion pairing;
- this repository, on a local non-removable disk.

Then prepare the pinned repository dependencies:

```bash
pnpm install --frozen-lockfile
uv sync --frozen
pnpm build
```

Build companion version 2.0.0 on a machine with the Android SDK and make sure
`apps/control-tower-companion/app/build/outputs/apk/debug/app-debug.apk` exists
at the same repository path on the gateway:

```powershell
cd apps/control-tower-companion
./gradlew.bat :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

Find each gateway's full MagicDNS name (remove the final displayed dot if it
has one):

```bash
tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'
```

Allow the ordinary account that owns the repository to manage this machine's
Tailscale Serve configuration, then enable unattended user services:

```bash
sudo tailscale set --operator="$(id -un)"
sudo loginctl enable-linger "$(id -un)"
```

## 2. Install the CIT academy gateway

Run this as the ordinary Linux account that owns the repository, replacing the
example `*.ts.net` name with the exact name from the prior command:

```bash
bash tools/hardware/install-remote-plug-gateway-linux.sh \
  --site-id citcoding-academy \
  --site-name 'CIT Coding 학원' \
  --tailscale-host cit-academy.example-tailnet.ts.net \
  --network-interface eno1
```

The script creates mode-0600 environment files, three user services, a
loopback-only runtime and Matter controller, and one persistent tailnet-only
Serve mount. The Serve target repeats the mounted path because Serve strips the
mount prefix before proxying. It does not print either generated credential.
The earlier `loginctl enable-linger` command lets these user services start at
boot before this account logs in.

Check the private mount. The unsigned response should be a bounded 422 or 401,
not the Studio or health document:

```bash
tailscale serve status
curl -i -X POST -H 'Content-Type: application/json' --data '{}' \
  https://cit-academy.example-tailnet.ts.net/api/v1/fabric/remote-plugs/state
curl -i https://cit-academy.example-tailnet.ts.net/api/v1/fabric/healthz
```

The second request must be 404. From a device outside the tailnet, both URLs
must be unreachable.

Open a one-time local administrator session without displaying or copying the
long-lived credential. Run this inside the gateway desktop session; if no local
browser is available, the command prints a single-use URL valid for 90 seconds:

```bash
.venv/bin/python -m cit_runtime.fabric_local_console
```

## 3. Commission the academy plugs

The controller owns Bluetooth adapter `hci0` and stores its Matter fabric only
under the gateway state directory. Keep the Linux gateway and Tapo P110M plugs
on the same normal Wi-Fi/LAN; guest-client isolation must be off.

Use remote outlets only for approved low-risk loads such as lamps. Do not use
this path for heaters, cooking appliances, medical equipment, pumps, power
tools, or anything whose unattended startup could injure someone or cause
damage. Confirm the plug, wiring, and load ratings for the local region.

Save the 2.4 GHz Wi-Fi credentials through hidden interactive input, then reset
and commission each plug using its printed Matter code:

```bash
.venv/bin/cit-matter-setup configure-wifi
.venv/bin/cit-matter-setup commission
.venv/bin/cit-matter-setup inventory
systemctl --user enable --now citxr-matter-gateway.service
systemctl --user status citxr-matter-gateway.service
```

Adapter startup deliberately forces each plug OFF. Remote callers can never add
another node to the fixed local selection.

## 4. Pair the phone with the academy

Install Tailscale on Android, sign in as the authorized owner, and leave it
enabled. Enable Android USB debugging temporarily, connect the phone to the
academy Linux gateway, authorize that exact computer, and choose **Install and
pair companion** in the local Control Tower settings. Version 2 pairing adds
the academy without erasing an existing home pairing. Next, select only the
plug cards that this phone may control and choose **Save plug selection** in
the phone automation settings. Leave unlock automation disabled if only manual
ON/OFF control is wanted. Disable USB debugging again after pairing.

The companion should show **CIT Coding 학원** and **Available on Wi-Fi or 5G
through Tailscale**. Test Status, ON, and OFF first while physically beside the
load, then repeat with Wi-Fi disabled so the phone is actually using 5G.

A remote gateway supports up to eight separately paired phones, each with its
own secret and request counter. Pair additional phones the same way; existing
pairings remain valid. Additional phones have manual remote plug control only.
The local **Unpair all phones** action revokes every pairing at that gateway.

## 5. Add home

Repeat sections 1–4 on the home gateway with a distinct Tailscale hostname and
site identity, for example:

```bash
bash tools/hardware/install-remote-plug-gateway-linux.sh \
  --site-id home \
  --site-name 'Home' \
  --tailscale-host home-plugs.example-tailnet.ts.net \
  --network-interface eth0
```

Pairing from the second gateway adds **Home** alongside the academy. The app and
widget send separate per-site sequences and secrets.

## 6. Restrict the tailnet

Tag both gateways `tag:cit-plug-gateway`. In the Tailscale policy, replace the
example email with the owner's identity and merge this grant into the existing
policy rather than replacing unrelated rules:

```json
{
  "tagOwners": {
    "tag:cit-plug-gateway": ["autogroup:admin"]
  },
  "grants": [
    {
      "src": ["owner@example.com"],
      "dst": ["tag:cit-plug-gateway"],
      "ip": ["tcp:443"]
    }
  ]
}
```

This network grant is an additional lock. Every request still needs the
per-site HMAC, timestamp, unique event ID, and increasing sequence. Do not keep
the default allow-all tailnet grant if the intent is owner-only control.

## Operations and recovery

```bash
systemctl --user status citxr-remote-plug-runtime.service
systemctl --user status citxr-matter-controller.service
systemctl --user status citxr-matter-gateway.service
journalctl --user -u citxr-matter-gateway.service --since today
tailscale serve status
```

- A command that times out has an unknown result. Use **Status**; do not assume
  it failed and do not automate a retry.
- An accepted response confirms Fabric dispatch, not direct observation of the
  outlet. Use **Status** when the physical result matters.
- If any selected plug is offline, ON switches none of the group. OFF still
  switches every reachable plug toward the safe state and reports the partial
  result; physically verify anything unavailable.
- The supervisor checks local Matter inventory every 30 seconds. When a new or
  recovered plug appears, it safely restarts the adapters and attaches it.
- Back up the gateway state directories offline. They contain the Matter fabric
  and phone pairing secret; never copy them between CIT and home.
- To revoke all phones at one site, use that site's local Control Tower **Unpair
  all phones** action. Every phone must then be paired again at that site.
  Removing a card only on Android is not server-side revocation.
- To rotate gateway service credentials, rerun the installer. It restarts
  enabled services with the new credentials; this safely turns managed loads
  off while adapters reconnect.
- To remove remote exposure, run
  `tailscale serve --https=443 --set-path=/api/v1/fabric/remote-plugs/ off`.

Tailscale Serve is documented as tailnet-only HTTPS and honors tailnet access
rules: <https://tailscale.com/docs/features/tailscale-serve>. The exact CLI
flags used here are documented at
<https://tailscale.com/docs/reference/tailscale-cli/serve>. Current grant syntax
is documented at <https://tailscale.com/docs/reference/syntax/grants>.

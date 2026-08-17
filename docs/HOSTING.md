# Hosting the Studio at admin.secondbrains.org/citxr

- Status date: 2026-08-17
- What this describes: a **simulation-only** runtime, reachable through a
  Cloudflare Tunnel and gated by Cloudflare Access
- What this does not describe, and must not become: a way to drive a robot from
  the internet. See "Hardware" at the end, which is the part to read before
  connecting a hub to anything hosted.

## What it is

Until now `admin.secondbrains.org/citxr/index.html` served the built Studio as
static files. That page could not drive anything: it resolved the API to its own
origin, found none, and said the runtime was unreachable. That was correct
behaviour, and it is why the page was of no practical use.

Now a runtime runs on this machine as a user service, bound to loopback, serving
both the Studio and its API under the path `/citxr`. A tunnel rule maps
`admin.secondbrains.org/citxr` to it, and Cloudflare Access decides who gets
that far.

```text
browser ──► Cloudflare (Access policy) ──► cloudflared ──► 127.0.0.1:8791
                                                            citxr-runtime.service
                                                            simulation, fake devices
```

Three properties hold this together, and each is worth naming because losing one
loses the safety of the arrangement:

1. **The runtime never binds a routable interface.** It refuses to
   (`--allow-non-loopback` exists and is not used). The only route in is the
   proxy its owner configured on purpose.
2. **The hosted runtime has no physical devices.** It starts with no `--config`,
   so it has the fakes and `physical_enabled` is false. There is nothing for a
   visitor to move.
3. **Access is the gate, not the passcode.** The runtime's own instructor
   passcode is checked with a constant-time compare and has no rate limit or
   lockout. That is adequate for a loopback service and is _not_ adequate as the
   only thing between the internet and a token, which is why the Cloudflare
   Access policy is not optional.

## The local half — already done

`~/.config/systemd/user/citxr-runtime.service`, enabled and started:

```bash
systemctl --user status citxr-runtime.service
curl -s http://127.0.0.1:8791/citxr/api/health
```

- Serves under `/citxr` (`--url-prefix /citxr`). Anything outside that prefix is
  a 404, so a misrouted request cannot become a second way in.
- Data (projects, recordings) in `/home/sb/.citxr-hosted`; log in
  `/home/sb/.citxr-hosted/logs/runtime.log`.
- Instructor passcode in `/home/sb/.config/citxr/hosted.env`, mode 0600, read by
  the unit as `CITXR_INSTRUCTOR_PASSCODE`. It survives a restart, which a random
  per-run passcode does not.
- Rebuilding the Studio (`pnpm build`) is live: the runtime serves the `dist`
  directory from disk.

Rotate the passcode:

```bash
printf 'CITXR_INSTRUCTOR_PASSCODE=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(18))')" \
  > /home/sb/.config/citxr/hosted.env
chmod 600 /home/sb/.config/citxr/hosted.env
systemctl --user restart citxr-runtime.service
```

## The Cloudflare half — yours to do

`cloudflared` here runs from `/etc/cloudflared/token`, so its routes live in the
Cloudflare dashboard and cannot be edited from this machine.

**Do these in this order.** Measured on 2026-08-17,
`https://admin.secondbrains.org/citxr/index.html` answers `200` to a stranger
with no login — today that is harmless, because the page it serves is static and
drives nothing. Add the tunnel route before the Access policy and the same
anonymous request reaches a runtime that hands out tokens.

**1. Access application (Zero Trust → Access → Applications → Add → Self-hosted):**

| Field       | Value                               |
| ----------- | ----------------------------------- |
| Application | `admin.secondbrains.org/citxr`      |
| Policy      | Allow · Emails · `jc@citcoding.com` |

**2. Public hostname (Zero Trust → Networks → Tunnels → this tunnel →
Published application routes):**

| Field    | Value                    |
| -------- | ------------------------ |
| Hostname | `admin.secondbrains.org` |
| Path     | `citxr*`                 |
| Service  | `http://127.0.0.1:8791`  |

It must sit **above** the catch-all rule for `admin.secondbrains.org`; rules are
matched in order, and the existing rule would otherwise take the path first.
No path rewriting is needed or available — the runtime is served under `/citxr`
precisely because the tunnel forwards the path as it arrived.

WebSockets are already enabled for this tunnel's traffic in the sense that
Cloudflare proxies them by default; the event stream is `wss://…/citxr/ws/events`
and needs no separate rule.

**3. Check it:**

```bash
curl -sI https://admin.secondbrains.org/citxr/api/health   # 302 to the Access login, not 200
```

A `200` carrying JSON there means the Access policy is not covering the path,
and an anonymous visitor can join the classroom. That is the one outcome to
treat as a fault rather than a nuisance. (Before the tunnel route exists, this
path returns `200` with ContentRadar's HTML, which is its single-page-app
fallback answering for a path nothing else claims — not the runtime.)

## What was verified here

Against the service as it now runs, in a real browser at
`http://127.0.0.1:8791/citxr/index.html` — the same shape the tunnel delivers:

```text
signed in                          true
device cards                       Fake Leap Motion | Fake LEGO Hub | Fake Quest Client
drive outcome                      Accepted · completed
websocket url                      ws://127.0.0.1:8791/citxr/ws/events?token=…
api calls all under /citxr         true
page errors                        none
instructor join, stored passcode   200
instructor join, wrong passcode    403
same passcode after a restart      200
unprefixed /api/health             404
```

## Hardware

**Do not connect a hub to the hosted runtime.** The tunnelled service is the
simulation. A physical session belongs on the machine the robot is next to,
reached at `http://127.0.0.1:8791/`, which is what every milestone report means
by "the working console is local".

Concretely, on any runtime that a tunnel can reach:

- never pass `--config` (that is what connects hubs),
- never pass `--allow-non-loopback`,
- never add a remote origin to `DEFAULT_ALLOWED_ORIGINS`.

The reason is not fussiness about topology. The dead-man control (ADR-028) is
attested by a heartbeat from the page holding it, and the arming workflow
(FR-066) assumes an instructor who can see the robot. Both are ways of saying
that the person who may make something move is in the room with it. A tunnel
removes exactly that, and no Access policy puts it back.

If a hosted physical session is ever genuinely wanted, it is a design change with
its own ADR, not a configuration change.

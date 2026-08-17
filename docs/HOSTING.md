# Hosting the Studio at admin.secondbrains.org/citxr

- Status date: 2026-08-18
- What this describes: a **simulation-only** runtime, published through the
  tunnel that already serves this host, and gated by its own join passcode
- What this does not describe, and must not become: a way to drive a robot from
  the internet. See "Hardware" at the end, which is the part to read before
  connecting a hub to anything hosted.

## What it is

Until now `admin.secondbrains.org/citxr/index.html` served the built Studio as
static files. That page could not drive anything: it resolved the API to its own
origin, found none, and said the runtime was unreachable. That was correct
behaviour, and it is why the page was of no practical use.

Now a runtime runs on this machine as a user service, bound to loopback, serving
both the Studio and its API under the path `/citxr`. It is published through the
tunnel that already exists: `admin.secondbrains.org` is one route to
ContentRadar's dev server, which proxies `/kakao`, `/wm`, `/studio` and now
`/citxr` to local ports. No new tunnel route was needed.

```text
browser ──► Cloudflare ──► cloudflared ──► ContentRadar vite :5174
                                             └── ^/citxr(/|$) ──► 127.0.0.1:8791
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
3. **The runtime closes its own join.** That host has no edge authentication --
   every app behind it defends itself -- so `CITXR_JOIN_PASSCODE` is set and no
   token exists until somebody presents a passcode (ADR-033). A student presents
   the classroom passcode; an instructor presents the instructor passcode, which
   the classroom passcode never substitutes for.

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
- Both passcodes in `/home/sb/.config/citxr/hosted.env`, mode 0600, read by the
  unit as `CITXR_INSTRUCTOR_PASSCODE` and `CITXR_JOIN_PASSCODE`. They survive a
  restart, which a random per-run passcode does not.
- Rebuilding the Studio (`pnpm build`) is live: the runtime serves the `dist`
  directory from disk.

Rotate either passcode:

```bash
python3 - <<'EOF' > /home/sb/.config/citxr/hosted.env
import secrets
print(f"CITXR_INSTRUCTOR_PASSCODE={secrets.token_urlsafe(18)}")
print(f"CITXR_JOIN_PASSCODE={secrets.token_urlsafe(12)}")
EOF
chmod 600 /home/sb/.config/citxr/hosted.env
systemctl --user restart citxr-runtime.service
```

The proxy rule lives in ContentRadar's `frontend/vite.proxy.ts` (`^/citxr(/|$)`,
`ws: true`, no rewrite -- the runtime already serves under the prefix). Vite reads
it at startup, so a change there needs
`systemctl --user restart contentradar-frontend.service`. While the runtime is
down the path returns a proxy error rather than the old static page; the unit is
`Restart=always`.

## The Cloudflare half — optional now, still worth doing

`cloudflared` here runs from `/etc/cloudflared/token`, so its routes live in the
Cloudflare dashboard and cannot be edited from this machine.

Nothing here is required for the deployment to work; it works now. What it adds
is a second lock in front of the first. The path is reachable anonymously —
`https://admin.secondbrains.org/citxr/api/health` answers 200 to anyone — and
what stops a stranger going further is the runtime's own join passcode.

**1. Access application (Zero Trust → Access → Applications → Add → Self-hosted):**

| Field       | Value                               |
| ----------- | ----------------------------------- |
| Application | `admin.secondbrains.org/citxr`      |
| Policy      | Allow · Emails · `jc@citcoding.com` |

**2.** No tunnel route to add. `admin.secondbrains.org` already resolves to
ContentRadar's dev server, and the proxy rule there sends `/citxr` on. That is
also why the runtime is served under a prefix: the proxy forwards the path as it
arrived.

WebSockets are already enabled for this tunnel's traffic in the sense that
Cloudflare proxies them by default; the event stream is `wss://…/citxr/ws/events`
and needs no separate rule.

**3. Check it:**

```bash
curl -sI https://admin.secondbrains.org/citxr/api/health   # 302 to the Access login, not 200
```

Until an Access policy exists this answers `200` with the runtime's health JSON,
which is the current state and is safe by the paragraph above: health is public
on purpose, and every other route is `401` without a token.

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

And through the tunnel, at `https://admin.secondbrains.org/citxr/index.html`,
after the join passcode was turned on:

```text
sign-in asks a student for the classroom passcode   true
wrong passcode                     "This classroom needs a passcode to join."
signed in with the passcode        true
drive outcome                      Accepted · completed
event stream                       wss://admin.secondbrains.org/citxr/ws/events
anonymous /citxr/api/devices       401
anonymous /citxr/api/classroom     401
anonymous /citxr/api/audit/export  401
anonymous POST /citxr/api/safety/stop  401
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

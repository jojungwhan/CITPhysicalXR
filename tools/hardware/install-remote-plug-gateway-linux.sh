#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --site-id ID --site-name NAME --tailscale-host HOST [--room-id ID] [--bluetooth-adapter N | --disable-bluetooth] [--network-interface NAME] [--state-root ABSOLUTE_PATH]" >&2
  exit 2
}

site_id=""
site_name=""
tailscale_host=""
room_id="plug-room"
bluetooth_adapter="0"
bluetooth_enabled="true"
network_interface=""
state_root="${HOME}/.local/share/cit-physical-xr-gateway"

while (($#)); do
  case "$1" in
    --site-id) site_id="${2:-}"; shift 2 ;;
    --site-name) site_name="${2:-}"; shift 2 ;;
    --tailscale-host) tailscale_host="${2:-}"; shift 2 ;;
    --room-id) room_id="${2:-}"; shift 2 ;;
    --bluetooth-adapter) bluetooth_adapter="${2:-}"; shift 2 ;;
    --disable-bluetooth) bluetooth_enabled="false"; shift ;;
    --network-interface) network_interface="${2:-}"; shift 2 ;;
    --state-root) state_root="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

identifier_pattern='^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
tailscale_pattern='^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+ts\.net$'
[[ "$site_id" =~ $identifier_pattern ]] || usage
[[ "$room_id" =~ $identifier_pattern ]] || usage
[[ "$tailscale_host" =~ $tailscale_pattern ]] || usage
(( ${#tailscale_host} <= 253 )) || usage
[[ "$bluetooth_adapter" =~ ^[0-9]+$ ]] || usage
[[ "$state_root" = /* ]] || usage
if [[ "$state_root" =~ [[:cntrl:]] || "$state_root" == *'"'* || "$state_root" == *'\'* ]]; then
  usage
fi
if [[ -z "$site_name" || ${#site_name} -gt 80 || "$site_name" =~ [[:cntrl:]] || "$site_name" == *'"'* || "$site_name" == *'\'* ]]; then
  usage
fi
if [[ -n "$network_interface" && ! "$network_interface" =~ ^[A-Za-z0-9._:-]{1,64}$ ]]; then
  usage
fi

for command_name in python3 node tailscale systemctl; do
  command -v "$command_name" >/dev/null || {
    echo "Required command is missing: $command_name" >&2
    exit 1
  }
done

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd -- "${script_directory}/../.." && pwd -P)"
runtime_python="${repository_root}/.venv/bin/python"
matter_entry="${repository_root}/apps/matter-controller/node_modules/matter-server/dist/esm/MatterServer.js"
companion_apk="${repository_root}/apps/control-tower-companion/app/build/outputs/apk/debug/app-debug.apk"
studio_directory="${repository_root}/apps/studio-web/dist"
[[ -x "$runtime_python" ]] || {
  echo "Run 'uv sync --frozen' in ${repository_root} first." >&2
  exit 1
}
[[ -f "$matter_entry" ]] || {
  echo "Run 'pnpm install --frozen-lockfile' in ${repository_root} first." >&2
  exit 1
}
[[ -f "$companion_apk" ]] || {
  echo "Build and copy the Control Tower Companion APK before installing." >&2
  exit 1
}
[[ -f "${studio_directory}/index.html" ]] || {
  echo "Run 'pnpm build' in ${repository_root} before installing." >&2
  exit 1
}
tailscale status >/dev/null || {
  echo "Enroll this Linux gateway in your tailnet before installing the service." >&2
  exit 1
}

config_root="${HOME}/.config/citxr"
unit_root="${HOME}/.config/systemd/user"
runtime_environment="${config_root}/remote-plug-runtime.env"
gateway_environment="${config_root}/remote-plug-adapter.env"
matter_environment="${config_root}/remote-plug-matter.env"
mkdir -p -- "$config_root" "$unit_root" "$state_root" "${state_root}/matter/controller" "${state_root}/matter/active"
chmod 700 -- "$config_root" "$state_root" "${state_root}/matter" "${state_root}/matter/controller" "${state_root}/matter/active"
umask 077

administrator_token="$(python3 -c 'import secrets; print("cit-admin-" + secrets.token_urlsafe(32))')"
adapter_token="$(python3 -c 'import secrets; print("cit-matter-" + secrets.token_urlsafe(32))')"

{
  printf 'CITXR_DATA_DIRECTORY="%s"\n' "${state_root}/runtime"
  printf 'CITXR_PUBLIC_ORIGIN="http://127.0.0.1:8766"\n'
  printf 'CITXR_ALLOWED_HOSTS="127.0.0.1,localhost,%s"\n' "$tailscale_host"
  printf 'CITXR_FABRIC_BOOTSTRAP_TOKEN="%s"\n' "$administrator_token"
  printf 'CITXR_MATTER_ADAPTER_TOKEN="%s"\n' "$adapter_token"
  printf 'CITXR_ALLOW_PHYSICAL_FABRIC="true"\n'
  printf 'CITXR_LAN_MAC_ACCESS="false"\n'
  printf 'CITXR_REMOTE_PLUG_ORIGIN="https://%s"\n' "$tailscale_host"
  printf 'CITXR_REMOTE_SITE_ID="%s"\n' "$site_id"
  printf 'CITXR_REMOTE_SITE_NAME="%s"\n' "$site_name"
  printf 'CITXR_MATTER_ROOM_ID="%s"\n' "$room_id"
  printf 'CITXR_UNLOCK_COMPANION_APK="%s"\n' "$companion_apk"
  printf 'CITXR_STUDIO_DIRECTORY="%s"\n' "$studio_directory"
} >"$runtime_environment"

{
  printf 'CITXR_MATTER_ADAPTER_TOKEN="%s"\n' "$adapter_token"
  printf 'CIT_MATTER_SITE_ID="%s"\n' "$site_id"
  printf 'CIT_MATTER_ROOM_ID="%s"\n' "$room_id"
  printf 'CIT_MATTER_HOST_ID="%s"\n' "$site_id"
  printf 'CIT_MATTER_ACTIVATION_ROOT="%s"\n' "${state_root}/matter/active"
  printf 'CIT_MATTER_ADAPTER_URL="ws://127.0.0.1:8766/api/v1/adapters/connect"\n'
  printf 'CIT_MATTER_SERVER_URL="ws://127.0.0.1:5580/ws"\n'
} >"$gateway_environment"

{
  printf 'STORAGE_PATH="%s"\n' "${state_root}/matter/controller"
  printf 'PORT="5580"\n'
  printf 'LISTEN_ADDRESS="127.0.0.1"\n'
  printf 'DEFAULT_FABRIC_LABEL="CIT-%s"\n' "$site_id"
  # Use BlueZ through the system D-Bus. The noble Linux default opens a raw
  # HCI socket, which is incompatible with this intentionally unprivileged
  # user service and its NoNewPrivileges hardening.
  if [[ "$bluetooth_enabled" == "true" ]]; then
    printf 'NOBLE_BINDINGS="dbus"\n'
    printf 'BLUETOOTH_ADAPTER="%s"\n' "$bluetooth_adapter"
  fi
  printf 'DISABLE_OTA="true"\n'
  printf 'DISABLE_DASHBOARD="true"\n'
  printf 'DISABLE_THREAD_DIAGNOSTICS="true"\n'
  printf 'LOG_LEVEL="warning"\n'
  if [[ -n "$network_interface" ]]; then
    printf 'PRIMARY_INTERFACE="%s"\n' "$network_interface"
  fi
} >"$matter_environment"
chmod 600 -- "$runtime_environment" "$gateway_environment" "$matter_environment"
unset administrator_token adapter_token

cat >"${unit_root}/citxr-remote-plug-runtime.service" <<EOF
[Unit]
Description=CIT remote smart-plug runtime
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${repository_root}
EnvironmentFile=${runtime_environment}
UMask=0077
ExecStart="${runtime_python}" -m uvicorn cit_runtime.fabric_service:create_persistent_fabric_app --factory --host 127.0.0.1 --port 8766
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

cat >"${unit_root}/citxr-matter-controller.service" <<EOF
[Unit]
Description=CIT loopback Matter controller
After=network-online.target bluetooth.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${repository_root}/apps/matter-controller
EnvironmentFile=${matter_environment}
UMask=0077
ExecStart="$(command -v node)" "${matter_entry}"
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

cat >"${unit_root}/citxr-matter-gateway.service" <<EOF
[Unit]
Description=CIT supervised Matter smart-plug adapters
After=citxr-remote-plug-runtime.service citxr-matter-controller.service
Requires=citxr-remote-plug-runtime.service citxr-matter-controller.service

[Service]
Type=simple
WorkingDirectory=${repository_root}
EnvironmentFile=${gateway_environment}
UMask=0077
ExecStart="${runtime_python}" -m cit_matter_smart_plug.gateway
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
KillMode=mixed
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
gateway_enabled="false"
if systemctl --user is-enabled --quiet citxr-matter-gateway.service; then
  gateway_enabled="true"
fi
systemctl --user enable citxr-remote-plug-runtime.service citxr-matter-controller.service
systemctl --user restart citxr-remote-plug-runtime.service citxr-matter-controller.service
if [[ "$gateway_enabled" == "true" ]]; then
  systemctl --user restart citxr-matter-gateway.service
fi

# Serve strips the mounted prefix before proxying, so repeat that prefix on the
# loopback target. This publishes only the remote-plug subtree; never use Funnel.
tailscale serve --bg --https=443 --set-path=/api/v1/fabric/remote-plugs/ \
  http://127.0.0.1:8766/api/v1/fabric/remote-plugs/

echo "Installed the ${site_name} gateway at https://${tailscale_host}."
echo "Open the private local console with:"
echo "  ${runtime_python} -m cit_runtime.fabric_local_console"
echo "Commission at least one plug, then run:"
echo "  systemctl --user enable --now citxr-matter-gateway.service"
echo "For unattended boot, an administrator must run: sudo loginctl enable-linger ${USER}"
echo "The generated administrator and adapter credentials remain only in ${config_root}."

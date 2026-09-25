#Requires -Version 7.4

[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [ValidatePattern('^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$')]
  [string]$SshTarget,
  [Parameter(Mandatory)]
  [string]$IdentityFile,
  [Parameter(Mandatory)]
  [ValidatePattern('^/[A-Za-z0-9._/-]+$')]
  [string]$GatewayRepository,
  [string]$DisplayName = "$env:COMPUTERNAME Control Tower",
  [string]$StateRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (-not $IsWindows) { throw "Gateway pairing uses this Windows user's DPAPI protection." }
if (-not $StateRoot) { $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric" }
$secretRoot = Join-Path ([IO.Path]::GetFullPath($StateRoot)) "secrets"
$secretPath = Join-Path $secretRoot "plug-gateways.dpapi"
$identityPath = (Resolve-Path -LiteralPath $IdentityFile -ErrorAction Stop).Path
$existing = @()
if (Test-Path -LiteralPath $secretPath -PathType Leaf) {
  $secure = ConvertTo-SecureString ([IO.File]::ReadAllText($secretPath))
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $existing = @([Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) | ConvertFrom-Json)
  } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
if ($existing.Count -ge 8) { throw "At most eight gateways can be paired." }
$encodedName = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($DisplayName))
$knownPairings = @($existing | Select-Object siteId, origin, deviceId)
$encodedKnown = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $knownPairings -Compress)))
$pairingScript = @"
import base64, json, sys, urllib.request
from pathlib import Path
from cit_runtime.fabric_local_console import _read_bootstrap_token
token = _read_bootstrap_token(Path.home() / '.config/citxr/remote-plug-runtime.env')
name = base64.b64decode('$encodedName').decode('utf-8')
known = json.loads(base64.b64decode('$encodedKnown'))
headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
request = urllib.request.Request('http://127.0.0.1:8766/api/v1/fabric/unlock-automation', headers=headers)
with urllib.request.urlopen(request, timeout=10) as response:
    snapshot = json.load(response)
remote = snapshot.get('remoteAccess') or {}
paired = {item['deviceId'] for item in snapshot.get('companions', [])}
request = urllib.request.Request('http://127.0.0.1:8766/api/v1/fabric/nodes', headers=headers)
with urllib.request.urlopen(request, timeout=10) as response:
    nodes = {item['nodeId']: item for item in json.load(response)}
known_plugs = [{'nodeId': node_id, 'displayName': nodes.get(node_id, {}).get('displayName', node_id)} for node_id in snapshot.get('selectedNodeIds', [])]
if any(item['siteId'] == remote.get('siteId') and item['origin'] == remote.get('origin') and item['deviceId'] in paired for item in known):
    print(json.dumps({'alreadyPaired': True, 'siteId': remote['siteId'], 'knownPlugs': known_plugs}))
    sys.exit(0)
request = urllib.request.Request('http://127.0.0.1:8766/api/v1/fabric/unlock-automation/desktop-pairings',
    data=json.dumps({'displayName': name}).encode(),
    headers=headers)
with urllib.request.urlopen(request, timeout=10) as response:
    configuration = json.load(response)
    configuration['knownPlugs'] = known_plugs
    print(json.dumps(configuration))
"@
# Only the one-time pairing response crosses SSH; the administrator secret stays on the gateway.
$raw = $pairingScript | & ssh -i $identityPath -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 $SshTarget "$GatewayRepository/.venv/bin/python -"
if ($LASTEXITCODE -ne 0) { throw "Gateway pairing failed. Existing local pairings were preserved." }
$configuration = ($raw | Out-String) | ConvertFrom-Json
if ($configuration.PSObject.Properties.Name -contains 'alreadyPaired') {
  Write-Host "This Windows Control Tower is already paired with $($configuration.siteId)."
  $current = $existing | Where-Object { $_.siteId -eq $configuration.siteId } | Select-Object -First 1
  $current | Add-Member -NotePropertyName knownPlugs -NotePropertyValue $configuration.knownPlugs -Force
  $configuration = $current
}
if (-not $configuration.secret -or $configuration.deviceId -notmatch '^desktop-[a-f0-9]{16}$') {
  throw "The gateway did not return a valid desktop pairing."
}
$configurations = @($existing | Where-Object { $_.siteId -ne $configuration.siteId }) + @($configuration)
$document = ConvertTo-Json -InputObject $configurations -Compress -Depth 5
$protected = ConvertFrom-SecureString (ConvertTo-SecureString $document -AsPlainText -Force)
New-Item -ItemType Directory -Path $secretRoot -Force | Out-Null
$temporaryPath = Join-Path $secretRoot ("plug-gateways-" + [Guid]::NewGuid().ToString('N') + ".tmp")
[IO.File]::WriteAllText($temporaryPath, $protected, [Text.UTF8Encoding]::new($false))
[IO.File]::Move($temporaryPath, $secretPath, $true)
Write-Host "Paired $($configuration.displayName) with this Windows Control Tower. Restart Control Tower to load the gateway."

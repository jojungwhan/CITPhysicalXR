#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Preflight", "ConfigureStart", "Start", "Status", "Stop")]
  [string]$Mode = "Start",
  [string]$StateRoot = "",
  [string]$SharedFabricRoot = "",
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8766,
  [string]$SiteId = "cit-local",
  [string]$RoomId = "classroom-a",
  [string]$HostId = "",
  [string]$HubName = "",
  [ValidateSet("", "spike-prime", "spike-essential", "robot-inventor")]
  [string]$HubModel = "",
  [string]$PortsJson = "",
  [switch]$Simulation,
  [switch]$SkipBuild,
  [switch]$NoOpenConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $StateRoot) { $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\lego-pybricks" }
if (-not $SharedFabricRoot) { $SharedFabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric" }
if (-not $HostId) { $HostId = "$($env:COMPUTERNAME.ToLowerInvariant())-lego" }
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$SharedFabricRoot = [IO.Path]::GetFullPath($SharedFabricRoot)
$runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$fabricOrigin = "http://127.0.0.1:$FabricPort"
$adapterUrl = "ws://127.0.0.1:$FabricPort/api/v1/adapters/connect"
$bootstrapSecretPath = Join-Path $SharedFabricRoot "secrets\fabric-bootstrap.dpapi"
$profilePath = Join-Path $StateRoot "profile.json"
$statePath = Join-Path $StateRoot "state.json"
$secretPath = Join-Path $StateRoot "secrets\adapter.dpapi"
$logRoot = Join-Path $StateRoot "logs"
$activationPath = Join-Path $StateRoot "monitoring-active.signal"

function Assert-Path([string]$Path, [string]$Description) {
  if (-not (Test-Path -LiteralPath $Path)) { throw "$Description was not found at $Path" }
}

function Read-ProtectedSecret([string]$Path) {
  Assert-Path $Path "Protected credential"
  $ciphertext = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8).Trim()
  $secure = ConvertTo-SecureString -String $ciphertext
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Save-ProtectedSecret([string]$Path, [string]$Value) {
  $secure = ConvertTo-SecureString -String $Value -AsPlainText -Force
  $ciphertext = ConvertFrom-SecureString -SecureString $secure
  [IO.File]::WriteAllText($Path, $ciphertext, [Text.UTF8Encoding]::new($false))
}

function Invoke-JsonApi(
  [ValidateSet("GET", "POST", "PUT")][string]$Method,
  [string]$Uri,
  [string]$Credential,
  [object]$Body = $null
) {
  $parameters = @{
    Method = $Method; Uri = $Uri
    Headers = @{ Authorization = "Bearer $Credential" }
    TimeoutSec = 15
  }
  if ($null -ne $Body) {
    $parameters.ContentType = "application/json"
    $parameters.Body = $Body | ConvertTo-Json -Depth 12 -Compress
  }
  return Invoke-RestMethod @parameters
}

function Load-JsonFile([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @{} }
  return [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) |
    ConvertFrom-Json -AsHashtable
}

function Save-JsonFile([string]$Path, [hashtable]$Value) {
  New-Item -ItemType Directory -Path (Split-Path $Path -Parent) -Force | Out-Null
  [IO.File]::WriteAllText(
    $Path,
    ($Value | ConvertTo-Json -Depth 10),
    [Text.UTF8Encoding]::new($false)
  )
}

function Expand-Sequence([object]$Value) {
  if ($null -eq $Value) { return }
  if (
    $Value -is [Collections.IEnumerable] -and
    $Value -isnot [string] -and
    $Value -isnot [Collections.IDictionary]
  ) {
    foreach ($item in $Value) { Write-Output $item }
    return
  }
  Write-Output $Value
}

function Get-ProcessCommandLine([int]$ProcessId) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
  if ($null -eq $process) { return $null }
  return [string]$process.CommandLine
}

function Stop-ExactProcess([object]$ProcessId) {
  if ($null -eq $ProcessId) { return }
  $numericId = [int]$ProcessId
  $commandLine = Get-ProcessCommandLine $numericId
  if ($null -eq $commandLine) { return }
  if (-not $commandLine.Contains("cit_lego_pybricks.fabric_main", [StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Ignoring stale PID $numericId because it is not the LEGO Fabric adapter"
    return
  }
  Stop-Process -Id $numericId
  Wait-Process -Id $numericId -Timeout 15 -ErrorAction SilentlyContinue
}

function Wait-Until([scriptblock]$Condition, [string]$FailureMessage, [int]$TimeoutSeconds = 45) {
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    if (& $Condition) { return }
    Start-Sleep -Milliseconds 250
  } while ([DateTimeOffset]::UtcNow -lt $deadline)
  throw $FailureMessage
}

function ConvertTo-StartProcessArgument([string]$Value) {
  # Start-Process joins ArgumentList entries into one Windows command line. Keep
  # each already-validated value intact when it contains whitespace.
  if ($Value.Contains('"')) {
    throw "LEGO process arguments cannot contain a quote character"
  }
  if (-not $Value -or $Value -match '\s') { return '"' + $Value + '"' }
  return $Value
}

function Read-InputProfile {
  if ($Mode -ne "ConfigureStart") { return @{} }
  $raw = [Console]::In.ReadToEnd()
  if (-not $raw -or [Text.Encoding]::UTF8.GetByteCount($raw) -gt 8192) {
    throw "LEGO setup must be a bounded JSON document"
  }
  return $raw | ConvertFrom-Json -AsHashtable
}

function Resolve-Profile {
  $profile = if ($Mode -eq "ConfigureStart") { Read-InputProfile } else { Load-JsonFile $profilePath }
  if ($HubName) { $profile.hubName = $HubName }
  if ($HubModel) { $profile.hubModel = $HubModel }
  if ($PortsJson) { $profile.ports = $PortsJson | ConvertFrom-Json -AsHashtable }
  if (-not $profile.ContainsKey("hubName") -or [string]$profile.hubName -notmatch '^[\p{L}\p{N}][\p{L}\p{N} ._-]{0,79}$') {
    throw "Enter the exact 1-80 character advertised LEGO hub name"
  }
  if (-not $profile.ContainsKey("hubModel") -or [string]$profile.hubModel -notin @("spike-prime", "spike-essential", "robot-inventor")) {
    throw "Choose a supported LEGO hub model"
  }
  if (-not $profile.ContainsKey("ports") -or $profile.ports -isnot [Collections.IDictionary]) {
    throw "LEGO setup requires a port map"
  }
  $allowedPorts = if ([string]$profile.hubModel -eq "spike-essential") { @("A", "B") } else { @("A", "B", "C", "D", "E", "F") }
  $allowedKinds = @("empty", "motor", "distance", "color", "force")
  $normalizedPorts = [ordered]@{}
  foreach ($entry in $profile.ports.GetEnumerator()) {
    $port = ([string]$entry.Key).ToUpperInvariant()
    $kind = ([string]$entry.Value).ToLowerInvariant()
    if ($port -notin $allowedPorts -or $kind -notin $allowedKinds) {
      throw "LEGO port map contains an unsupported port or device kind"
    }
    $normalizedPorts[$port] = $kind
  }
  if (@($normalizedPorts.Values | Where-Object { $_ -ne "empty" }).Count -lt 1) {
    throw "LEGO monitoring requires at least one configured sensor or motor port"
  }
  return @{
    schemaVersion = "1.0"
    hubName = [string]$profile.hubName
    hubModel = [string]$profile.hubModel
    ports = $normalizedPorts
  }
}

function Stop-Lego([hashtable]$State, [string]$Bootstrap) {
  if (Test-Path -LiteralPath $activationPath) { [IO.File]::Delete($activationPath) }
  # The monitoring session is shared with Brain and future independent sensor
  # adapters. This component owns only its adapter process and activation file.
  $null = $Bootstrap
  Start-Sleep -Milliseconds 900
  Stop-ExactProcess $(if ($State.ContainsKey("adapterPid")) { $State.adapterPid } else { $null })
  if ($State.Count -gt 0) {
    $State.stoppedAt = [DateTimeOffset]::UtcNow.ToString("o")
    Save-JsonFile $statePath $State
  }
}

$state = Load-JsonFile $statePath
$bootstrap = if (Test-Path -LiteralPath $bootstrapSecretPath) { Read-ProtectedSecret $bootstrapSecretPath } else { "" }
if ($Mode -eq "Stop") { Stop-Lego $state $bootstrap; exit 0 }
if ($Mode -eq "Status") {
  Write-Host "Profile: $(if (Test-Path -LiteralPath $profilePath) { $profilePath } else { 'not configured' })"
  Write-Host "Adapter PID: $(if ($state.ContainsKey('adapterPid')) { $state.adapterPid } else { 'not started' })"
  Write-Host "Session: $(if ($state.ContainsKey('sessionId')) { $state.sessionId } else { 'not started' })"
  Write-Host "Logs: $logRoot"
  exit 0
}

Assert-Path $runtimePython "CIT runtime Python"
Assert-Path $bootstrapSecretPath "Shared Fabric credential; open Classroom Control first"
$health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 5
if (-not $Simulation -and $health.physicalActuation -ne "enabled") {
  throw "Enable classroom devices in the CIT button before connecting a real LEGO hub"
}
if (-not $Simulation) {
  & $runtimePython -c "import pybricksdev" 2>$null
  if ($LASTEXITCODE -ne 0) {
    throw "The optional Pybricks Bluetooth transport is missing; rerun the CIT business installer"
  }
}
$profile = Resolve-Profile
if ($Mode -eq "Preflight") {
  Write-Host "PASS exact-name LEGO profile is valid for $($profile.hubModel)"
  Write-Host "PASS connection starts in an unarmed monitoring session"
  exit 0
}
if ($Mode -eq "ConfigureStart") { Save-JsonFile $profilePath $profile }
if (-not $SkipBuild) {
  & uv sync --all-packages --directory $repositoryRoot
  if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
}

Stop-Lego $state $bootstrap
New-Item -ItemType Directory -Path $StateRoot, (Split-Path $secretPath -Parent), $logRoot -Force | Out-Null
$hash = [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes([string]$profile.hubName))
$suffix = ([Convert]::ToHexString($hash)).Substring(0, 12).ToLowerInvariant()
$nodeId = "lego-$suffix"
$sessionMode = if ($Simulation) { "simulation" } else { "physical" }
$session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/monitoring/session" -Credential $bootstrap -Body @{
  siteId = $SiteId; roomId = $RoomId; mode = $sessionMode
}
$existingRole = @(
  Expand-Sequence $session.roleBindings |
    Where-Object { $_.nodeId -eq $nodeId -and $_.role -like "robot_sensor_*" } |
    Select-Object -First 1
)
$occupiedRoles = @(
  Expand-Sequence $session.roleBindings |
    Where-Object { $_.role -like "robot_sensor_*" } |
    ForEach-Object role
)
$sensorRole = if ($existingRole.Count -gt 0) {
  [string]$existingRole[0].role
} else {
  @(1..8 | ForEach-Object { "robot_sensor_$_" } | Where-Object { $_ -notin $occupiedRoles } | Select-Object -First 1)[0]
}
if (-not $sensorRole) { throw "The shared monitoring session already has eight LEGO sensor roles" }
$identity = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/auth/identities" -Credential $bootstrap -Body @{
  identityId = "cit-lego-$suffix-$(([string]$session.sessionId).Substring(0, 8))"
  actorType = "adapter"; roles = @("plugin.cit.lego-pybricks")
  permissions = @("fabric.adapters.connect", "fabric.events.publish", "fabric.nodes.write")
  siteId = $SiteId; roomId = $RoomId; sessionId = [string]$session.sessionId; ttlSeconds = 86400
}
Save-ProtectedSecret $secretPath ([string]$identity.token)
$arguments = @(
  "-m", "cit_lego_pybricks.fabric_main",
  "--adapter-url", $adapterUrl,
  "--fabric-origin", $fabricOrigin,
  "--session-id", [string]$session.sessionId,
  "--site-id", $SiteId,
  "--room-id", $RoomId,
  "--host-id", $HostId,
  "--node-id", $nodeId,
  "--display-name", [string]$profile.hubName,
  "--activation-file", $activationPath,
  "--mode", $(if ($Simulation) { "simulation" } else { "pybricks-ble" }),
  "--hub-name", [string]$profile.hubName,
  "--hub-model", [string]$profile.hubModel,
  "--ports-base64", [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes(($profile.ports | ConvertTo-Json -Compress))
  )
)
$processArguments = @($arguments | ForEach-Object { ConvertTo-StartProcessArgument ([string]$_) })
$process = Start-Process `
  -FilePath $runtimePython `
  -ArgumentList $processArguments `
  -WorkingDirectory $repositoryRoot `
  -WindowStyle Hidden `
  -Environment @{ CIT_FABRIC_ADAPTER_TOKEN = [string]$identity.token } `
  -RedirectStandardOutput (Join-Path $logRoot "adapter.stdout.log") `
  -RedirectStandardError (Join-Path $logRoot "adapter.stderr.log") `
  -PassThru
$state = @{
  adapterPid = $process.Id; sessionId = [string]$session.sessionId
  nodeId = $nodeId; hubName = [string]$profile.hubName
  startedAt = [DateTimeOffset]::UtcNow.ToString("o")
}
Save-JsonFile $statePath $state
try {
  Wait-Until {
    $nodes = @(Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential $bootstrap)
    return @($nodes | Where-Object { $_.nodeId -eq $nodeId -and $_.connectionState -eq "connected" }).Count -eq 1
  } "The LEGO adapter did not connect; inspect $logRoot"
  $null = Invoke-JsonApi -Method PUT -Uri "$fabricOrigin/api/v1/fabric/sessions/$($state.sessionId)/roles/$sensorRole" -Credential $bootstrap -Body @{ nodeId = $nodeId }
  if ([string]$session.state -ne "active") {
    $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$($state.sessionId)/start" -Credential $bootstrap
  }
  [IO.File]::WriteAllText($activationPath, "active`n", [Text.Encoding]::ASCII)
} catch {
  Stop-Lego $state $bootstrap
  throw
}

Write-Host "READY LEGO hub '$($profile.hubName)' is connected for unarmed sensor monitoring."
Write-Host "Motor movement remains unavailable until a tutor assigns this node to an armed ground-robot lesson."
if (-not $NoOpenConsole) {
  & (Join-Path $PSScriptRoot "interaction-fabric-console.ps1") -Mode Open -FabricPort $FabricPort -StateRoot $SharedFabricRoot
}

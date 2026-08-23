#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Preflight", "Start", "Status", "Stop")]
  [string]$Mode = "Start",
  [ValidateSet("All", "Tello", "MindWave", "Demo", "Fleet")]
  [string]$Device = "All",
  [string]$Brain2DevicesRoot = "",
  [string]$ExternalPython = "",
  [string]$StateRoot = "",
  [string]$SharedFabricRoot = "",
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8766,
  [string]$SiteId = "cit-local",
  [string]$RoomId = "classroom-a",
  [string]$HostId = "",
  [string]$TelloNodeId = "tello-01",
  [string]$MindWaveNodeId = "mindwave-mobile2-01",
  [string]$BrainDemoNodeId = "brain2devices-demo-01",
  [string]$FleetNodeId = "brain2devices-fleet-01",
  [string]$TelloIpAddress = "",
  [switch]$Simulation,
  [switch]$CompatibilityApi,
  [switch]$SkipBuild,
  [switch]$NoOpenConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$sourceCatalogPath = Join-Path $PSScriptRoot "external-sources.generated.json"
if (-not (Test-Path -LiteralPath $sourceCatalogPath -PathType Leaf)) {
  throw "Generated external-source catalog is missing; run pnpm generate"
}
$sourceCatalog = [IO.File]::ReadAllText($sourceCatalogPath, [Text.Encoding]::UTF8) |
  ConvertFrom-Json
$expectedRevision = [string]$sourceCatalog.sources.brain2devices.revision
$workspaceRoot = Split-Path $repositoryRoot -Parent
if (-not $Brain2DevicesRoot) { $Brain2DevicesRoot = Join-Path $workspaceRoot "brain2devices" }
if (-not $ExternalPython) { $ExternalPython = Join-Path $Brain2DevicesRoot ".venv\Scripts\python.exe" }
if (-not $StateRoot) { $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\brain2devices-fabric" }
if (-not $SharedFabricRoot) { $SharedFabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric" }
if (-not $HostId) { $HostId = "$($env:COMPUTERNAME.ToLowerInvariant())-brain-devices" }
if ($Simulation -and $CompatibilityApi) { throw "Simulation and CompatibilityApi are mutually exclusive" }

$Brain2DevicesRoot = [IO.Path]::GetFullPath($Brain2DevicesRoot)
$ExternalPython = [IO.Path]::GetFullPath($ExternalPython)
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$SharedFabricRoot = [IO.Path]::GetFullPath($SharedFabricRoot)
$runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$fabricOrigin = "http://127.0.0.1:$FabricPort"
$adapterUrl = "ws://127.0.0.1:$FabricPort/api/v1/adapters/connect"
$bootstrapSecretPath = Join-Path $SharedFabricRoot "secrets\fabric-bootstrap.dpapi"
$statePath = Join-Path $StateRoot "state.json"
$secretRoot = Join-Path $StateRoot "secrets"
$logRoot = Join-Path $StateRoot "logs"
$activationPath = Join-Path $StateRoot "monitoring-active.signal"

$identifierPattern = '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
foreach ($entry in @{
    SiteId = $SiteId; RoomId = $RoomId; HostId = $HostId
    TelloNodeId = $TelloNodeId; MindWaveNodeId = $MindWaveNodeId
    BrainDemoNodeId = $BrainDemoNodeId; FleetNodeId = $FleetNodeId
  }.GetEnumerator()) {
  if ($entry.Value -notmatch $identifierPattern) { throw "$($entry.Key) must be a CIT identifier" }
}

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

function Load-State {
  if (-not (Test-Path -LiteralPath $statePath)) { return @{} }
  return [IO.File]::ReadAllText($statePath, [Text.Encoding]::UTF8) | ConvertFrom-Json -AsHashtable
}

function Save-State([hashtable]$State) {
  New-Item -ItemType Directory -Path $StateRoot, $secretRoot, $logRoot -Force | Out-Null
  $State.updatedAt = [DateTimeOffset]::UtcNow.ToString("o")
  [IO.File]::WriteAllText(
    $statePath,
    ($State | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false)
  )
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

function Expand-Sequence([object]$Value) {
  if ($null -eq $Value) { return @() }
  if ($Value -is [Collections.IEnumerable] -and $Value -isnot [string] -and $Value -isnot [Collections.IDictionary]) {
    return @($Value)
  }
  return @($Value)
}

function Wait-Until([scriptblock]$Condition, [string]$FailureMessage, [int]$TimeoutSeconds = 70) {
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    if (& $Condition) { return }
    Start-Sleep -Milliseconds 250
  } while ([DateTimeOffset]::UtcNow -lt $deadline)
  throw $FailureMessage
}

function Get-ProcessCommandLine([int]$ProcessId) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
  if ($null -eq $process) { return $null }
  return [string]$process.CommandLine
}

function Stop-ExactProcess([object]$ProcessId, [string]$RequiredFragment) {
  if ($null -eq $ProcessId) { return }
  $numericId = [int]$ProcessId
  $commandLine = Get-ProcessCommandLine $numericId
  if ($null -eq $commandLine) { return }
  if (-not $commandLine.Contains($RequiredFragment, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Ignoring stale PID $numericId because it is not $RequiredFragment"
    return
  }
  Stop-Process -Id $numericId
  Wait-Process -Id $numericId -Timeout 15 -ErrorAction SilentlyContinue
}

function Show-Preflight {
  Assert-Path $runtimePython "CIT runtime Python"
  Assert-Path $bootstrapSecretPath "Shared Fabric credential; open Classroom Control first"
  if (-not $Simulation) {
    Assert-Path $ExternalPython "Brain2Devices Python"
    Assert-Path (Join-Path $Brain2DevicesRoot "src\brain2devices\hardware\protocols.py") "Brain2Devices ports"
    $revision = (& git -C $Brain2DevicesRoot rev-parse HEAD 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $revision -ne $expectedRevision) {
      throw "Brain2Devices must be the characterized revision $expectedRevision; found '$revision'"
    }
    $dirty = (& git -C $Brain2DevicesRoot status --porcelain=v1 --untracked-files=normal 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $dirty) {
      throw "Brain2Devices must be a clean checkout before physical adapters start; use a separate checkout at $expectedRevision"
    }
    if ($CompatibilityApi) {
      $null = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/state" -TimeoutSec 5
    }
  }
  $health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 5
  Write-Host "PASS Interaction Fabric is $($health.status)"
  Write-Host "PASS Tello and MindWave use separate adapter and vendor processes"
  Write-Host "PASS the optional one-shot demo uses a third bounded compatibility node"
  Write-Host "PASS Brain2Devices source revision $expectedRevision"
  Write-Host "PASS no takeoff or movement capability is advertised by the Tello adapter"
}

function New-AdapterIdentity(
  [string]$Bootstrap,
  [string]$SessionId,
  [string]$PluginId,
  [string]$IdentityPrefix
) {
  $suffix = $SessionId.Substring(0, [Math]::Min(16, $SessionId.Length))
  $permissions = @("fabric.adapters.connect", "fabric.events.publish", "fabric.nodes.write")
  if ($PluginId -eq "cit.tello") { $permissions += "fabric.media.publish" }
  return Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/auth/identities" -Credential $Bootstrap -Body @{
    identityId = "$IdentityPrefix-$suffix"
    actorType = "adapter"
    roles = @("plugin.$PluginId")
    permissions = $permissions
    siteId = $SiteId; roomId = $RoomId; sessionId = $SessionId; ttlSeconds = 86400
  }
}

function Start-AdapterProcess(
  [string]$Module,
  [string]$NodeId,
  [string]$Credential,
  [string]$SessionId,
  [string]$LogName,
  [string]$ActivationFile,
  [string]$AdapterMode,
  [string[]]$AdditionalArguments
) {
  $arguments = @(
    "-m", $Module,
    "--adapter-url", $adapterUrl,
    "--fabric-origin", $fabricOrigin,
    "--session-id", $SessionId,
    "--site-id", $SiteId,
    "--room-id", $RoomId,
    "--host-id", $HostId,
    "--node-id", $NodeId,
    "--activation-file", $ActivationFile,
    "--mode", $AdapterMode
  ) + $AdditionalArguments
  return Start-Process `
    -FilePath $runtimePython `
    -ArgumentList $arguments `
    -WorkingDirectory $repositoryRoot `
    -WindowStyle Hidden `
    -Environment @{ CIT_FABRIC_ADAPTER_TOKEN = $Credential } `
    -RedirectStandardOutput (Join-Path $logRoot "$LogName.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "$LogName.stderr.log") `
    -PassThru
}

function Stop-Adapters([hashtable]$State, [string]$Bootstrap) {
  if (Test-Path -LiteralPath $activationPath) { [IO.File]::Delete($activationPath) }
  # The monitoring session is shared with independent adapters. Stopping this
  # component must not stop LEGO or another monitoring node.
  $null = $Bootstrap
  # Give each adapter's activation watcher time to execute its safe shutdown.
  Start-Sleep -Milliseconds 1200
  # Disarm/cancel the combined one-shot gate before stopping either independent
  # sensor or safe-state aircraft projection.
  Stop-ExactProcess $(if ($State.ContainsKey("brainDemoPid")) { $State.brainDemoPid } else { $null }) "cit_brain2devices_demo"
  Stop-ExactProcess $(if ($State.ContainsKey("fleetPid")) { $State.fleetPid } else { $null }) "cit_brain2devices_demo.fleet_main"
  if ($State.ContainsKey("telloAdapters")) {
    foreach ($adapter in @($State.telloAdapters)) {
      Stop-ExactProcess $adapter.pid "cit_tello"
    }
  } else {
    Stop-ExactProcess $(if ($State.ContainsKey("telloPid")) { $State.telloPid } else { $null }) "cit_tello"
  }
  Stop-ExactProcess $(if ($State.ContainsKey("mindwavePid")) { $State.mindwavePid } else { $null }) "cit_mindwave_mobile2"
  $State.stoppedAt = [DateTimeOffset]::UtcNow.ToString("o")
  Save-State $State
}

if ($Mode -eq "Preflight") { Show-Preflight; exit 0 }

$state = Load-State
$bootstrap = if (Test-Path -LiteralPath $bootstrapSecretPath) { Read-ProtectedSecret $bootstrapSecretPath } else { "" }
if ($Mode -eq "Stop") { Stop-Adapters $state $bootstrap; exit 0 }
if ($Mode -eq "Status") {
  Write-Host "Session: $(if ($state.ContainsKey('sessionId')) { $state.sessionId } else { 'not started' })"
  Write-Host "Tello adapters: $(if ($state.ContainsKey('telloAdapters')) { @($state.telloAdapters).Count } elseif ($state.ContainsKey('telloPid')) { 1 } else { 0 })"
  Write-Host "MindWave PID: $(if ($state.ContainsKey('mindwavePid')) { $state.mindwavePid } else { 'not started' })"
  Write-Host "Bounded demo PID: $(if ($state.ContainsKey('brainDemoPid')) { $state.brainDemoPid } else { 'not started' })"
  Write-Host "Fleet sequence PID: $(if ($state.ContainsKey('fleetPid')) { $state.fleetPid } else { 'not started' })"
  Write-Host "Logs: $logRoot"
  exit 0
}

New-Item -ItemType Directory -Path $StateRoot, $secretRoot, $logRoot -Force | Out-Null
Show-Preflight
if (-not $SkipBuild) {
  & uv sync --all-packages --directory $repositoryRoot
  if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
}
if (Test-Path -LiteralPath $activationPath) { [IO.File]::Delete($activationPath) }
$existingProcessState = $state.ContainsKey("telloAdapters") -or $state.ContainsKey("telloPid") -or $state.ContainsKey("mindwavePid") -or $state.ContainsKey("brainDemoPid") -or $state.ContainsKey("fleetPid")
if ($existingProcessState) { Stop-Adapters $state $bootstrap }
$sessionMode = if ($Simulation) { "simulation" } else { "physical" }
$session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/monitoring/session" -Credential $bootstrap -Body @{
  siteId = $SiteId; roomId = $RoomId; mode = $sessionMode
}
$state.sessionId = [string]$session.sessionId
$state.siteId = $SiteId
$state.roomId = $RoomId

$expectedNodes = [Collections.Generic.List[string]]::new()
$bindings = [Collections.Generic.List[object]]::new()
$occupiedRoles = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($existingBinding in @(Expand-Sequence $session.roleBindings)) {
  $null = $occupiedRoles.Add([string]$existingBinding.role)
}
$adapterMode = if ($Simulation) { "simulation" } elseif ($CompatibilityApi) { "brain2devices-api" } else { "brain2devices" }
$telloTargets = @(@{ droneId = "primary"; nodeId = $TelloNodeId })
if ($Simulation -and $Device -in @("All", "Tello", "Fleet")) {
  $telloTargets = @(
    for ($index = 0; $index -lt 3; $index++) {
      @{
        droneId = if ($index -eq 0) { "primary" } else { "drone-$($index + 1)" }
        nodeId = if ($index -eq 0) { $TelloNodeId } else { "tello-$($index + 1)" }
      }
    }
  )
}
if ($CompatibilityApi -and $Device -in @("All", "Tello", "Fleet")) {
  $brainState = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/state" -TimeoutSec 5
  $connected = @($brainState.fleet.drones | Where-Object { $_.connection -eq "connected" } | Select-Object -First 8)
  if ($connected.Count -eq 0) { throw "Brain2Devices has no connected Tello to expose" }
  $telloTargets = @(
    for ($index = 0; $index -lt $connected.Count; $index++) {
      @{
        droneId = [string]$connected[$index].id
        nodeId = if ($index -eq 0) { $TelloNodeId } else { "tello-$($index + 1)" }
      }
    }
  )
}
if ($Device -in @("All", "Tello")) {
  $state.telloAdapters = @()
  for ($index = 0; $index -lt $telloTargets.Count; $index++) {
    $target = $telloTargets[$index]
    $identity = New-AdapterIdentity $bootstrap $state.sessionId "cit.tello" "cit-tello-$($index + 1)"
    Save-ProtectedSecret (Join-Path $secretRoot "tello-$($index + 1)-adapter.dpapi") ([string]$identity.token)
    $extra = @()
    if (-not $Simulation -and -not $CompatibilityApi) {
      $extra += @("--repository", $Brain2DevicesRoot, "--external-python", $ExternalPython)
    }
    if ($CompatibilityApi) {
      $extra += @("--brain2devices-drone-id", [string]$target.droneId)
    }
    if ($TelloIpAddress) { $extra += @("--ip-address", $TelloIpAddress) }
    $process = Start-AdapterProcess "cit_tello" ([string]$target.nodeId) ([string]$identity.token) $state.sessionId "tello-$($index + 1)-adapter" $activationPath $adapterMode $extra
    $state.telloAdapters += @{ pid = $process.Id; nodeId = [string]$target.nodeId; droneId = [string]$target.droneId }
    $expectedNodes.Add([string]$target.nodeId)
    $existingRole = @(
      Expand-Sequence $session.roleBindings |
        Where-Object { $_.nodeId -eq [string]$target.nodeId -and $_.role -like "safety_drone_*" } |
        Select-Object -First 1
    )
    $role = if ($existingRole.Count -gt 0) {
      [string]$existingRole[0].role
    } else {
      @(1..8 | ForEach-Object { "safety_drone_$_" } | Where-Object { -not $occupiedRoles.Contains($_) } | Select-Object -First 1)[0]
    }
    if (-not $role) { throw "The shared monitoring session already has eight Tello roles" }
    $null = $occupiedRoles.Add($role)
    $bindings.Add(@{ role = $role; nodeId = [string]$target.nodeId })
  }
}
if ($Device -in @("All", "MindWave")) {
  $identity = New-AdapterIdentity $bootstrap $state.sessionId "cit.mindwave-mobile2" "cit-mindwave"
  Save-ProtectedSecret (Join-Path $secretRoot "mindwave-adapter.dpapi") ([string]$identity.token)
  $extra = @()
  if (-not $Simulation -and -not $CompatibilityApi) {
    $extra += @("--repository", $Brain2DevicesRoot, "--external-python", $ExternalPython)
  }
  $process = Start-AdapterProcess "cit_mindwave_mobile2" $MindWaveNodeId ([string]$identity.token) $state.sessionId "mindwave-adapter" $activationPath $adapterMode $extra
  $state.mindwavePid = $process.Id
  $state.mindwaveNodeId = $MindWaveNodeId
  $expectedNodes.Add($MindWaveNodeId)
  $bindings.Add(@{ role = "biosignal_input"; nodeId = $MindWaveNodeId })
}
if ($Device -in @("All", "Demo")) {
  if (-not $Simulation -and -not $CompatibilityApi) {
    throw "The combined MindWave demo is available only through the characterized Brain2Devices loopback service"
  }
  $identity = New-AdapterIdentity $bootstrap $state.sessionId "cit.brain2devices-demo" "cit-brain-demo"
  Save-ProtectedSecret (Join-Path $secretRoot "brain-demo-adapter.dpapi") ([string]$identity.token)
  $demoMode = if ($Simulation) { "simulation" } else { "brain2devices-api" }
  $process = Start-AdapterProcess "cit_brain2devices_demo" $BrainDemoNodeId ([string]$identity.token) $state.sessionId "brain-demo-adapter" $activationPath $demoMode @()
  $state.brainDemoPid = $process.Id
  $state.brainDemoNodeId = $BrainDemoNodeId
  $expectedNodes.Add($BrainDemoNodeId)
  $bindings.Add(@{ role = "brain_flight_demo"; nodeId = $BrainDemoNodeId })
}
if ($Device -in @("All", "Tello", "Fleet") -and $telloTargets.Count -ge 2) {
  if (-not $Simulation -and -not $CompatibilityApi) {
    throw "The fleet sequence requires the characterized Brain2Devices loopback service"
  }
  $identity = New-AdapterIdentity $bootstrap $state.sessionId "cit.brain2devices-fleet" "cit-fleet-sequence"
  Save-ProtectedSecret (Join-Path $secretRoot "fleet-sequence-adapter.dpapi") ([string]$identity.token)
  $fleetMode = if ($Simulation) { "simulation" } else { "brain2devices-api" }
  $fleetExtra = @()
  foreach ($target in $telloTargets) {
    $fleetExtra += @("--allowed-drone-id", [string]$target.droneId)
  }
  if ($Simulation) {
    $fleetExtra += @("--simulation-drone-count", [string]$telloTargets.Count)
  }
  $process = Start-AdapterProcess "cit_brain2devices_demo.fleet_main" $FleetNodeId ([string]$identity.token) $state.sessionId "fleet-sequence-adapter" $activationPath $fleetMode $fleetExtra
  $state.fleetPid = $process.Id
  $state.fleetNodeId = $FleetNodeId
  $expectedNodes.Add($FleetNodeId)
  $bindings.Add(@{ role = "fleet_sequence_controller"; nodeId = $FleetNodeId })
} elseif ($Device -eq "Fleet") {
  throw "Connect at least two Tellos before starting the fleet sequence controller"
}
Save-State $state

try {
  Wait-Until {
    $nodes = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential $bootstrap))
    return @($nodes | Where-Object { $_.nodeId -in $expectedNodes -and $_.connectionState -eq "connected" }).Count -eq $expectedNodes.Count
  } "The selected Brain2Devices adapters did not register; inspect $logRoot"
  foreach ($binding in $bindings) {
    $null = Invoke-JsonApi -Method PUT -Uri "$fabricOrigin/api/v1/fabric/sessions/$($state.sessionId)/roles/$($binding.role)" -Credential $bootstrap -Body @{ nodeId = $binding.nodeId }
  }
  if ([string]$session.state -ne "active") {
    $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$($state.sessionId)/start" -Credential $bootstrap
  }
  [IO.File]::WriteAllText($activationPath, "active`n", [Text.Encoding]::ASCII)
} catch {
  Stop-Adapters $state $bootstrap
  throw
}

Write-Host "READY independent adapter nodes: $($expectedNodes -join ', ')"
Write-Host "Tello exposes telemetry, land, and emergency stop; takeoff/movement remain disabled."
Write-Host "MindWave publishes vendor-derived metrics only; raw EEG remains excluded."
if ($Device -in @("All", "Tello", "Fleet") -and $telloTargets.Count -ge 2) {
  Write-Host "The separate fleet controller exposes one tutor-armed ordered sequence and one stop-and-land command."
}
if ($Device -in @("All", "Demo")) {
  Write-Host "The separate demo controller exposes one explicitly confirmed one-shot arm and one stop capability."
}
if (-not $NoOpenConsole) {
  & (Join-Path $PSScriptRoot "interaction-fabric-console.ps1") -Mode Open -FabricPort $FabricPort -StateRoot $SharedFabricRoot
}

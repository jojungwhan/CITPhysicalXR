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
  [switch]$Simulation,
  [switch]$SkipBuild,
  [switch]$NoOpenConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $StateRoot) { $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\wonder-workshop" }
if (-not $SharedFabricRoot) { $SharedFabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric" }
if (-not $HostId) { $HostId = "$($env:COMPUTERNAME.ToLowerInvariant())-wonder" }
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$SharedFabricRoot = [IO.Path]::GetFullPath($SharedFabricRoot)
$runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$fabricOrigin = "http://127.0.0.1:$FabricPort"
$adapterUrl = "ws://127.0.0.1:$FabricPort/api/v1/adapters/connect"
$bootstrapSecretPath = Join-Path $SharedFabricRoot "secrets\fabric-bootstrap.dpapi"
$profilePath = Join-Path $StateRoot "profile.json"
$statePath = Join-Path $StateRoot "state.json"
$logRoot = Join-Path $StateRoot "logs"

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
  return [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json -AsHashtable
}

function Save-JsonFile([string]$Path, [object]$Value) {
  New-Item -ItemType Directory -Path (Split-Path $Path -Parent) -Force | Out-Null
  [IO.File]::WriteAllText(
    $Path,
    ($Value | ConvertTo-Json -Depth 12),
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
  if (-not $commandLine.Contains("cit_wonder_workshop.fabric_main", [StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Ignoring stale PID $numericId because it is not the Dash/Dot adapter"
    return
  }
  Stop-Process -Id $numericId
  Wait-Process -Id $numericId -Timeout 15 -ErrorAction SilentlyContinue
}

function Stop-Wonder([hashtable]$State) {
  foreach ($adapter in @(Expand-Sequence $(if ($State.ContainsKey("adapters")) { $State.adapters } else { @() }))) {
    if ($adapter.activationFile -and (Test-Path -LiteralPath $adapter.activationFile)) {
      [IO.File]::Delete([string]$adapter.activationFile)
    }
  }
  # The adapter-level Dash deadman has time to write a local stop before a
  # supervised process is terminated.
  Start-Sleep -Milliseconds 900
  foreach ($adapter in @(Expand-Sequence $(if ($State.ContainsKey("adapters")) { $State.adapters } else { @() }))) {
    Stop-ExactProcess $adapter.pid
  }
  if ($State.Count -gt 0) {
    $State.stoppedAt = [DateTimeOffset]::UtcNow.ToString("o")
    Save-JsonFile $statePath $State
  }
}

function Wait-Until([scriptblock]$Condition, [string]$FailureMessage, [int]$TimeoutSeconds = 60) {
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    if (& $Condition) { return }
    Start-Sleep -Milliseconds 250
  } while ([DateTimeOffset]::UtcNow -lt $deadline)
  throw $FailureMessage
}

function ConvertTo-StartProcessArgument([string]$Value) {
  if ($Value.Contains('"')) { throw "Dash/Dot process arguments cannot contain quotes" }
  if (-not $Value -or $Value -match '\s') { return '"' + $Value + '"' }
  return $Value
}

function Get-VisibleRobots {
  $raw = & $runtimePython -m cit_wonder_workshop.discovery --duration 6 --json
  if ($LASTEXITCODE -ne 0) { throw "Dash/Dot Bluetooth discovery failed" }
  return @($raw | ConvertFrom-Json)
}

function Resolve-Profile {
  $requested = if ($Mode -eq "ConfigureStart") {
    $raw = [Console]::In.ReadToEnd()
    if (-not $raw -or [Text.Encoding]::UTF8.GetByteCount($raw) -gt 8192) {
      throw "Dash/Dot setup must be a bounded JSON document"
    }
    $raw | ConvertFrom-Json -AsHashtable
  } else {
    Load-JsonFile $profilePath
  }
  $requestedRobots = @(Expand-Sequence $(if ($requested.ContainsKey("robots")) { $requested.robots } else { @() }))
  $candidateIds = @($requestedRobots | ForEach-Object candidateId)
  if ($candidateIds.Count -lt 1 -or $candidateIds.Count -gt 4) {
    throw "Select between one and four Dash/Dot robots"
  }
  if (@($candidateIds | Select-Object -Unique).Count -ne $candidateIds.Count) {
    throw "Select each Dash/Dot robot only once"
  }
  foreach ($robot in $requestedRobots) {
    if (
      [string]$robot.candidateId -notmatch '^wonder-[a-f0-9]{12}$' -or
      [string]$robot.model -notin @("dash", "dot")
    ) {
      throw "A selected Dash/Dot candidate ID is invalid"
    }
  }
  if ($Simulation) {
    return @{
      schemaVersion = "1.0"
      robots = @($requestedRobots | ForEach-Object {
        @{ candidateId = [string]$_.candidateId; displayName = "Simulated $($_.model)"; model = [string]$_.model }
      })
    }
  }
  $visible = @(Get-VisibleRobots)
  $robots = foreach ($candidateId in $candidateIds) {
    $matches = @($visible | Where-Object { $_.candidateId -eq [string]$candidateId })
    if ($matches.Count -ne 1) {
      throw "Selected robot $candidateId is no longer uniquely visible; scan again"
    }
    $requestedModel = [string]@($requestedRobots | Where-Object { $_.candidateId -eq $candidateId })[0].model
    if ([string]$matches[0].model -ne $requestedModel) {
      throw "Selected robot $candidateId changed model identity; scan again"
    }
    @{
      candidateId = [string]$matches[0].candidateId
      displayName = [string]$matches[0].displayName
      model = [string]$matches[0].model
    }
  }
  return @{ schemaVersion = "1.0"; robots = @($robots) }
}

$state = Load-JsonFile $statePath
if ($Mode -eq "Stop") { Stop-Wonder $state; exit 0 }
if ($Mode -eq "Status") {
  $adapters = @(Expand-Sequence $(if ($state.ContainsKey("adapters")) { $state.adapters } else { @() }))
  Write-Host "Configured profile: $(if (Test-Path -LiteralPath $profilePath) { $profilePath } else { 'none' })"
  Write-Host "Adapter processes: $($adapters.Count)"
  foreach ($adapter in $adapters) { Write-Host "  $($adapter.displayName): PID $($adapter.pid), node $($adapter.nodeId)" }
  Write-Host "Logs: $logRoot"
  exit 0
}

Assert-Path $runtimePython "CIT runtime Python"
if (-not $Simulation) {
  & $runtimePython -c "import bleak" 2>$null
  if ($LASTEXITCODE -ne 0) {
    throw "Dash/Dot Bluetooth support is missing; rerun the CIT business installer"
  }
}
if ($Mode -eq "Preflight") {
  $robots = @(
    if (-not $Simulation) { Get-VisibleRobots }
  )
  Write-Host "PASS read-only Bluetooth scan completed; $($robots.Count) Dash/Dot robot(s) visible"
  foreach ($robot in $robots) { Write-Host "  $($robot.displayName) [$($robot.model)] $($robot.candidateId)" }
  Write-Host "PASS no robot connection, light, sound, head, or drive command was sent"
  exit 0
}

Assert-Path $bootstrapSecretPath "Shared Fabric credential; open Classroom Control first"
$health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 5
if (-not $Simulation -and $health.physicalActuation -ne "enabled") {
  throw "Enable classroom devices in Classroom Control before connecting real Dash/Dot robots"
}
if (-not $SkipBuild) {
  & uv sync --package cit-wonder-workshop --extra hardware --directory $repositoryRoot --inexact
  if ($LASTEXITCODE -ne 0) { throw "Dash/Dot dependency installation failed" }
}
$profile = Resolve-Profile
if ($Mode -eq "ConfigureStart") { Save-JsonFile $profilePath $profile }

$bootstrap = Read-ProtectedSecret $bootstrapSecretPath
Stop-Wonder $state
New-Item -ItemType Directory -Path $StateRoot, $logRoot -Force | Out-Null
$sessionMode = if ($Simulation) { "simulation" } else { "physical" }
$session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/monitoring/session" -Credential $bootstrap -Body @{
  siteId = $SiteId; roomId = $RoomId; mode = $sessionMode
}
$occupiedRoles = @(
  Expand-Sequence $session.roleBindings |
    Where-Object { $_.role -like "robot_sensor_*" } |
    ForEach-Object role
)
$adapterStates = [Collections.Generic.List[object]]::new()
try {
  foreach ($robot in @(Expand-Sequence $profile.robots)) {
    $candidateId = [string]$robot.candidateId
    $suffix = $candidateId.Substring($candidateId.Length - 12)
    $nodeId = "wonder-$([string]$robot.model)-$suffix"
    $existingRole = @(
      Expand-Sequence $session.roleBindings |
        Where-Object { $_.nodeId -eq $nodeId -and $_.role -like "robot_sensor_*" } |
        Select-Object -First 1
    )
    $role = if ($existingRole.Count -gt 0) {
      [string]$existingRole[0].role
    } else {
      @(1..8 | ForEach-Object { "robot_sensor_$_" } | Where-Object { $_ -notin $occupiedRoles } | Select-Object -First 1)[0]
    }
    if (-not $role) { throw "The monitoring session has no free robot sensor role" }
    $occupiedRoles += $role
    $identity = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/auth/identities" -Credential $bootstrap -Body @{
      identityId = "cit-wonder-$suffix-$(([string]$session.sessionId).Substring(0, 8))"
      actorType = "adapter"; roles = @("plugin.cit.wonder-workshop")
      permissions = @("fabric.adapters.connect", "fabric.events.publish", "fabric.nodes.write")
      siteId = $SiteId; roomId = $RoomId; sessionId = [string]$session.sessionId; ttlSeconds = 86400
    }
    $activationFile = Join-Path $StateRoot "$nodeId-active.signal"
    $arguments = @(
      "-m", "cit_wonder_workshop.fabric_main",
      "--adapter-url", $adapterUrl,
      "--fabric-origin", $fabricOrigin,
      "--session-id", [string]$session.sessionId,
      "--site-id", $SiteId,
      "--room-id", $RoomId,
      "--host-id", $HostId,
      "--node-id", $nodeId,
      "--display-name", [string]$robot.displayName,
      "--activation-file", $activationFile,
      "--candidate-id", $candidateId,
      "--model", [string]$robot.model,
      "--mode", $(if ($Simulation) { "simulation" } else { "bleak" })
    )
    $processArguments = @($arguments | ForEach-Object { ConvertTo-StartProcessArgument ([string]$_) })
    $process = Start-Process `
      -FilePath $runtimePython `
      -ArgumentList $processArguments `
      -WorkingDirectory $repositoryRoot `
      -WindowStyle Hidden `
      -Environment @{ CIT_FABRIC_ADAPTER_TOKEN = [string]$identity.token } `
      -RedirectStandardOutput (Join-Path $logRoot "$nodeId.stdout.log") `
      -RedirectStandardError (Join-Path $logRoot "$nodeId.stderr.log") `
      -PassThru
    $adapterState = @{
      pid = $process.Id; nodeId = $nodeId; candidateId = $candidateId
      displayName = [string]$robot.displayName; model = [string]$robot.model
      role = $role; activationFile = $activationFile
    }
    $adapterStates.Add($adapterState)
    # Persist every child immediately. If the API timeout terminates this
    # launcher while a later robot is still connecting, the next Stop/Start can
    # identify and safely stop every already-spawned adapter process.
    Save-JsonFile $statePath @{
      schemaVersion = "1.0"; sessionId = [string]$session.sessionId
      phase = "starting"; adapters = @($adapterStates)
      startingAt = [DateTimeOffset]::UtcNow.ToString("o")
    }
    Wait-Until {
      $nodes = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential $bootstrap))
      return @(
        $nodes | Where-Object {
          $null -ne $_ -and
          $null -ne $_.PSObject.Properties["nodeId"] -and
          $null -ne $_.PSObject.Properties["connectionState"] -and
          $_.nodeId -eq $nodeId -and
          $_.connectionState -eq "connected"
        }
      ).Count -eq 1
    } "The $($robot.displayName) adapter did not connect; inspect $logRoot"
    $session = Invoke-JsonApi -Method PUT -Uri "$fabricOrigin/api/v1/fabric/sessions/$($session.sessionId)/roles/$role" -Credential $bootstrap -Body @{ nodeId = $nodeId }
  }
  if ([string]$session.state -ne "active") {
    $session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$($session.sessionId)/start" -Credential $bootstrap
  }
  foreach ($adapter in $adapterStates) {
    [IO.File]::WriteAllText([string]$adapter.activationFile, "active`n", [Text.Encoding]::ASCII)
  }
  $state = @{
    schemaVersion = "1.0"; sessionId = [string]$session.sessionId
    phase = "running"; adapters = @($adapterStates)
    startedAt = [DateTimeOffset]::UtcNow.ToString("o")
  }
  Save-JsonFile $statePath $state
} catch {
  Stop-Wonder @{ adapters = @($adapterStates) }
  throw
}

Write-Host "READY $($adapterStates.Count) selected Dash/Dot robot(s) connected for unarmed sensor monitoring."
Write-Host "Dash movement, head motion, and sound remain locked until a tutor arms the physical session."
if (-not $NoOpenConsole) {
  & (Join-Path $PSScriptRoot "interaction-fabric-console.ps1") -Mode Open -FabricPort $FabricPort -StateRoot $SharedFabricRoot
}

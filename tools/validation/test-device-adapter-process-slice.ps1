#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 18766,
  [string]$StateRoot = "",
  [switch]$KeepState,
  [ValidateRange(0, 180)]
  [int]$HoldSeconds = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
if (-not $StateRoot) {
  $StateRoot = Join-Path $temporaryRoot ("cit-fabric-e2e-" + [Guid]::NewGuid().ToString("N"))
}
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$stateLeaf = Split-Path $StateRoot -Leaf
if (
  -not $StateRoot.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -or
  $stateLeaf -notmatch '^cit-fabric-e2e-[0-9a-f]{32}$'
) {
  throw "StateRoot must be a dedicated cit-fabric-e2e-<32 hex> directory under $temporaryRoot"
}

$fabricRoot = Join-Path $StateRoot "fabric"
$brainRoot = Join-Path $StateRoot "brain"
$legoRoot = Join-Path $StateRoot "lego"
$fabricLauncher = Join-Path $repositoryRoot "tools\hardware\interaction-fabric-console.ps1"
$brainLauncher = Join-Path $repositoryRoot "tools\hardware\brain2devices-fabric-adapters.ps1"
$legoLauncher = Join-Path $repositoryRoot "tools\hardware\lego-pybricks.ps1"
$bootstrap = ""

function Read-ProtectedSecret([string]$Path) {
  $ciphertext = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8).Trim()
  $secure = ConvertTo-SecureString -String $ciphertext
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Invoke-AuthenticatedGet([string]$Path, [string]$Credential) {
  return Invoke-RestMethod `
    -Uri "http://127.0.0.1:$FabricPort$Path" `
    -Headers @{ Authorization = "Bearer $Credential" } `
    -TimeoutSec 10
}

function Invoke-AuthenticatedPost([string]$Path, [string]$Credential, [hashtable]$Body) {
  return Invoke-RestMethod `
    -Method POST `
    -Uri "http://127.0.0.1:$FabricPort$Path" `
    -Headers @{ Authorization = "Bearer $Credential" } `
    -ContentType "application/json" `
    -Body ($Body | ConvertTo-Json -Depth 12 -Compress) `
    -TimeoutSec 15
}

function New-CommandRequest(
  [string]$SessionId,
  [string]$TargetRole,
  [string]$Action,
  [hashtable]$Parameters,
  [int]$TtlMilliseconds
) {
  $correlation = [Guid]::NewGuid().ToString()
  return @{
    messageId = [Guid]::NewGuid().ToString()
    schemaVersion = "1.0"
    messageType = "command.requested"
    action = $Action
    target = @{ role = $TargetRole }
    sessionId = $SessionId
    parameters = $Parameters
    priority = "instructor_override"
    idempotencyKey = "process-slice:$Action`:$correlation"
    requestedAt = [DateTimeOffset]::UtcNow.ToString("o")
    ttlMs = $TtlMilliseconds
    safetyProfile = "classroom-drone-monitoring"
    correlationId = $correlation
  }
}

function Wait-ForCommandSuccess(
  [object]$Submission,
  [string]$Credential,
  [string]$Description
) {
  $commandId = [string]$Submission.lifecycle[0].commandId
  if (-not $commandId) { throw "$Description returned no command identity" }
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds(10)
  do {
    $records = @(
      Expand-Sequence (Invoke-AuthenticatedGet "/api/v1/fabric/commands/lifecycle?commandId=$commandId&limit=100" $Credential)
    )
    $terminal = @($records | Where-Object {
        $_.lifecycle.stage -in @("SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "REJECTED")
      } | Select-Object -Last 1)
    if ($terminal.Count -eq 1) {
      if ([string]$terminal[0].lifecycle.stage -ne "SUCCEEDED") {
        throw "$Description ended as $($terminal[0].lifecycle.stage): $($terminal[0].lifecycle.code) $($terminal[0].lifecycle.message)"
      }
      return
    }
    Start-Sleep -Milliseconds 100
  } while ([DateTimeOffset]::UtcNow -lt $deadline)
  throw "$Description did not reach a terminal lifecycle"
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

try {
  & $fabricLauncher `
    -Mode Start `
    -FabricPort $FabricPort `
    -StateRoot $fabricRoot `
    -SkipBuild `
    -NoOpenConsole

  & $brainLauncher `
    -Mode Start `
    -Device All `
    -Simulation `
    -FabricPort $FabricPort `
    -SharedFabricRoot $fabricRoot `
    -StateRoot $brainRoot `
    -SkipBuild `
    -NoOpenConsole

  $legoProfile = @{
    hubName = "CIT Sensor Simulation"
    hubModel = "spike-essential"
    ports = @{ A = "distance"; B = "empty" }
  } | ConvertTo-Json -Compress
  $legoProfile | & pwsh `
    -NoProfile `
    -NonInteractive `
    -File $legoLauncher `
    -Mode ConfigureStart `
    -Simulation `
    -FabricPort $FabricPort `
    -SharedFabricRoot $fabricRoot `
    -StateRoot $legoRoot `
    -SkipBuild `
    -NoOpenConsole
  if ($LASTEXITCODE -ne 0) { throw "LEGO sensor-only simulation failed to start" }

  Start-Sleep -Seconds 3
  $bootstrap = Read-ProtectedSecret (Join-Path $fabricRoot "secrets\fabric-bootstrap.dpapi")
  $nodes = @(Expand-Sequence (Invoke-AuthenticatedGet "/api/v1/fabric/nodes" $bootstrap))
  $plugins = @($nodes | ForEach-Object pluginId)
  foreach ($required in @("cit.tello", "cit.mindwave-mobile2", "cit.brain2devices-demo", "cit.brain2devices-fleet", "cit.lego-pybricks")) {
    if ($required -notin $plugins) { throw "Missing registered plugin $required" }
  }

  $tello = $nodes | Where-Object pluginId -eq "cit.tello" | Select-Object -First 1
  $telloActions = @($tello.consumedCapabilities | ForEach-Object name)
  if (
    "mobility.flight.takeoff" -in $telloActions -or
    @($telloActions | Where-Object { $_ -match 'move|velocity' }).Count -gt 0
  ) {
    throw "Unsafe Tello capability advertised"
  }
  if (
    "mobility.flight.land" -notin $telloActions -or
    "mobility.flight.emergency_stop" -notin $telloActions
  ) {
    throw "Safe Tello capabilities are missing"
  }

  $lego = $nodes | Where-Object pluginId -eq "cit.lego-pybricks" | Select-Object -First 1
  if (@($lego.consumedCapabilities).Count -ne 0) {
    throw "Sensor-only LEGO node advertised movement"
  }

  $sessions = @(
    Expand-Sequence (Invoke-AuthenticatedGet "/api/v1/fabric/sessions" $bootstrap)
  )
  $activeMonitoring = @(
    $sessions |
      Where-Object { $_.state -eq "active" -and $_.coursePackId -eq "device-monitoring" }
  )
  if ($activeMonitoring.Count -ne 1) {
    throw "Independent adapters did not converge on one active monitoring session"
  }
  $boundNodeIds = @($activeMonitoring[0].roleBindings | ForEach-Object nodeId)
  foreach ($requiredNode in @("tello-01", "tello-2", "tello-3", "mindwave-mobile2-01", "brain2devices-demo-01", "brain2devices-fleet-01", $lego.nodeId)) {
    if ($requiredNode -notin $boundNodeIds) {
      throw "Shared monitoring session is missing $requiredNode"
    }
  }

  $events = @(
    Expand-Sequence (Invoke-AuthenticatedGet "/api/v1/fabric/events?limit=100" $bootstrap)
  )
  $topics = @($events | ForEach-Object { $_.event.topic })
  if ("telemetry.flight.state" -notin $topics) { throw "Tello telemetry event is missing" }
  if (@($topics | Where-Object { $_ -like "mindwave.esense.*" }).Count -eq 0) {
    throw "MindWave semantic event is missing"
  }
  if ("telemetry.flight.brain_demo.status" -notin $topics) {
    throw "Bounded Brain2Devices demo status is missing"
  }
  if ("telemetry.flight.fleet_sequence.status" -notin $topics) {
    throw "Bounded fleet-sequence status is missing"
  }
  if ("robot.sensor.state" -notin $topics) { throw "LEGO sensor event is missing" }

  $sessionId = [string]$activeMonitoring[0].sessionId
  $brainArmResult = Invoke-AuthenticatedPost "/api/v1/fabric/commands" $bootstrap (
    New-CommandRequest $sessionId "brain_flight_demo" "mobility.flight.brain_demo.arm" @{
      attentionEnabled = $true
      attentionThreshold = 50
      meditationEnabled = $false
      meditationThreshold = 50
      blinkEnabled = $false
      blinkThreshold = 50
      dwellSeconds = 0
      instructorPresent = $true
      flightAreaClear = $true
      emergencyPlanReady = $true
    } 5000
  )
  Wait-ForCommandSuccess $brainArmResult $bootstrap "Simulated MindWave demo arm"
  $completedBrainDemo = $null
  $brainDemoDeadline = [DateTimeOffset]::UtcNow.AddSeconds(10)
  do {
    Start-Sleep -Milliseconds 250
    $brainDemoEvents = @(
      Expand-Sequence (Invoke-AuthenticatedGet "/api/v1/fabric/events?sessionId=$sessionId&limit=500" $bootstrap) |
        Where-Object { $_.event.topic -eq "telemetry.flight.brain_demo.status" }
    )
    $completedBrainDemo = @(
      $brainDemoEvents |
        Where-Object { $_.event.payload.phase -eq "simulated_completed" } |
        Select-Object -Last 1
    )
  } while ($completedBrainDemo.Count -eq 0 -and [DateTimeOffset]::UtcNow -lt $brainDemoDeadline)
  if ($completedBrainDemo.Count -ne 1) {
    throw "Simulated MindWave demo did not reach completed status"
  }
  if (
    [string]$completedBrainDemo[0].event.payload.triggeredBy -ne "attention" -or
    $completedBrainDemo[0].event.payload.armed -ne $false
  ) {
    throw "Simulated MindWave demo did not consume its one-shot attention trigger"
  }
  $brainStopResult = Invoke-AuthenticatedPost "/api/v1/fabric/commands" $bootstrap (
    New-CommandRequest $sessionId "brain_flight_demo" "mobility.flight.brain_demo.stop" @{} 5000
  )
  Wait-ForCommandSuccess $brainStopResult $bootstrap "Simulated MindWave demo stop"

  $armResult = Invoke-AuthenticatedPost "/api/v1/fabric/commands" $bootstrap (
    New-CommandRequest $sessionId "fleet_sequence_controller" "mobility.flight.fleet_sequence.arm" @{
      droneIds = @("primary", "drone-2", "drone-3")
      allowedSourceNodeIds = @()
      launchIntervalSeconds = 1
      minimumBatteryPercent = 30
      instructorPresent = $true
      flightAreaClear = $true
      emergencyPlanReady = $true
      independentRoutesConfirmed = $true
    } 5000
  )
  Wait-ForCommandSuccess $armResult $bootstrap "Simulated fleet arm"
  $startResult = Invoke-AuthenticatedPost "/api/v1/fabric/commands" $bootstrap (
    New-CommandRequest $sessionId "fleet_sequence_controller" "mobility.flight.fleet_sequence.start" @{} 2000
  )
  Wait-ForCommandSuccess $startResult $bootstrap "Simulated fleet start"
  $completedFleet = $null
  $fleetDeadline = [DateTimeOffset]::UtcNow.AddSeconds(12)
  do {
    Start-Sleep -Milliseconds 250
    $fleetEvents = @(
      Expand-Sequence (Invoke-AuthenticatedGet "/api/v1/fabric/events?sessionId=$sessionId&limit=500" $bootstrap) |
        Where-Object { $_.event.topic -eq "telemetry.flight.fleet_sequence.status" }
    )
    $completedFleet = @($fleetEvents | Where-Object { $_.event.payload.phase -eq "completed" } | Select-Object -Last 1)
  } while ($completedFleet.Count -eq 0 -and [DateTimeOffset]::UtcNow -lt $fleetDeadline)
  if ($completedFleet.Count -ne 1) { throw "Simulated fleet did not reach completed status" }
  $launched = @($completedFleet[0].event.payload.launchedDroneIds)
  if (($launched -join ",") -ne "primary,drone-2,drone-3") {
    throw "Simulated fleet launch order was '$($launched -join ',')'"
  }
  $stopResult = Invoke-AuthenticatedPost "/api/v1/fabric/commands" $bootstrap (
    New-CommandRequest $sessionId "fleet_sequence_controller" "mobility.flight.fleet_sequence.stop" @{} 5000
  )
  Wait-ForCommandSuccess $stopResult $bootstrap "Simulated fleet stop"

  $mediaSources = @(
    Expand-Sequence (Invoke-AuthenticatedGet "/api/v1/fabric/media/sources" $bootstrap)
  )
  $telloCamera = $mediaSources | Where-Object { $_.nodeId -eq "tello-01" } | Select-Object -First 1
  if ($null -eq $telloCamera -or $telloCamera.state -ne "online") {
    throw "Simulated Tello camera did not publish into the unified media wall"
  }

  Write-Host "PASS three independent Tellos, MindWave, bounded-demo, bounded-fleet, and sensor-only LEGO processes registered"
  Write-Host "PASS simulated MindWave attention completed one bounded one-shot demo and disarmed"
  Write-Host "PASS bounded fleet arm/start completed primary, drone-2, drone-3 in order and stop succeeded"
  Write-Host "PASS Tello exposes land/emergency only and LEGO sensor-only exposes no movement"
  Write-Host "PASS one shared unarmed monitoring session emitted semantic events and a Tello camera frame"
  if ($HoldSeconds -gt 0) {
    Write-Host "READY browser smoke window is open for $HoldSeconds seconds"
    Start-Sleep -Seconds $HoldSeconds
  }
}
finally {
  try {
    & $legoLauncher `
      -Mode Stop `
      -FabricPort $FabricPort `
      -SharedFabricRoot $fabricRoot `
      -StateRoot $legoRoot `
      -NoOpenConsole
  } catch { Write-Warning "LEGO test cleanup failed: $($_.Exception.Message)" }
  try {
    & $brainLauncher `
      -Mode Stop `
      -Device All `
      -FabricPort $FabricPort `
      -SharedFabricRoot $fabricRoot `
      -StateRoot $brainRoot `
      -NoOpenConsole
  } catch { Write-Warning "Brain adapter test cleanup failed: $($_.Exception.Message)" }
  try {
    & $fabricLauncher `
      -Mode Stop `
      -FabricPort $FabricPort `
      -StateRoot $fabricRoot `
      -NoOpenConsole
  } catch { Write-Warning "Fabric test cleanup failed: $($_.Exception.Message)" }

  if (-not $KeepState -and (Test-Path -LiteralPath $StateRoot)) {
    $resolved = [IO.Path]::GetFullPath($StateRoot)
    if (
      $resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
      (Split-Path $resolved -Leaf) -match '^cit-fabric-e2e-[0-9a-f]{32}$'
    ) {
      Remove-Item -LiteralPath $resolved -Recurse -Force
    }
  }
}

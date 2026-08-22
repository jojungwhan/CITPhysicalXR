#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Preflight", "Start", "Scan", "Status", "Open", "Stop")]
  [string]$Mode = "Start",
  [string]$Brain2DevicesRoot = "",
  [string]$StateRoot = "",
  [string]$SharedFabricRoot = "",
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8766,
  [ValidateRange(1024, 65535)]
  [int]$BrainPort = 8765,
  [switch]$AllowPhysical,
  [switch]$NoOpenConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $Brain2DevicesRoot) {
  $Brain2DevicesRoot = Join-Path (Split-Path $repositoryRoot -Parent) "brain2devices"
}
if (-not $StateRoot) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\brain2devices"
}
if (-not $SharedFabricRoot) {
  $SharedFabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
}
$Brain2DevicesRoot = [IO.Path]::GetFullPath($Brain2DevicesRoot)
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$SharedFabricRoot = [IO.Path]::GetFullPath($SharedFabricRoot)
$statePath = Join-Path $StateRoot "state.json"
$logRoot = Join-Path $StateRoot "logs"
$brainOrigin = "http://127.0.0.1:$BrainPort"
$fabricOrigin = "http://127.0.0.1:$FabricPort"
$fabricLauncher = Join-Path $repositoryRoot "tools\hardware\interaction-fabric-console.ps1"
$discoveryScript = Join-Path $repositoryRoot "tools\hardware\find-classroom-devices.ps1"
$brainExecutable = Join-Path $Brain2DevicesRoot ".venv\Scripts\brain2devices-web.exe"

function Get-ListeningProcessId([int]$Port) {
  $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($null -eq $listener) { return $null }
  return [int]$listener.OwningProcess
}

function Get-ProcessCommandLine([int]$ProcessId) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
  if ($null -eq $process) { return $null }
  return [string]$process.CommandLine
}

function Load-State {
  if (-not (Test-Path -LiteralPath $statePath)) { return @{} }
  return [IO.File]::ReadAllText($statePath, [Text.Encoding]::UTF8) |
    ConvertFrom-Json -AsHashtable
}

function Save-State([hashtable]$State) {
  New-Item -ItemType Directory -Path $StateRoot, $logRoot -Force | Out-Null
  $State.updatedAt = [DateTimeOffset]::UtcNow.ToString("o")
  [IO.File]::WriteAllText(
    $statePath,
    ($State | ConvertTo-Json -Depth 6),
    [Text.UTF8Encoding]::new($false)
  )
}

function Wait-Until([scriptblock]$Condition, [string]$FailureMessage, [int]$TimeoutSeconds = 35) {
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    if (& $Condition) { return }
    Start-Sleep -Milliseconds 250
  } while ([DateTimeOffset]::UtcNow -lt $deadline)
  throw $FailureMessage
}

function Get-BrainState {
  return Invoke-RestMethod -Uri "$brainOrigin/api/state" -TimeoutSec 5
}

function Show-Preflight {
  if (-not (Test-Path -LiteralPath $Brain2DevicesRoot)) {
    throw "Brain2Devices checkout was not found at $Brain2DevicesRoot"
  }
  if (-not (Test-Path -LiteralPath $brainExecutable)) {
    throw "Brain2Devices hardware executable was not found at $brainExecutable"
  }
  if (-not (Test-Path -LiteralPath $discoveryScript)) {
    throw "CIT device discovery script was not found"
  }
  Write-Host "PASS preserved Brain2Devices checkout $Brain2DevicesRoot"
  & $brainExecutable --self-test
  if ($LASTEXITCODE -ne 0) { throw "Brain2Devices hardware self-test failed" }
  Write-Host "PASS self-test imports the packaged Tello and MindWave dependencies"
  Write-Host "PASS startup alone sends no Tello SDK, flight, or MindWave connection command"
}

function Ensure-Fabric {
  if ($null -ne (Get-ListeningProcessId $FabricPort)) { return }
  $parameters = @{
    Mode = "Start"
    FabricPort = $FabricPort
    StateRoot = $SharedFabricRoot
    NoOpenConsole = $true
  }
  if ($AllowPhysical) { $parameters.AllowPhysical = $true }
  & $fabricLauncher @parameters
}

function Start-BrainService([hashtable]$State) {
  $listenerId = Get-ListeningProcessId $BrainPort
  if ($null -ne $listenerId) {
    try {
      $null = Get-BrainState
    } catch {
      throw "Port $BrainPort is not the expected local Brain2Devices service"
    }
    $State.brainPid = $listenerId
    $State.brainOwned = $false
    Save-State $State
    Write-Host "INFO preserved existing Brain2Devices service on $brainOrigin"
    return
  }
  New-Item -ItemType Directory -Path $StateRoot, $logRoot -Force | Out-Null
  $process = Start-Process `
    -FilePath $brainExecutable `
    -ArgumentList @("--no-browser", "--web-port", [string]$BrainPort) `
    -WorkingDirectory $Brain2DevicesRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot "brain2devices.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "brain2devices.stderr.log") `
    -PassThru
  $State.brainLauncherPid = $process.Id
  $State.brainOwned = $true
  Save-State $State
  Wait-Until {
    try {
      $null = Get-BrainState
      return $true
    } catch { return $false }
  } "Brain2Devices did not become ready; inspect $logRoot"
  $State.brainPid = Get-ListeningProcessId $BrainPort
  Save-State $State
}

function Show-Status([hashtable]$State) {
  Write-Host "Unified classroom UI: $fabricOrigin/fabric"
  Write-Host "Brain2Devices helper: $brainOrigin"
  $listenerId = Get-ListeningProcessId $BrainPort
  if ($null -eq $listenerId) {
    Write-Host "Brain2Devices: stopped"
    return
  }
  $snapshot = Get-BrainState
  $connectedDrones = @($snapshot.fleet.drones | Where-Object { $_.connection -eq "connected" }).Count
  Write-Host "Brain2Devices: running (PID $listenerId, $($snapshot.mode) mode)"
  Write-Host "Tello sessions: $connectedDrones connected / $(@($snapshot.fleet.drones).Count) listed"
  Write-Host "MindWave: $($snapshot.headset.connection)"
  Write-Host "Ownership: $(if ($State.ContainsKey('brainOwned') -and $State.brainOwned) { 'this launcher' } else { 'preserved external service' })"
}

function Stop-BrainService([hashtable]$State) {
  if (-not ($State.ContainsKey("brainOwned") -and $State.brainOwned)) {
    Write-Host "Preserved Brain2Devices because this launcher does not own it."
    return
  }
  $processIds = @()
  if ($State.ContainsKey("brainPid")) { $processIds += [int]$State.brainPid }
  if ($State.ContainsKey("brainLauncherPid")) { $processIds += [int]$State.brainLauncherPid }
  foreach ($processId in @($processIds | Sort-Object -Unique)) {
    $commandLine = Get-ProcessCommandLine $processId
    if ($null -eq $commandLine) { continue }
    if (
      -not $commandLine.Contains("brain2devices-web", [StringComparison]::OrdinalIgnoreCase) -and
      -not $commandLine.Contains("brain2devices.cli", [StringComparison]::OrdinalIgnoreCase)
    ) {
      Write-Warning "Ignoring PID $processId because it is not Brain2Devices"
      continue
    }
    Stop-Process -Id $processId
    Wait-Process -Id $processId -Timeout 15 -ErrorAction SilentlyContinue
  }
  $State.brainOwned = $false
  $State.stoppedAt = [DateTimeOffset]::UtcNow.ToString("o")
  Save-State $State
  Write-Host "Stopped only the Brain2Devices process owned by this launcher."
}

$state = Load-State
switch ($Mode) {
  "Preflight" {
    Show-Preflight
  }
  "Scan" {
    & $discoveryScript `
      -StateRoot $SharedFabricRoot `
      -Brain2DevicesRoot $Brain2DevicesRoot
  }
  "Status" {
    Show-Status $state
  }
  "Open" {
    & $fabricLauncher -Mode Open -FabricPort $FabricPort -StateRoot $SharedFabricRoot
  }
  "Stop" {
    Stop-BrainService $state
  }
  "Start" {
    Show-Preflight
    Ensure-Fabric
    Start-BrainService $state
    Show-Status $state
    if (-not $NoOpenConsole) {
      & $fabricLauncher -Mode Open -FabricPort $FabricPort -StateRoot $SharedFabricRoot
    }
  }
}

#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Start", "Enable", "Scan", "Status", "Open")]
  [string]$Mode = "Start",
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8766,
  [string]$StateRoot = "",
  [string]$Brain2DevicesRoot = "",
  [switch]$AllowPhysical
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $StateRoot) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
}
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$fabricLauncher = Join-Path $repositoryRoot "tools\hardware\interaction-fabric-console.ps1"
$brainLauncher = Join-Path $repositoryRoot "tools\hardware\brain2devices-hardware.ps1"
$discoveryScript = Join-Path $repositoryRoot "tools\hardware\find-classroom-devices.ps1"

function Start-ClassroomDevices([bool]$RestartSimulationHost) {
  $physicalEnabled = [bool]$AllowPhysical -or $RestartSimulationHost
  if ($RestartSimulationHost) {
    $health = $null
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:$FabricPort/api/v1/fabric/healthz" -TimeoutSec 3
    } catch {
      # No matching listener is the normal cold-start path. The fixed Fabric
      # launcher performs the authoritative credential/port validation below.
    }
    if ($null -ne $health -and $health.physicalActuation -ne "enabled") {
      Write-Host "Restarting the local simulation-only Fabric in disarmed physical-adapter mode."
      & $fabricLauncher -Mode Stop -FabricPort $FabricPort -StateRoot $StateRoot
    }
  }

  $fabricParameters = @{
    Mode = "Start"
    FabricPort = $FabricPort
    StateRoot = $StateRoot
    NoOpenConsole = $true
  }
  if ($physicalEnabled) { $fabricParameters.AllowPhysical = $true }
  & $fabricLauncher @fabricParameters

  $brainParameters = @{
    Mode = "Start"
    FabricPort = $FabricPort
    SharedFabricRoot = $StateRoot
    NoOpenConsole = $true
  }
  if ($Brain2DevicesRoot) { $brainParameters.Brain2DevicesRoot = $Brain2DevicesRoot }
  if ($physicalEnabled) { $brainParameters.AllowPhysical = $true }
  & $brainLauncher @brainParameters

  Write-Host "READY. In Classroom Control, choose Find devices."
  Write-Host "CIT will show connected, found, ready, and setup-needed hardware separately."
  & $fabricLauncher -Mode Open -FabricPort $FabricPort -StateRoot $StateRoot
}

switch ($Mode) {
  "Scan" {
    $parameters = @{ StateRoot = $StateRoot }
    if ($Brain2DevicesRoot) { $parameters.Brain2DevicesRoot = $Brain2DevicesRoot }
    & $discoveryScript @parameters
  }
  "Status" {
    & $fabricLauncher -Mode Status -FabricPort $FabricPort -StateRoot $StateRoot
    $brainParameters = @{
      Mode = "Status"
      FabricPort = $FabricPort
      SharedFabricRoot = $StateRoot
    }
    if ($Brain2DevicesRoot) { $brainParameters.Brain2DevicesRoot = $Brain2DevicesRoot }
    & $brainLauncher @brainParameters
  }
  "Open" {
    & $fabricLauncher -Mode Open -FabricPort $FabricPort -StateRoot $StateRoot
  }
  "Start" {
    Start-ClassroomDevices -RestartSimulationHost $false
  }
  "Enable" {
    Start-ClassroomDevices -RestartSimulationHost $true
  }
}

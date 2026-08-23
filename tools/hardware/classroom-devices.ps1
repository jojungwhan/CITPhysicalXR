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
$siteProfilePath = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\site\site.json"
if (-not $Brain2DevicesRoot -and (Test-Path -LiteralPath $siteProfilePath -PathType Leaf)) {
  try {
    $siteProfile = [IO.File]::ReadAllText($siteProfilePath, [Text.Encoding]::UTF8) |
      ConvertFrom-Json
    if (
      $siteProfile.PSObject.Properties.Name -contains "brain2devicesRoot" -and
      $siteProfile.brain2devicesRoot
    ) {
      $Brain2DevicesRoot = [string]$siteProfile.brain2devicesRoot
    }
  } catch {
    throw "The CIT business-site profile is invalid; run the business installer again."
  }
}
if ($Brain2DevicesRoot) {
  $Brain2DevicesRoot = [IO.Path]::GetFullPath($Brain2DevicesRoot)
}
if (-not $StateRoot) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
}
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$fabricLauncher = Join-Path $repositoryRoot "tools\hardware\interaction-fabric-console.ps1"
$brainLauncher = Join-Path $repositoryRoot "tools\hardware\brain2devices-hardware.ps1"
$matterLauncher = Join-Path $repositoryRoot "tools\hardware\matter-smart-plug.ps1"
$discoveryScript = Join-Path $repositoryRoot "tools\hardware\find-classroom-devices.ps1"

function Start-ClassroomDevices([bool]$RestartSimulationHost) {
  $physicalEnabled = [bool]$AllowPhysical -or $RestartSimulationHost
  $lanMediaEnabled = $physicalEnabled
  if ($RestartSimulationHost) {
    $health = $null
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:$FabricPort/api/v1/fabric/healthz" -TimeoutSec 3
    } catch {
      # No matching listener is the normal cold-start path. The fixed Fabric
      # launcher performs the authoritative credential/port validation below.
    }
    if ($null -ne $health) {
      Write-Host "Restarting the local Fabric with the managed device paths, disarmed physical adapters, and scoped phone-camera access."
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
  if ($lanMediaEnabled) { $fabricParameters.AllowLanMedia = $true }
  if ($Brain2DevicesRoot) { $fabricParameters.Brain2DevicesRoot = $Brain2DevicesRoot }
  & $fabricLauncher @fabricParameters

  try {
    & $matterLauncher `
      -Mode ControllerStart `
      -SharedFabricRoot $StateRoot `
      -FabricPort $FabricPort `
      -SkipBuild `
      -NoOpenConsole
  } catch {
    Write-Warning "The local Matter controller is unavailable: $($_.Exception.Message)"
  }

  $brainParameters = @{
    Mode = "Start"
    FabricPort = $FabricPort
    SharedFabricRoot = $StateRoot
    NoOpenConsole = $true
  }
  if ($Brain2DevicesRoot) { $brainParameters.Brain2DevicesRoot = $Brain2DevicesRoot }
  if ($physicalEnabled) { $brainParameters.AllowPhysical = $true }
  try {
    & $brainLauncher @brainParameters
  } catch {
    Write-Warning "The optional Brain2Devices integration is unavailable: $($_.Exception.Message)"
  }

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

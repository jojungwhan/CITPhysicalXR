#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Start", "Scan", "Status", "Open")]
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
    $fabricParameters = @{
      Mode = "Start"
      FabricPort = $FabricPort
      StateRoot = $StateRoot
      NoOpenConsole = $true
    }
    if ($AllowPhysical) { $fabricParameters.AllowPhysical = $true }
    & $fabricLauncher @fabricParameters

    $brainParameters = @{
      Mode = "Start"
      FabricPort = $FabricPort
      SharedFabricRoot = $StateRoot
      NoOpenConsole = $true
    }
    if ($Brain2DevicesRoot) { $brainParameters.Brain2DevicesRoot = $Brain2DevicesRoot }
    if ($AllowPhysical) { $brainParameters.AllowPhysical = $true }
    & $brainLauncher @brainParameters

    Write-Host "READY. In Classroom Control, choose Find devices."
    Write-Host "CIT will show connected, found, ready, and setup-needed hardware separately."
    & $fabricLauncher -Mode Open -FabricPort $FabricPort -StateRoot $StateRoot
  }
}

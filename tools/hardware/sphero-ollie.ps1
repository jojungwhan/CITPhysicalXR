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

$launcher = Join-Path $PSScriptRoot "sphero-bolt.ps1"
& $launcher @PSBoundParameters -RobotVariant ollie
exit $LASTEXITCODE

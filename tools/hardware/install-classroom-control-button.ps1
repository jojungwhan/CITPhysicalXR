#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Install", "Remove", "Status")]
  [string]$Mode = "Install",
  [string]$DesktopRoot = "",
  [string]$ProgramsRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (-not $IsWindows) { throw "CIT Classroom Control shortcuts require Windows." }

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$launcher = Join-Path $PSScriptRoot "classroom-control-button.ps1"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
  throw "The CIT Classroom Control button is missing."
}
$pwshCommand = Get-Command pwsh -ErrorAction Stop
if (-not $DesktopRoot) { $DesktopRoot = [Environment]::GetFolderPath("Desktop") }
if (-not $ProgramsRoot) { $ProgramsRoot = [Environment]::GetFolderPath("Programs") }
$DesktopRoot = [IO.Path]::GetFullPath($DesktopRoot)
$ProgramsRoot = [IO.Path]::GetFullPath($ProgramsRoot)
$startMenuDirectory = Join-Path $ProgramsRoot "CIT Classroom"
$shortcutPaths = @(
  (Join-Path $DesktopRoot "CIT Classroom Control.lnk"),
  (Join-Path $startMenuDirectory "CIT Classroom Control.lnk")
)

function Install-Shortcut([string]$Path) {
  $parent = Split-Path $Path -Parent
  New-Item -ItemType Directory -Path $parent -Force | Out-Null
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($Path)
  $shortcut.TargetPath = $pwshCommand.Source
  $shortcut.Arguments = "-WindowStyle Hidden -NoProfile -STA -File `"$launcher`""
  $shortcut.WorkingDirectory = $repositoryRoot
  $shortcut.Description = "Start and open CIT Classroom Control without PowerShell"
  $shortcut.IconLocation = "$($pwshCommand.Source),0"
  $shortcut.WindowStyle = 1
  $shortcut.Save()
}

switch ($Mode) {
  "Install" {
    foreach ($path in $shortcutPaths) { Install-Shortcut -Path $path }
    Write-Host "Installed the CIT Classroom Control button on the Desktop and Start menu."
  }
  "Remove" {
    foreach ($path in $shortcutPaths) {
      if (Test-Path -LiteralPath $path -PathType Leaf) {
        Remove-Item -LiteralPath $path -Force
      }
    }
    if (
      (Test-Path -LiteralPath $startMenuDirectory -PathType Container) -and
      @(Get-ChildItem -LiteralPath $startMenuDirectory -Force).Count -eq 0
    ) {
      Remove-Item -LiteralPath $startMenuDirectory -Force
    }
    Write-Host "Removed the CIT Classroom Control shortcuts."
  }
  "Status" {
    foreach ($path in $shortcutPaths) {
      Write-Host "$(if (Test-Path -LiteralPath $path -PathType Leaf) { 'READY' } else { 'MISSING' }) $path"
    }
  }
}

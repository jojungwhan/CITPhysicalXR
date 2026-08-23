#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Install", "Status")]
  [string]$Mode = "Install",
  [string]$SiteId = "business-site",
  [string]$RoomId = "classroom-a",
  [string]$WifiSsid = "",
  [string]$Brain2DevicesRoot = "",
  [switch]$SkipWifiConfiguration,
  [switch]$SkipBrain2Devices,
  [switch]$SkipLegoBluetooth,
  [switch]$InstallPrerequisites,
  [switch]$OpenAfterInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $IsWindows) { throw "The CIT business-site installer requires Windows 11." }
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$citStateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR"
$siteRoot = Join-Path $citStateRoot "site"
$siteProfilePath = Join-Path $siteRoot "site.json"
$matterLauncher = Join-Path $PSScriptRoot "matter-smart-plug.ps1"
$shortcutInstaller = Join-Path $PSScriptRoot "install-classroom-control-button.ps1"
$classroomLauncher = Join-Path $PSScriptRoot "classroom-devices.ps1"
$sourceCatalogPath = Join-Path $PSScriptRoot "external-sources.generated.json"
$brainRequirementsPath = Join-Path $repositoryRoot "config\brain2devices-windows-requirements.txt"
$corepackPath = ""

if (-not (Test-Path -LiteralPath $sourceCatalogPath -PathType Leaf)) {
  throw "Generated external-source catalog is missing; run pnpm generate"
}
$sourceCatalog = [IO.File]::ReadAllText($sourceCatalogPath, [Text.Encoding]::UTF8) |
  ConvertFrom-Json
$brainSource = $sourceCatalog.sources.brain2devices
if (-not $Brain2DevicesRoot) {
  $Brain2DevicesRoot = Join-Path `
    (Join-Path $citStateRoot "external") `
    ([string]$brainSource.localDirectory)
}
$brainRoot = [IO.Path]::GetFullPath($Brain2DevicesRoot)

function Resolve-Executable([string]$Name) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($null -eq $command) { return "" }
  return $command.Source
}

function Assert-Path([string]$Path, [string]$Description) {
  if (-not (Test-Path -LiteralPath $Path)) { throw "$Description was not found at $Path" }
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
  Push-Location $repositoryRoot
  try {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable exited with code $LASTEXITCODE" }
  } finally {
    Pop-Location
  }
}

function Test-VisualCppBuildTools {
  $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
  if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) { return $false }
  $installation = & $vswhere `
    -latest `
    -products * `
    -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
    -property installationPath
  return [bool]$installation
}

function Install-MissingPrerequisites {
  $winget = Resolve-Executable "winget"
  if (-not $winget) {
    throw "Windows Package Manager (winget) is required for automatic prerequisite setup."
  }
  if (-not (Resolve-Executable "node")) {
    Write-Host "Installing the pinned Node.js 22 runtime..."
    Invoke-Checked $winget @(
      "install", "--exact", "--id", "OpenJS.NodeJS",
      "--version", "22.17.0", "--accept-source-agreements", "--accept-package-agreements"
    )
    $env:Path = "${env:ProgramFiles}\nodejs;$env:Path"
  }
  if (-not (Resolve-Executable "uv")) {
    Write-Host "Installing uv..."
    Invoke-Checked $winget @(
      "install", "--exact", "--id", "astral-sh.uv",
      "--accept-source-agreements", "--accept-package-agreements"
    )
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
  }
  if (-not (Resolve-Executable "git")) {
    Write-Host "Installing Git for the exact external integration checkouts..."
    Invoke-Checked $winget @(
      "install", "--exact", "--id", "Git.Git",
      "--accept-source-agreements", "--accept-package-agreements"
    )
    $env:Path = "$env:ProgramFiles\Git\cmd;$env:Path"
  }
  if (-not (Test-VisualCppBuildTools)) {
    Write-Host "Installing Visual C++ build tools required by the Windows Matter Bluetooth driver..."
    Invoke-Checked $winget @(
      "install", "--exact", "--id", "Microsoft.VisualStudio.2022.BuildTools",
      "--override", "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended",
      "--accept-source-agreements", "--accept-package-agreements"
    )
  }
}

function Assert-Prerequisites {
  $node = Resolve-Executable "node"
  $uv = Resolve-Executable "uv"
  $git = Resolve-Executable "git"
  if (-not $node -or -not $uv -or -not $git) {
    throw "Node.js 22, uv, and Git are required. Run this installer again with -InstallPrerequisites."
  }
  $nodeVersion = (& $node --version).TrimStart('v')
  if ([version]$nodeVersion -lt [version]"22.17.0" -or [version]$nodeVersion -ge [version]"23.0.0") {
    throw "CIT currently requires Node.js 22.17 through 22.x; found $nodeVersion."
  }
  if (-not (Test-VisualCppBuildTools)) {
    throw "Visual C++ Build Tools are required for local Matter Bluetooth. Run this installer again with -InstallPrerequisites."
  }
  Invoke-Checked $uv @("python", "install", "3.13")
  $nodeGypPython = (& $uv python find 3.13).Trim()
  if (-not $nodeGypPython) { throw "uv could not prepare Python for the Matter Bluetooth build." }
  $env:npm_config_python = $nodeGypPython
  $corepack = Join-Path (Split-Path $node -Parent) "corepack.cmd"
  if (-not (Test-Path -LiteralPath $corepack -PathType Leaf)) {
    throw "Node.js Corepack is missing; reinstall the pinned Node.js 22 package."
  }
  $script:corepackPath = $corepack
  Invoke-Checked $corepack @("pnpm@10.28.2", "--version")
}

function Prepare-Brain2Devices {
  if ($SkipBrain2Devices) { return }
  $git = Resolve-Executable "git"
  $uv = Resolve-Executable "uv"
  $expectedRepository = [string]$brainSource.repository
  $expectedRevision = [string]$brainSource.revision
  $createdCheckout = $false
  if (-not (Test-Path -LiteralPath $brainRoot -PathType Container)) {
    Write-Host "Installing the exact Brain2Devices source used by CIT..."
    Invoke-Checked $git @("clone", "--filter=blob:none", "--no-checkout", $expectedRepository, $brainRoot)
    $createdCheckout = $true
  }
  if (-not (Test-Path -LiteralPath (Join-Path $brainRoot ".git") -PathType Container)) {
    throw "Brain2Devices path exists but is not a Git checkout: $brainRoot"
  }
  $remote = (& $git -C $brainRoot config --get remote.origin.url | Out-String).Trim()
  if ($remote.TrimEnd("/") -ne $expectedRepository.TrimEnd("/")) {
    throw "Brain2Devices origin must be $expectedRepository; found '$remote'"
  }
  $currentRevision = (& $git -C $brainRoot rev-parse HEAD | Out-String).Trim()
  if (-not $createdCheckout) {
    $dirty = (& $git -C $brainRoot status --porcelain=v1 --untracked-files=normal | Out-String).Trim()
    if ($dirty) {
      throw "Brain2Devices has local or untracked changes; CIT will not execute, replace, or switch that checkout. Use a separate clean checkout at $expectedRevision"
    }
    if ($currentRevision -ne $expectedRevision) {
      throw "Brain2Devices is an existing checkout at $currentRevision; CIT will not switch its branch. Use a separate checkout at $expectedRevision"
    }
  }
  if ($createdCheckout) {
    Invoke-Checked $git @("-C", $brainRoot, "fetch", "origin", $expectedRevision)
    Invoke-Checked $git @("-C", $brainRoot, "checkout", "--detach", $expectedRevision)
  }
  $verifiedRevision = (& $git -C $brainRoot rev-parse HEAD | Out-String).Trim()
  $verifiedStatus = (& $git -C $brainRoot status --porcelain=v1 --untracked-files=normal | Out-String).Trim()
  if ($verifiedRevision -ne $expectedRevision -or $verifiedStatus) {
    throw "Brain2Devices must be a clean checkout at $expectedRevision before CIT installs it."
  }
  Assert-Path $brainRequirementsPath "Pinned Brain2Devices Windows requirements"
  Invoke-Checked $uv @("python", "install", "3.12")
  $brainPython = Join-Path $brainRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path -LiteralPath $brainPython -PathType Leaf)) {
    Invoke-Checked $uv @("venv", "--python", "3.12", (Join-Path $brainRoot ".venv"))
  }
  Invoke-Checked $uv @(
    "pip", "install", "--python", $brainPython,
    "--requirement", $brainRequirementsPath
  )
  Invoke-Checked $uv @(
    "pip", "install", "--python", $brainPython, "--no-deps", "--editable", $brainRoot
  )
  $brainExecutable = Join-Path $brainRoot ".venv\Scripts\brain2devices-web.exe"
  Assert-Path $brainExecutable "Brain2Devices executable"
  & $brainExecutable --self-test
  if ($LASTEXITCODE -ne 0) { throw "Brain2Devices hardware self-test failed" }
  Write-Host "Prepared Brain2Devices $expectedRevision in its independent Python 3.12 environment."
}

function Prepare-LegoBluetooth {
  if ($SkipLegoBluetooth) { return }
  $uv = Resolve-Executable "uv"
  Write-Host "Preparing the pinned optional Pybricks Bluetooth transport..."
  Invoke-Checked $uv @(
    "sync", "--package", "cit-lego-pybricks", "--extra", "hardware", "--frozen", "--inexact"
  )
}

function Save-SiteProfile {
  foreach ($entry in @(@("SiteId", $SiteId), @("RoomId", $RoomId))) {
    if ([string]$entry[1] -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
      throw "$($entry[0]) must begin with a letter or number and contain only letters, numbers, dot, underscore, or dash."
    }
  }
  New-Item -ItemType Directory -Path $siteRoot -Force | Out-Null
  $profile = [ordered]@{
    schemaVersion = "1.0"
    siteId = $SiteId
    roomId = $RoomId
    repositoryRoot = $repositoryRoot
    installedAt = [DateTimeOffset]::UtcNow.ToString('o')
    smartPlugProvisioning = "matter-local"
    vendorCloudAccountRequired = $false
    brain2devicesRevision = $(if ($SkipBrain2Devices) { $null } else { [string]$brainSource.revision })
    brain2devicesRoot = $(if ($SkipBrain2Devices) { $null } else { $brainRoot })
  }
  [IO.File]::WriteAllText(
    $siteProfilePath,
    ($profile | ConvertTo-Json -Depth 6),
    [Text.UTF8Encoding]::new($false)
  )
}

function Configure-MatterWifi {
  if ($SkipWifiConfiguration) { return }
  $ssid = if ($WifiSsid) { $WifiSsid } else { Read-Host "Classroom Wi-Fi name (SSID)" }
  if (-not $ssid) { throw "A classroom Wi-Fi SSID is required for Wi-Fi Matter plugs." }
  $passwordSecure = Read-Host "Classroom Wi-Fi password (not printed or sent to CIT Fabric)" -AsSecureString
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passwordSecure)
  $password = $null
  $payload = $null
  try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $payload = @{ ssid = $ssid; password = $password } | ConvertTo-Json -Compress
    $payload | & (Resolve-Executable "pwsh") `
      -NoProfile `
      -NonInteractive `
      -File $matterLauncher `
      -Mode ConfigureWifi `
      -SiteId $SiteId `
      -RoomId $RoomId `
      -SkipBuild
    if ($LASTEXITCODE -ne 0) { throw "The local Matter controller rejected Wi-Fi setup." }
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $password = $null
    $payload = $null
  }
}

function Show-Status {
  Write-Host "CIT business-site profile: $(if (Test-Path -LiteralPath $siteProfilePath) { $siteProfilePath } else { 'not installed' })"
  if (Test-Path -LiteralPath $siteProfilePath) {
    $profile = Get-Content -LiteralPath $siteProfilePath -Raw | ConvertFrom-Json
    Write-Host "Site / room: $($profile.siteId) / $($profile.roomId)"
    Write-Host "Smart-plug path: local Matter; vendor cloud account required=$($profile.vendorCloudAccountRequired)"
    Write-Host "Brain2Devices revision: $(if ($profile.PSObject.Properties.Name -contains 'brain2devicesRevision' -and $profile.brain2devicesRevision) { $profile.brain2devicesRevision } else { 'not installed by this profile' })"
    Write-Host "Brain2Devices managed source: $(if ($profile.PSObject.Properties.Name -contains 'brain2devicesRoot' -and $profile.brain2devicesRoot) { $profile.brain2devicesRoot } else { 'not installed by this profile' })"
  }
  & $matterLauncher -Mode Status
  & $shortcutInstaller -Mode Status
}

if ($Mode -eq "Status") {
  Show-Status
  exit 0
}

if ($InstallPrerequisites) { Install-MissingPrerequisites }
Assert-Prerequisites

$uv = Resolve-Executable "uv"
if (-not $corepackPath) { throw "Node.js Corepack is unavailable after prerequisite setup." }
Write-Host "Preparing the pinned CIT Python workspace..."
Invoke-Checked $uv @("sync", "--all-packages", "--frozen", "--extra", "smart-plug-lan")
Write-Host "Preparing the pinned CIT web, controller, and Windows Bluetooth dependencies..."
Invoke-Checked $corepackPath @("pnpm@10.28.2", "install", "--frozen-lockfile")
Invoke-Checked $corepackPath @("pnpm@10.28.2", "build")
Prepare-Brain2Devices
Prepare-LegoBluetooth
Save-SiteProfile

& $matterLauncher -Mode ControllerStart -SiteId $SiteId -RoomId $RoomId -SkipBuild
if ($LASTEXITCODE -ne 0) { throw "The local Matter controller did not start." }
Configure-MatterWifi
& $shortcutInstaller -Mode Install
if ($LASTEXITCODE -ne 0) { throw "The Classroom Control shortcut was not installed." }

Write-Host ""
Write-Host "CIT business-site installation is ready."
Write-Host "No proprietary smart-plug account, cloud API, device ID, or local key was configured."
Write-Host "Tutors can now use the CIT Classroom Control desktop button, choose Find devices, and add Matter plugs by their printed setup code."
Write-Host "Use only plugs whose product label explicitly includes Matter."

if ($OpenAfterInstall) {
  & $classroomLauncher -Mode Enable -AllowPhysical
}

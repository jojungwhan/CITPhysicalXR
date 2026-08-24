#Requires -Version 5.1

[CmdletBinding()]
param(
  [string]$SiteId = "business-site",
  [string]$RoomId = "classroom-a",
  [string]$WifiSsid = "",
  [string]$SiteProfilePath = "",
  [switch]$SkipWifiConfiguration,
  [switch]$SkipBrain2Devices,
  [switch]$SkipLegoBluetooth,
  [switch]$NoOpenAfterInstall,
  [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
  throw "This setup package supports Windows 11 only."
}

$bundleRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$bundleManifestPath = Join-Path $bundleRoot "bundle-manifest.json"
$defaultSiteProfilePath = Join-Path $bundleRoot "cit-site-template.json"
$installRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "CITPhysicalXR\app"))

function Resolve-Executable([string]$Name) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($null -eq $command) { return "" }
  return $command.Source
}

function Assert-Identifier([string]$Name, [string]$Value) {
  if ($Value -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
    throw "$Name must begin with a letter or number and contain only letters, numbers, dot, underscore, or dash."
  }
}

function Read-JsonObject([string]$Path, [string]$Description) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "$Description was not found at $Path"
  }
  $file = Get-Item -LiteralPath $Path
  if ($file.Length -gt 1MB) { throw "$Description is unexpectedly large." }
  return [IO.File]::ReadAllText($file.FullName, [Text.Encoding]::UTF8) | ConvertFrom-Json
}

function Remove-InstallStaging([string]$Path) {
  $resolved = [IO.Path]::GetFullPath($Path)
  $parent = [IO.Path]::GetFullPath((Split-Path $resolved -Parent))
  $leaf = Split-Path $resolved -Leaf
  if ($parent -ne $installRoot -or -not $leaf.StartsWith(".installing-")) {
    throw "Refusing to remove an unexpected installation path: $resolved"
  }
  if (Test-Path -LiteralPath $resolved) {
    Remove-Item -LiteralPath $resolved -Recurse -Force
  }
}

function Assert-VerifiedSourceTree(
  [string]$Root,
  [string]$ExpectedManifestHash,
  [string]$ExpectedRevision
) {
  $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd(
    [IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar
  )
  $rootPrefix = "$resolvedRoot$([IO.Path]::DirectorySeparatorChar)"
  $sourceManifestPath = Join-Path $resolvedRoot "cit-release-files.json"
  if (-not (Test-Path -LiteralPath $sourceManifestPath -PathType Leaf)) {
    throw "The extracted source file manifest is missing."
  }
  $actualManifestHash = (
    Get-FileHash -LiteralPath $sourceManifestPath -Algorithm SHA256
  ).Hash.ToLowerInvariant()
  if ($actualManifestHash -ne $ExpectedManifestHash) {
    throw "The extracted source file manifest failed its SHA-256 check."
  }
  $sourceManifest = Read-JsonObject $sourceManifestPath "Release file manifest"
  if (
    [string]$sourceManifest.schemaVersion -ne "1.0" -or
    [string]$sourceManifest.revision -ne $ExpectedRevision
  ) {
    throw "The extracted source file manifest identifies a different release."
  }
  $files = @($sourceManifest.files)
  if ($files.Count -lt 1 -or $files.Count -gt 10000) {
    throw "The extracted source file manifest has an invalid file count."
  }
  foreach ($entry in $files) {
    $relative = [string]$entry.path
    $segments = $relative -split '/'
    if (
      -not $relative -or
      $relative.Contains("\") -or
      [IO.Path]::IsPathRooted($relative) -or
      $segments -contains ".." -or
      $segments -contains "." -or
      $relative.IndexOfAny([char[]]@(0, 10, 13)) -ge 0
    ) {
      throw "The release file manifest contains an unsafe path."
    }
    $filePath = [IO.Path]::GetFullPath((Join-Path $resolvedRoot $relative))
    if (-not $filePath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
      throw "A release file escaped the versioned source directory."
    }
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
      throw "A release file is missing: $relative"
    }
    $expectedHash = ([string]$entry.sha256).ToLowerInvariant()
    if ($expectedHash -notmatch '^[a-f0-9]{64}$') {
      throw "A release file has an invalid checksum: $relative"
    }
    if ((Get-Item -LiteralPath $filePath).Length -ne [long]$entry.sizeBytes) {
      throw "A release file has an unexpected size: $relative"
    }
    $actualHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
      throw "A release file failed its SHA-256 check: $relative"
    }
  }
}

Write-Host "CIT Classroom Setup" -ForegroundColor Cyan
Write-Host "This setup does not copy tokens, Wi-Fi passwords, Matter databases, or device credentials."
Write-Host "Internet access is required while pinned Microsoft, OpenJS, Python, npm, PyPI, and Git dependencies are installed."

$manifest = Read-JsonObject $bundleManifestPath "Bundle manifest"
if ([string]$manifest.schemaVersion -ne "1.0") { throw "Unsupported bundle manifest version." }
$revision = [string]$manifest.revision
$version = [string]$manifest.version
$payloadName = [string]$manifest.payloadFile
$expectedPayloadHash = ([string]$manifest.payloadSha256).ToLowerInvariant()
$sourceManifestName = [string]$manifest.sourceManifestFile
$expectedSourceManifestHash = ([string]$manifest.sourceManifestSha256).ToLowerInvariant()
if ($revision -notmatch '^[a-f0-9]{7,40}$') { throw "The bundle revision is invalid." }
if (-not $version -or $version.Length -gt 80) { throw "The bundle version is invalid." }
if ($payloadName -ne "payload.zip") { throw "The bundle payload name is invalid." }
if ($expectedPayloadHash -notmatch '^[a-f0-9]{64}$') { throw "The bundle checksum is invalid." }
if ($sourceManifestName -ne "cit-release-files.json") {
  throw "The source file manifest name is invalid."
}
if ($expectedSourceManifestHash -notmatch '^[a-f0-9]{64}$') {
  throw "The source file manifest checksum is invalid."
}

$payloadPath = [IO.Path]::GetFullPath((Join-Path $bundleRoot $payloadName))
if ((Split-Path $payloadPath -Parent) -ne $bundleRoot) {
  throw "The bundle payload must remain beside this installer."
}
if (-not (Test-Path -LiteralPath $payloadPath -PathType Leaf)) {
  throw "The installation payload is missing: $payloadPath"
}
$actualPayloadHash = (Get-FileHash -LiteralPath $payloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualPayloadHash -ne $expectedPayloadHash) {
  throw "The installation payload failed its SHA-256 integrity check. Download it again."
}

$resolvedSiteProfile = if ($SiteProfilePath) {
  [IO.Path]::GetFullPath($SiteProfilePath)
} elseif (Test-Path -LiteralPath $defaultSiteProfilePath -PathType Leaf) {
  $defaultSiteProfilePath
} else {
  ""
}
if ($resolvedSiteProfile) {
  $siteProfile = Read-JsonObject $resolvedSiteProfile "CIT site template"
  $allowedProperties = @("schemaVersion", "siteId", "roomId")
  $unexpected = @($siteProfile.PSObject.Properties.Name | Where-Object { $_ -notin $allowedProperties })
  if ($unexpected.Count -gt 0) {
    throw "The site template contains unsupported or sensitive fields: $($unexpected -join ', ')"
  }
  if ([string]$siteProfile.schemaVersion -ne "1.0") { throw "Unsupported site template version." }
  $SiteId = [string]$siteProfile.siteId
  $RoomId = [string]$siteProfile.roomId
}
Assert-Identifier "SiteId" $SiteId
Assert-Identifier "RoomId" $RoomId

if ($ValidateOnly) {
  New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
  $validationRoot = [IO.Path]::GetFullPath(
    (Join-Path $installRoot ".installing-$([Guid]::NewGuid().ToString('N'))")
  )
  New-Item -ItemType Directory -Path $validationRoot | Out-Null
  try {
    Expand-Archive -LiteralPath $payloadPath -DestinationPath $validationRoot
    $validationSource = Join-Path $validationRoot "CITPhysicalXR"
    Assert-VerifiedSourceTree $validationSource $expectedSourceManifestHash $revision
  } finally {
    Remove-InstallStaging $validationRoot
  }
  Write-Host "The CIT transfer package and every source file passed integrity validation."
  exit 0
}

$winget = Resolve-Executable "winget"
$pwsh = Resolve-Executable "pwsh"
$pwshNeedsInstall = -not $pwsh
if ($pwsh) {
  $existingPwshVersion = (& $pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()').Trim()
  $pwshNeedsInstall = [version]$existingPwshVersion -lt [version]"7.4"
}
if ($pwshNeedsInstall) {
  if (-not $winget) {
    throw "Windows Package Manager (winget) is required to install PowerShell 7.4."
  }
  Write-Host "Installing PowerShell 7 for the CIT hardware runtime..."
  & $winget install --exact --id Microsoft.PowerShell --force --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) { throw "PowerShell 7 installation failed with code $LASTEXITCODE." }
  $commonPwsh = Join-Path $env:ProgramFiles "PowerShell\7\pwsh.exe"
  if (Test-Path -LiteralPath $commonPwsh -PathType Leaf) { $pwsh = $commonPwsh }
}
if (-not $pwsh) { throw "PowerShell 7.4 or later is required." }
$pwshVersion = (& $pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()').Trim()
if ([version]$pwshVersion -lt [version]"7.4") {
  throw "PowerShell 7.4 or later is required; found $pwshVersion."
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
$targetRoot = [IO.Path]::GetFullPath((Join-Path $installRoot $revision))
if ((Split-Path $targetRoot -Parent) -ne $installRoot) {
  throw "The versioned installation target is outside the CIT application directory."
}

if (-not (Test-Path -LiteralPath $targetRoot -PathType Container)) {
  $stagingRoot = [IO.Path]::GetFullPath((Join-Path $installRoot ".installing-$([Guid]::NewGuid().ToString('N'))"))
  New-Item -ItemType Directory -Path $stagingRoot | Out-Null
  try {
    Write-Host "Verifying complete. Extracting CIT $version ($($revision.Substring(0, 12)))..."
    Expand-Archive -LiteralPath $payloadPath -DestinationPath $stagingRoot
    $stagedSource = Join-Path $stagingRoot "CITPhysicalXR"
    $releaseMetadataPath = Join-Path $stagedSource "cit-release-source.json"
    $releaseMetadata = Read-JsonObject $releaseMetadataPath "Release metadata"
    if ([string]$releaseMetadata.revision -ne $revision) {
      throw "The extracted source revision does not match the verified bundle manifest."
    }
    Assert-VerifiedSourceTree $stagedSource $expectedSourceManifestHash $revision
    Move-Item -LiteralPath $stagedSource -Destination $targetRoot
  } finally {
    Remove-InstallStaging $stagingRoot
  }
} else {
  Assert-VerifiedSourceTree $targetRoot $expectedSourceManifestHash $revision
  $installedMetadata = Read-JsonObject (Join-Path $targetRoot "cit-release-source.json") "Installed release metadata"
  if ([string]$installedMetadata.revision -ne $revision) {
    throw "The existing versioned CIT directory does not match this package."
  }
  Write-Host "Reusing the verified CIT $version source already installed for this revision."
}

$businessInstaller = Join-Path $targetRoot "tools\hardware\install-business-site.ps1"
if (-not (Test-Path -LiteralPath $businessInstaller -PathType Leaf)) {
  throw "The CIT business-site installer is missing from the verified payload."
}
$installerArguments = @(
  "-NoProfile",
  "-STA",
  "-File", $businessInstaller,
  "-Mode", "Install",
  "-SiteId", $SiteId,
  "-RoomId", $RoomId,
  "-InstallPrerequisites"
)
if ($WifiSsid) { $installerArguments += @("-WifiSsid", $WifiSsid) }
if ($SkipWifiConfiguration) { $installerArguments += "-SkipWifiConfiguration" }
if ($SkipBrain2Devices) { $installerArguments += "-SkipBrain2Devices" }
if ($SkipLegoBluetooth) { $installerArguments += "-SkipLegoBluetooth" }
if (-not $NoOpenAfterInstall) { $installerArguments += "-OpenAfterInstall" }

Write-Host "Installing the local CIT runtime and hardware adapters for $SiteId / $RoomId..."
& $pwsh @installerArguments
if ($LASTEXITCODE -ne 0) { throw "CIT setup stopped with code $LASTEXITCODE." }

Write-Host ""
Write-Host "CIT Classroom Control is ready." -ForegroundColor Green
Write-Host "Use the Desktop or Start-menu shortcut; the page opens with a short-lived local access ticket."
Write-Host "For Matter plugs at this new site, factory-reset and commission each plug locally from the page."

#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Preflight", "Build", "Install")]
  [string]$Mode = "Preflight",
  [string]$GlassesRepositoryRoot = "",
  [string]$DeviceSerial = "",
  [switch]$DeveloperMode,
  [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $GlassesRepositoryRoot) {
  $GlassesRepositoryRoot = Join-Path (Split-Path $repositoryRoot -Parent) "glasses2CLI"
}
$GlassesRepositoryRoot = [IO.Path]::GetFullPath($GlassesRepositoryRoot)
$nativeRoot = Join-Path $GlassesRepositoryRoot "apps\android-bridge\native"
$gradleWrapper = Join-Path $nativeRoot "gradlew.bat"
$apkPath = Join-Path $nativeRoot "phone\build\outputs\apk\debug\phone-debug.apk"

function Assert-File([string]$Path, [string]$Description) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "$Description was not found at $Path"
  }
}

function Resolve-Executable([string]$Name) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($null -eq $command) { throw "Required executable '$Name' was not found" }
  return $command.Source
}

function Read-ProcessSecret([string]$Name, [string]$Prompt) {
  $current = [Environment]::GetEnvironmentVariable($Name)
  if (-not [string]::IsNullOrWhiteSpace($current)) { return $current }
  if (-not [Environment]::UserInteractive) {
    throw "$Name is required in the process environment."
  }
  $secure = Read-Host -Prompt $Prompt -AsSecureString
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($value)) { throw "$Name cannot be empty." }
    [Environment]::SetEnvironmentVariable($Name, $value, "Process")
    return $value
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
  }
}

function Resolve-GitHubPackagesUser([string]$Token) {
  $current = [Environment]::GetEnvironmentVariable("GITHUB_ACTOR")
  if (-not [string]::IsNullOrWhiteSpace($current)) { return $current }
  try {
    $profile = Invoke-RestMethod `
      -Uri "https://api.github.com/user" `
      -Headers @{
        Authorization = "Bearer $Token"
        Accept = "application/vnd.github+json"
        "User-Agent" = "CIT-Meta-Camera-Setup"
      } `
      -TimeoutSec 20
    $username = [string]$profile.login
  } catch {
    throw "The GitHub package token could not identify its account. Check that the token is valid and try again."
  }
  if ([string]::IsNullOrWhiteSpace($username)) {
    throw "The GitHub package token returned no account name."
  }
  [Environment]::SetEnvironmentVariable("GITHUB_ACTOR", $username, "Process")
  return $username
}

function Assert-MetaPackageAccess([string]$Token, [string]$Username) {
  $artifacts = @("mwdat-core", "mwdat-camera")
  foreach ($artifact in $artifacts) {
    $uri = "https://maven.pkg.github.com/facebook/meta-wearables-dat-android/com/meta/wearable/$artifact/0.9.0/$artifact-0.9.0.pom"
    $credentialBytes = [Text.Encoding]::UTF8.GetBytes("${Username}:$Token")
    try {
      $authorization = "Basic $([Convert]::ToBase64String($credentialBytes))"
      $response = Invoke-WebRequest `
        -Uri $uri `
        -Method Get `
        -Headers @{ Authorization = $authorization } `
        -SkipHttpErrorCheck `
        -TimeoutSec 20
    } catch {
      throw "Could not reach Meta's official Android package repository. Check the technician computer's internet connection and try again."
    } finally {
      if ($credentialBytes.Length -gt 0) {
        [Array]::Clear($credentialBytes, 0, $credentialBytes.Length)
      }
      $authorization = $null
    }
    if ($response.StatusCode -ne 200) {
      throw "The GitHub token cannot read Meta's $artifact package (HTTP $($response.StatusCode)). Give the token read:packages access, then choose Meta camera setup again."
    }
  }
  Write-Host "PASS Meta SDK packages are accessible"
}

function Assert-MetaBuildEnvironment {
  if (-not $IsWindows) {
    throw "The current Meta camera companion installer is validated for Windows 11."
  }
  Assert-File $gradleWrapper "Android Gradle wrapper"
  $githubToken = Read-ProcessSecret "GITHUB_TOKEN" "GitHub token with read:packages access"
  $githubUsername = Resolve-GitHubPackagesUser $githubToken
  Assert-MetaPackageAccess $githubToken $githubUsername
  if (-not $DeveloperMode) {
    $applicationId = [Environment]::GetEnvironmentVariable("CIT_META_APPLICATION_ID")
    if ([string]::IsNullOrWhiteSpace($applicationId)) {
      $applicationId = Read-Host -Prompt "Meta Wearables application ID"
      if ([string]::IsNullOrWhiteSpace($applicationId)) {
        throw "CIT_META_APPLICATION_ID cannot be empty."
      }
      [Environment]::SetEnvironmentVariable(
        "CIT_META_APPLICATION_ID",
        $applicationId,
        "Process"
      )
    }
    Read-ProcessSecret "CIT_META_CLIENT_TOKEN" "Meta Wearables client token" | Out-Null
  }
}

function Invoke-MetaGradle([string[]]$Tasks) {
  Push-Location $nativeRoot
  try {
    # Switching the optional Kotlin source set invalidates this project's
    # ordinary configuration cache; keep this one technician build isolated.
    & $gradleWrapper "--no-configuration-cache" "-PcitMetaCamera=true" @Tasks
    if ($LASTEXITCODE -ne 0) {
      throw "The Meta camera Android build failed with exit code $LASTEXITCODE. If Maven returned 401, the GitHub token is missing read:packages access."
    }
  } finally {
    Pop-Location
  }
}

function Build-MetaCompanion {
  Assert-MetaBuildEnvironment
  Invoke-MetaGradle @(
    ":phone:testDebugUnitTest",
    ":phone:assembleDebug"
  )
  Assert-File $apkPath "Meta-enabled CIT glasses APK"
  Write-Host "READY Meta camera companion built at $apkPath"
}

function Get-AndroidDevices([string]$AdbPath) {
  $rows = & $AdbPath devices
  if ($LASTEXITCODE -ne 0) { throw "adb devices failed" }
  return @(
    $rows |
      Select-Object -Skip 1 |
      ForEach-Object {
        $parts = @($_ -split "\s+")
        if ($parts.Count -ge 2 -and $parts[1] -eq "device") { $parts[0] }
      } |
      Where-Object { $_ }
  )
}

if ($Mode -eq "Preflight") {
  Assert-MetaBuildEnvironment
  Resolve-Executable "java" | Out-Null
  Write-Host "PASS preserved Android bridge at $GlassesRepositoryRoot"
  Write-Host "PASS Meta SDK package credential is valid and held in process memory"
  Write-Host $(if ($DeveloperMode) {
      "PASS Meta developer-mode build selected"
    } else {
      "PASS Meta application credentials are present in process memory"
    })
  Write-Host "No phone, glasses, camera, or classroom device was contacted."
  exit 0
}

if ($Mode -eq "Build") {
  Build-MetaCompanion
  exit 0
}

if (-not $SkipBuild) {
  Build-MetaCompanion
} else {
  Assert-MetaBuildEnvironment
  Assert-File $apkPath "Existing Meta-enabled CIT glasses APK"
}

$adb = Resolve-Executable "adb"
$devices = @(Get-AndroidDevices $adb)
if ($DeviceSerial) {
  if ($DeviceSerial -notin $devices) {
    throw "Android device '$DeviceSerial' is not connected and authorized in adb."
  }
  $target = $DeviceSerial
} elseif ($devices.Count -eq 1) {
  $target = [string]$devices[0]
} elseif ($devices.Count -eq 0) {
  throw "No authorized Android phone is connected. Enable USB debugging, connect the phone, and accept its authorization prompt."
} else {
  throw "More than one Android device is connected. Re-run with -DeviceSerial followed by the exact adb serial."
}

& $adb -s $target install -r $apkPath
if ($LASTEXITCODE -ne 0) { throw "adb could not install the Meta camera companion" }
Write-Host "READY installed the Meta-enabled CIT glasses companion on $target"
Write-Host "Tutors now pair it from Classroom Control; they do not need this script or its credentials."

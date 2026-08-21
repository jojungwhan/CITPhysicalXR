#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Preflight", "Start", "Open", "Status", "CopyCredential", "Stop")]
  [string]$Mode = "Start",
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8766,
  [string]$StateRoot = "",
  [switch]$AllowPhysical,
  [switch]$SkipBuild,
  [switch]$NoOpenConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $StateRoot) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
}
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$statePath = Join-Path $StateRoot "state.json"
$secretRoot = Join-Path $StateRoot "secrets"
$logRoot = Join-Path $StateRoot "logs"
$runtimeDataRoot = Join-Path $StateRoot "runtime"
$bootstrapSecretPath = Join-Path $secretRoot "fabric-bootstrap.dpapi"
$fabricOrigin = "http://127.0.0.1:$FabricPort"
$fabricProcessMarker = "cit_runtime.fabric_service:create_persistent_fabric_app"

function Assert-Path([string]$Path, [string]$Description) {
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "$Description was not found at $Path"
  }
}

function Resolve-Executable([string]$Name) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($null -eq $command) { throw "Required executable '$Name' was not found" }
  return $command.Source
}

function Invoke-External(
  [string]$Executable,
  [string[]]$Arguments,
  [string]$WorkingDirectory
) {
  Push-Location $WorkingDirectory
  try {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "$Executable exited with code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function New-RandomCredential {
  $bytes = [Security.Cryptography.RandomNumberGenerator]::GetBytes(48)
  return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Save-ProtectedSecret([string]$Path, [string]$Value) {
  $secure = ConvertTo-SecureString -String $Value -AsPlainText -Force
  $ciphertext = ConvertFrom-SecureString -SecureString $secure
  [IO.File]::WriteAllText($Path, $ciphertext, [Text.UTF8Encoding]::new($false))
}

function Read-ProtectedSecret([string]$Path) {
  Assert-Path $Path "Protected Fabric credential"
  $ciphertext = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8).Trim()
  $secure = ConvertTo-SecureString -String $ciphertext
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
  }
}

function Load-State {
  if (-not (Test-Path -LiteralPath $statePath)) { return @{} }
  return [IO.File]::ReadAllText($statePath, [Text.Encoding]::UTF8) |
    ConvertFrom-Json -AsHashtable
}

function Save-State([hashtable]$State) {
  $State.updatedAt = [DateTimeOffset]::UtcNow.ToString('o')
  [IO.File]::WriteAllText(
    $statePath,
    ($State | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false)
  )
}

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

function Stop-ExactProcess([object]$ProcessId) {
  if ($null -eq $ProcessId) { return }
  $numericId = [int]$ProcessId
  $commandLine = Get-ProcessCommandLine $numericId
  if ($null -eq $commandLine) { return }
  if (-not $commandLine.Contains($fabricProcessMarker, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Ignoring stale PID $numericId because it is not the expected Fabric process"
    return
  }
  Stop-Process -Id $numericId
  Wait-Process -Id $numericId -Timeout 15 -ErrorAction SilentlyContinue
}

function Wait-Until(
  [scriptblock]$Condition,
  [string]$FailureMessage,
  [int]$TimeoutSeconds = 45
) {
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    if (& $Condition) { return }
    Start-Sleep -Milliseconds 250
  } while ([DateTimeOffset]::UtcNow -lt $deadline)
  throw $FailureMessage
}

function Invoke-JsonApi(
  [ValidateSet("GET", "POST")]
  [string]$Method,
  [string]$Uri,
  [string]$Credential
) {
  return Invoke-RestMethod `
    -Method $Method `
    -Uri $Uri `
    -Headers @{ Authorization = "Bearer $Credential" } `
    -TimeoutSec 10
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

function Start-HiddenProcess(
  [string]$Executable,
  [string[]]$Arguments,
  [hashtable]$Environment
) {
  return Start-Process `
    -FilePath $Executable `
    -ArgumentList $Arguments `
    -WorkingDirectory $repositoryRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot "cit-fabric.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "cit-fabric.stderr.log") `
    -Environment $Environment `
    -PassThru
}

function Show-Preflight {
  Assert-Path $repositoryRoot "CIT repository"
  foreach ($name in @("uv", "pnpm.cmd")) {
    Write-Host "PASS tool $name -> $(Resolve-Executable $name)"
  }
  $listener = Get-ListeningProcessId $FabricPort
  Write-Host $(if ($null -eq $listener) { "PASS Fabric port $FabricPort is available" } else { "INFO Fabric port $FabricPort is already in use by PID $listener" })
  Write-Host "PASS one console will accept input, output, bidirectional, simulator, and coding-agent nodes"
  Write-Host "Physical adapter dispatch: $(if ($AllowPhysical) { 'explicitly enabled; sessions remain disarmed by default' } else { 'disabled' })"
}

function Build-Systems {
  if ($SkipBuild) { return }
  Invoke-External (Resolve-Executable "uv") @("sync", "--all-packages", "--frozen") $repositoryRoot
  Invoke-External (Resolve-Executable "pnpm.cmd") @("install", "--frozen-lockfile") $repositoryRoot
  Invoke-External (Resolve-Executable "pnpm.cmd") @("build") $repositoryRoot
}

function Ensure-BootstrapCredential {
  if (Test-Path -LiteralPath $bootstrapSecretPath) {
    return Read-ProtectedSecret $bootstrapSecretPath
  }
  $credential = New-RandomCredential
  Save-ProtectedSecret $bootstrapSecretPath $credential
  return $credential
}

function Start-Fabric([hashtable]$State, [string]$Credential) {
  $listenerId = Get-ListeningProcessId $FabricPort
  if ($null -ne $listenerId) {
    try {
      $null = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/auth/whoami" -Credential $Credential
      $health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 5
      if ($AllowPhysical -and $health.physicalActuation -ne "enabled") {
        throw "physical actuation is disabled"
      }
    } catch {
      throw "Port $FabricPort does not host the matching shared Fabric: $($_.Exception.Message)"
    }
    $alreadyOwned = (
      $State.ContainsKey("fabricOwned") -and
      $State.fabricOwned -and
      $State.ContainsKey("fabricPid") -and
      [int]$State.fabricPid -eq $listenerId
    )
    $State.fabricPid = $listenerId
    $State.fabricOwned = [bool]$alreadyOwned
    $State.allowPhysical = ($health.physicalActuation -eq "enabled")
    Save-State $State
    return
  }

  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  Assert-Path $runtimePython "CIT virtual-environment Python"
  $process = Start-HiddenProcess `
    -Executable $runtimePython `
    -Arguments @(
      "-m", "uvicorn", "cit_runtime.fabric_service:create_persistent_fabric_app", "--factory",
      "--host", "127.0.0.1", "--port", [string]$FabricPort
    ) `
    -Environment @{
      CITXR_DATA_DIRECTORY = $runtimeDataRoot
      CITXR_PUBLIC_ORIGIN = $fabricOrigin
      CITXR_ALLOWED_HOSTS = "127.0.0.1,localhost"
    CITXR_FABRIC_BOOTSTRAP_TOKEN = $Credential
    CITXR_ALLOW_PHYSICAL_FABRIC = if ($AllowPhysical) { "true" } else { "false" }
    CITXR_DISCOVERY_STATE_ROOT = $StateRoot
  }
  $State.fabricLauncherPid = $process.Id
  $State.fabricOwned = $true
  $State.allowPhysical = [bool]$AllowPhysical
  Save-State $State
  Wait-Until {
    try {
      $null = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/auth/whoami" -Credential $Credential
      return $true
    } catch { return $false }
  } "The shared CIT Fabric did not become ready"
  $State.fabricPid = Get-ListeningProcessId $FabricPort
  Save-State $State
}

function Get-NodeIoType([object]$Node) {
  $publishes = @($Node.publishedCapabilities).Count -gt 0
  $consumes = @($Node.consumedCapabilities).Count -gt 0
  if ($publishes -and $consumes) { return "bidirectional" }
  if ($consumes) { return "output" }
  return "input"
}

function Show-Status([hashtable]$State, [string]$Credential) {
  Write-Host "Unified console: $fabricOrigin/fabric"
  Write-Host "State root: $StateRoot"
  $listenerId = Get-ListeningProcessId $FabricPort
  if ($null -eq $listenerId) {
    Write-Host "Fabric: offline"
    return
  }
  Write-Host "Fabric: listening (PID $listenerId)"
  if (-not $Credential) {
    Write-Host "Nodes: unavailable because the protected credential is missing"
    return
  }
  $health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 5
  Write-Host "Physical actuation: $($health.physicalActuation)"
  $nodes = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential $Credential))
  Write-Host "Registered nodes: $($nodes.Count)"
  foreach ($node in $nodes | Sort-Object { Get-NodeIoType $_ }, displayName) {
    $published = @($node.publishedCapabilities | ForEach-Object { $_.name }) -join ", "
    $consumed = @($node.consumedCapabilities | ForEach-Object { $_.name }) -join ", "
    Write-Host "  [$((Get-NodeIoType $node).ToUpperInvariant())] $($node.displayName) ($($node.nodeId))"
    if ($published) { Write-Host "    publishes: $published" }
    if ($consumed) { Write-Host "    consumes: $consumed" }
  }
}

function Open-TutorConsole([string]$Credential) {
  if (-not $Credential) { throw "No classroom access is available; start CIT first" }
  if (-not (Get-ListeningProcessId $FabricPort)) {
    throw "CIT Classroom Control is not running; use -Mode Start first"
  }
  try {
    $handoff = Invoke-JsonApi `
      -Method POST `
      -Uri "$fabricOrigin/api/v1/fabric/auth/console-tickets" `
      -Credential $Credential
    if (-not $handoff.ticket) { throw "CIT did not return a classroom access link" }
    $ticket = [Uri]::EscapeDataString([string]$handoff.ticket)
    Start-Process -FilePath "$fabricOrigin/fabric#console-ticket=$ticket" | Out-Null
    Write-Host "Opened Classroom Control with automatic local sign-in."
    Write-Host "The access link expires quickly and can be used only once."
  } catch {
    Write-Warning "Automatic sign-in is unavailable: $($_.Exception.Message)"
    Start-Process -FilePath "$fabricOrigin/fabric" | Out-Null
    Write-Host "The page will show the access-code fallback."
  }
}

function Stop-Fabric([hashtable]$State, [string]$Credential) {
  if ($Credential -and (Get-ListeningProcessId $FabricPort)) {
    try {
      $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/safety/stop-all" -Credential $Credential
    } catch {
      Write-Warning "Fabric emergency stop failed: $($_.Exception.Message)"
    }
  }
  if ($State.ContainsKey("fabricOwned") -and $State.fabricOwned) {
    $processIds = @()
    if ($State.ContainsKey("fabricPid")) { $processIds += $State.fabricPid }
    if ($State.ContainsKey("fabricLauncherPid")) { $processIds += $State.fabricLauncherPid }
    foreach ($processId in $processIds | Select-Object -Unique) {
      Stop-ExactProcess $processId
    }
  }
  foreach ($key in @("fabricPid", "fabricLauncherPid", "fabricOwned")) {
    $State.Remove($key)
  }
  $State.stoppedAt = [DateTimeOffset]::UtcNow.ToString('o')
  Save-State $State
  Write-Host "Stopped the shared Fabric process. Adapter launchers retain their own state and credentials."
}

if ($Mode -eq "Preflight") {
  Show-Preflight
  exit 0
}

$state = Load-State
$credential = if (Test-Path -LiteralPath $bootstrapSecretPath) {
  Read-ProtectedSecret $bootstrapSecretPath
} else { "" }

if ($Mode -eq "Status") {
  Show-Status $state $credential
  exit 0
}
if ($Mode -eq "Open") {
  Open-TutorConsole $credential
  exit 0
}
if ($Mode -eq "CopyCredential") {
  if (-not $credential) { throw "No shared Fabric credential exists; start the console first" }
  Set-Clipboard -Value $credential
  Write-Host "Copied the classroom access code without printing it."
  Write-Host "Use the page's access-code fallback, then clear the clipboard with: Set-Clipboard -Value ''"
  exit 0
}

New-Item -ItemType Directory -Path $StateRoot, $secretRoot, $logRoot, $runtimeDataRoot -Force | Out-Null
if ($Mode -eq "Stop") {
  Stop-Fabric $state $credential
  exit 0
}

Show-Preflight
Build-Systems
$credential = Ensure-BootstrapCredential
Start-Fabric $state $credential
Show-Status $state $credential
Write-Host "READY one Fabric UI is available at $fabricOrigin/fabric"
Write-Host "Attach integrations with -SharedFabricRoot `"$StateRoot`" -FabricPort $FabricPort"
Write-Host "Reopen tutor controls with: pnpm hardware:fabric:windows -- -Mode Open -FabricPort $FabricPort -StateRoot `"$StateRoot`""
if (-not $NoOpenConsole) { Open-TutorConsole $credential }

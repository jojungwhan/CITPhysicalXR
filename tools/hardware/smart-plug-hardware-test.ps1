#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Configure", "Preflight", "Start", "Status", "Verify", "CopyCredential", "Stop")]
  [string]$Mode = "Start",
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8766,
  [string]$SharedFabricRoot = "",
  [string]$StateRoot = "",
  [switch]$Live,
  [ValidateSet("tuya", "gosund")]
  [string]$Vendor = "tuya",
  [string]$Model = "Tuya-compatible outlet",
  [string]$DeviceAddress = "",
  [ValidateSet("3.1", "3.2", "3.3", "3.4", "3.5")]
  [string]$ProtocolVersion = "3.3",
  [ValidateRange(1, 255)]
  [int]$SwitchDps = 1,
  [ValidateRange(1, 30)]
  [int]$TimeoutSeconds = 3,
  [string]$SiteId = "local-site",
  [string]$RoomId = "local-room",
  [string]$HostId = $env:COMPUTERNAME,
  [string]$NodeId = "smart-plug-01",
  [switch]$SkipBuild,
  [switch]$NoOpenConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $SharedFabricRoot) {
  $SharedFabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
}
if (-not $StateRoot) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\smart-plug"
}
$SharedFabricRoot = [IO.Path]::GetFullPath($SharedFabricRoot)
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$statePath = Join-Path $StateRoot "state.json"
$secretRoot = Join-Path $StateRoot "secrets"
$logRoot = Join-Path $StateRoot "logs"
$hardwareSecretPath = Join-Path $secretRoot "tuya-device.dpapi"
$adapterSecretPath = Join-Path $secretRoot "fabric-adapter.dpapi"
$bootstrapSecretPath = Join-Path $SharedFabricRoot "secrets\fabric-bootstrap.dpapi"
$activationPath = Join-Path $StateRoot "session-active.flag"
$fabricOrigin = "http://127.0.0.1:$FabricPort"
$fabricAdapterUrl = "ws://127.0.0.1:$FabricPort/api/v1/adapters/connect"

function Assert-Path([string]$Path, [string]$Description) {
  if (-not (Test-Path -LiteralPath $Path)) { throw "$Description was not found at $Path" }
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
    if ($LASTEXITCODE -ne 0) { throw "$Executable exited with code $LASTEXITCODE" }
  } finally {
    Pop-Location
  }
}

function New-RandomCredential {
  $bytes = [Security.Cryptography.RandomNumberGenerator]::GetBytes(48)
  return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function ConvertFrom-SecretValue([Security.SecureString]$Value) {
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
  }
}

function Save-ProtectedSecret([string]$Path, [string]$Value) {
  $secure = ConvertTo-SecureString -String $Value -AsPlainText -Force
  $ciphertext = ConvertFrom-SecureString -SecureString $secure
  [IO.File]::WriteAllText($Path, $ciphertext, [Text.UTF8Encoding]::new($false))
}

function Read-ProtectedSecret([string]$Path) {
  Assert-Path $Path "Protected local secret"
  $ciphertext = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8).Trim()
  $secure = ConvertTo-SecureString -String $ciphertext
  return ConvertFrom-SecretValue $secure
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

function Stop-ExactAdapter([object]$ProcessId) {
  if ($null -eq $ProcessId) { return }
  $numericId = [int]$ProcessId
  $commandLine = Get-ProcessCommandLine $numericId
  if ($null -eq $commandLine) { return }
  if (-not $commandLine.Contains("cit_tuya_smart_plug", [StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Ignoring stale PID $numericId because it is not the smart-plug adapter"
    return
  }
  Stop-Process -Id $numericId
  Wait-Process -Id $numericId -Timeout 15 -ErrorAction SilentlyContinue
}

function Wait-Until(
  [scriptblock]$Condition,
  [string]$FailureMessage,
  [int]$Timeout = 30
) {
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($Timeout)
  do {
    if (& $Condition) { return }
    Start-Sleep -Milliseconds 250
  } while ([DateTimeOffset]::UtcNow -lt $deadline)
  throw $FailureMessage
}

function Invoke-JsonApi(
  [ValidateSet("GET", "POST", "PUT")]
  [string]$Method,
  [string]$Uri,
  [string]$Credential,
  [object]$Body = $null
) {
  $parameters = @{
    Method = $Method
    Uri = $Uri
    Headers = @{ Authorization = "Bearer $Credential" }
    TimeoutSec = 10
  }
  if ($null -ne $Body) {
    $parameters.ContentType = "application/json"
    $parameters.Body = $Body | ConvertTo-Json -Depth 12 -Compress
  }
  return Invoke-RestMethod @parameters
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

function Configure-Hardware([hashtable]$State) {
  New-Item -ItemType Directory -Path $StateRoot, $secretRoot, $logRoot -Force | Out-Null
  $address = if ($DeviceAddress) { $DeviceAddress } else { Read-Host "Smart-plug IPv4 address" }
  $deviceIdSecure = Read-Host "Tuya device ID" -AsSecureString
  $localKeySecure = Read-Host "Tuya local key (16 characters)" -AsSecureString
  $deviceId = ConvertFrom-SecretValue $deviceIdSecure
  $localKey = ConvertFrom-SecretValue $localKeySecure
  $protectedJson = $null
  try {
    if (-not $deviceId) { throw "Tuya device ID cannot be empty" }
    if ($localKey.Length -ne 16) { throw "Tuya local key must contain exactly 16 characters" }
    $protectedJson = @{ deviceId = $deviceId; localKey = $localKey } | ConvertTo-Json -Compress
    Save-ProtectedSecret $hardwareSecretPath $protectedJson
  } finally {
    $deviceId = $null
    $localKey = $null
    $protectedJson = $null
  }
  $State.vendor = $Vendor
  $State.model = $Model
  $State.deviceAddress = $address
  $State.protocolVersion = $ProtocolVersion
  $State.switchDps = $SwitchDps
  $State.timeoutSeconds = $TimeoutSeconds
  Save-State $State
  Write-Host "Saved non-secret device settings and a current-user DPAPI-protected Tuya profile."
  Write-Host "No credential was printed or written to the repository."
}

function Get-HardwareProfile([hashtable]$State) {
  foreach ($key in @("vendor", "model", "deviceAddress", "protocolVersion", "switchDps")) {
    if (-not $State.ContainsKey($key) -or -not $State[$key]) {
      throw "Hardware profile is incomplete; run -Mode Configure first"
    }
  }
  $protected = Read-ProtectedSecret $hardwareSecretPath | ConvertFrom-Json -AsHashtable
  if (-not $protected.deviceId -or -not $protected.localKey) {
    throw "Protected Tuya profile is incomplete; run -Mode Configure again"
  }
  return $protected
}

function Use-HardwareEnvironment([hashtable]$Profile, [scriptblock]$Operation) {
  $oldDeviceId = [Environment]::GetEnvironmentVariable("CIT_TUYA_DEVICE_ID", "Process")
  $oldLocalKey = [Environment]::GetEnvironmentVariable("CIT_TUYA_LOCAL_KEY", "Process")
  try {
    [Environment]::SetEnvironmentVariable("CIT_TUYA_DEVICE_ID", [string]$Profile.deviceId, "Process")
    [Environment]::SetEnvironmentVariable("CIT_TUYA_LOCAL_KEY", [string]$Profile.localKey, "Process")
    & $Operation
  } finally {
    [Environment]::SetEnvironmentVariable("CIT_TUYA_DEVICE_ID", $oldDeviceId, "Process")
    [Environment]::SetEnvironmentVariable("CIT_TUYA_LOCAL_KEY", $oldLocalKey, "Process")
  }
}

function Show-Preflight([hashtable]$State) {
  Assert-Path $repositoryRoot "CIT repository"
  foreach ($name in @("uv", "pnpm.cmd")) {
    Write-Host "PASS tool $name -> $(Resolve-Executable $name)"
  }
  Assert-Path $bootstrapSecretPath "Shared Fabric credential; start the unified console first"
  $listener = Get-ListeningProcessId $FabricPort
  if ($null -eq $listener) {
    throw "Shared Fabric is not listening on port $FabricPort; start hardware:fabric:windows"
  }
  $bootstrap = Read-ProtectedSecret $bootstrapSecretPath
  $null = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/auth/whoami" -Credential $bootstrap
  $health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 5
  if ($Live -and $health.physicalActuation -ne "enabled") {
    throw "Live smart-plug mode requires the shared Fabric to start with -AllowPhysical"
  }
  Write-Host "PASS matching shared Fabric (physical actuation: $($health.physicalActuation))"
  if (-not $Live) {
    Write-Host "PASS simulation mode; no LAN device will be contacted"
    return
  }
  $profile = Get-HardwareProfile $State
  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  Assert-Path $runtimePython "CIT virtual-environment Python"
  Use-HardwareEnvironment $profile {
    & $runtimePython -m cit_tuya_smart_plug.probe `
      --device-address ([string]$State.deviceAddress) `
      --protocol-version ([string]$State.protocolVersion) `
      --switch-dps ([string]$State.switchDps) `
      --timeout ([string]$State.timeoutSeconds)
    if ($LASTEXITCODE -ne 0) { throw "Read-only Tuya LAN probe failed" }
  }
  Write-Host "PASS $($State.vendor) model $($State.model) uses the configured Tuya LAN boundary"
}

function Build-Systems {
  if ($SkipBuild) { return }
  $uvArguments = @("sync", "--all-packages", "--frozen")
  if ($Live) { $uvArguments += @("--extra", "smart-plug-lan") }
  Invoke-External (Resolve-Executable "uv") $uvArguments $repositoryRoot
  Invoke-External (Resolve-Executable "pnpm.cmd") @("install", "--frozen-lockfile") $repositoryRoot
  Invoke-External (Resolve-Executable "pnpm.cmd") @("build") $repositoryRoot
}

function New-FabricSession([hashtable]$State, [string]$Bootstrap) {
  $session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions" -Credential $Bootstrap -Body @{
    coursePackId = "smart-plug-control"
    coursePackVersion = "1.0.0"
    siteId = $SiteId
    roomId = $RoomId
    mode = if ($Live) { "physical" } else { "simulation" }
  }
  $State.sessionId = $session.sessionId
  Save-State $State
  return $session
}

function New-AdapterCredential([hashtable]$State, [string]$Bootstrap, [string]$SessionId) {
  $identityId = "cit-plug-$($SessionId.Substring(0, [Math]::Min(16, $SessionId.Length)))"
  $response = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/auth/identities" -Credential $Bootstrap -Body @{
    identityId = $identityId
    actorType = "adapter"
    roles = @("plugin.cit.tuya-smart-plug")
    permissions = @("fabric.adapters.connect", "fabric.events.publish", "fabric.nodes.write")
    siteId = $SiteId
    roomId = $RoomId
    sessionId = $SessionId
    ttlSeconds = 86400
  }
  Save-ProtectedSecret $adapterSecretPath ([string]$response.token)
  $State.adapterIdentityId = $identityId
  Save-State $State
  return [string]$response.token
}

function Start-Adapter(
  [hashtable]$State,
  [string]$Credential,
  [string]$SessionId
) {
  if (Test-Path -LiteralPath $activationPath) { [IO.File]::Delete($activationPath) }
  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  $arguments = @(
    "-m", "cit_tuya_smart_plug",
    "--adapter-url", $fabricAdapterUrl,
    "--fabric-origin", $fabricOrigin,
    "--session-id", $SessionId,
    "--site-id", $SiteId,
    "--room-id", $RoomId,
    "--host-id", $HostId,
    "--node-id", $NodeId,
    "--activation-file", $activationPath,
    "--mode", $(if ($Live) { "lan" } else { "simulation" }),
    "--vendor", $(if ($Live) { [string]$State.vendor } else { $Vendor }),
    "--protocol-version", $(if ($Live) { [string]$State.protocolVersion } else { $ProtocolVersion }),
    "--switch-dps", $(if ($Live) { [string]$State.switchDps } else { [string]$SwitchDps }),
    "--timeout", $(if ($Live) { [string]$State.timeoutSeconds } else { [string]$TimeoutSeconds })
  )
  $environment = @{
    CIT_FABRIC_ADAPTER_TOKEN = $Credential
    CIT_TUYA_MODEL = $(if ($Live) { [string]$State.model } else { "Simulated smart plug" })
  }
  if ($Live) {
    $profile = Get-HardwareProfile $State
    $environment.CIT_TUYA_DEVICE_ID = [string]$profile.deviceId
    $environment.CIT_TUYA_LOCAL_KEY = [string]$profile.localKey
    $arguments += @("--device-address", [string]$State.deviceAddress)
  }
  $process = Start-Process `
    -FilePath $runtimePython `
    -ArgumentList $arguments `
    -WorkingDirectory $repositoryRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot "smart-plug-adapter.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "smart-plug-adapter.stderr.log") `
    -Environment $environment `
    -PassThru
  $State.adapterPid = $process.Id
  Save-State $State
  Wait-Until {
    try {
      $bootstrap = Read-ProtectedSecret $bootstrapSecretPath
      $nodes = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential $bootstrap))
      return @($nodes | Where-Object { $_.nodeId -eq $NodeId -and $_.connectionState -eq "connected" }).Count -eq 1
    } catch { return $false }
  } "Smart-plug adapter did not register; inspect $logRoot" 45
}

function Bind-And-Start([hashtable]$State, [string]$Bootstrap, [string]$SessionId) {
  $null = Invoke-JsonApi -Method PUT -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId/roles/classroom_plug" -Credential $Bootstrap -Body @{
    nodeId = $NodeId
  }
  if ($Live) {
    $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId/arm" -Credential $Bootstrap
  }
  $session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId/start" -Credential $Bootstrap
  [IO.File]::WriteAllText($activationPath, "active`n", [Text.Encoding]::ASCII)
  $State.live = [bool]$Live
  Save-State $State
  return $session
}

function Show-Status([hashtable]$State, [string]$Bootstrap) {
  Write-Host "Unified console: $fabricOrigin/fabric"
  Write-Host "Component state: $StateRoot"
  Write-Host "Mode: $(if ($State.ContainsKey('live') -and $State.live) { 'LIVE Tuya LAN' } else { 'simulation' })"
  Write-Host "Session: $(if ($State.ContainsKey('sessionId')) { $State.sessionId } else { 'not created' })"
  Write-Host "Adapter PID: $(if ($State.ContainsKey('adapterPid')) { $State.adapterPid } else { 'not recorded' })"
  if ($Bootstrap -and (Get-ListeningProcessId $FabricPort)) {
    $nodes = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential $Bootstrap))
    foreach ($node in $nodes | Where-Object { $_.nodeId -eq $NodeId }) {
      Write-Host "Node: $($node.displayName) [$($node.connectionState)/$($node.healthState)]"
    }
  }
  Write-Host "Logs: $logRoot"
}

function Show-Verification([hashtable]$State, [string]$Bootstrap) {
  if (-not $State.ContainsKey("sessionId")) { throw "No smart-plug session exists" }
  $sessionId = [string]$State.sessionId
  $events = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/events?sessionId=$sessionId&limit=500" -Credential $Bootstrap))
  $states = @($events | Where-Object { $_.event.topic -eq "power.switch.state" -and $_.event.sourceNodeId -eq $NodeId })
  if ($states.Count -eq 0) {
    throw "No normalized smart-plug state event has arrived; inspect $logRoot"
  }
  $latest = $states[-1].event.payload
  Write-Host "PASS adapter -> Fabric normalized state is recorded"
  Write-Host "Latest state: $(if ($latest.on) { 'ON' } else { 'OFF' }) ($($latest.source))"
  Write-Host "Use the unified UI to test explicit on then off; never attach an unapproved load."
}

function Request-SafeOff([hashtable]$State, [string]$Bootstrap) {
  if (-not $State.ContainsKey("sessionId") -or -not (Get-ListeningProcessId $FabricPort)) { return }
  try {
    $sessionId = [string]$State.sessionId
    $correlation = [guid]::NewGuid().ToString()
    $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/commands" -Credential $Bootstrap -Body @{
      messageId = [guid]::NewGuid().ToString()
      schemaVersion = "1.0"
      messageType = "command.requested"
      action = "power.switch.set"
      target = @{ role = "classroom_plug" }
      sessionId = $sessionId
      parameters = @{ on = $false }
      priority = "instructor_override"
      idempotencyKey = "launcher-off:$correlation"
      requestedAt = [DateTimeOffset]::UtcNow.ToString('o')
      ttlMs = 5000
      safetyProfile = "classroom-smart-plug"
      correlationId = $correlation
    }
    Write-Host "Requested the deterministic off safe state."
  } catch {
    $responseDetail = if ($_.ErrorDetails.Message) { " $($_.ErrorDetails.Message)" } else { "" }
    Write-Warning "Smart-plug off request failed: $($_.Exception.Message)$responseDetail"
  }
}

function Stop-Test([hashtable]$State, [string]$Bootstrap) {
  if ($Bootstrap) { Request-SafeOff $State $Bootstrap }
  if (Test-Path -LiteralPath $activationPath) { [IO.File]::Delete($activationPath) }
  if ($State.ContainsKey("adapterPid")) {
    $adapterId = [int]$State.adapterPid
    Wait-Process -Id $adapterId -Timeout 8 -ErrorAction SilentlyContinue
    Stop-ExactAdapter $adapterId
  }
  if ($Bootstrap -and $State.ContainsKey("sessionId") -and (Get-ListeningProcessId $FabricPort)) {
    try {
      $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$($State.sessionId)/stop" -Credential $Bootstrap
    } catch {
      Write-Warning "Session stop failed: $($_.Exception.Message)"
    }
  }
  Write-Host "Stopped only the smart-plug component. Shared Fabric and protected configuration remain."
}

$state = Load-State
if ($Mode -eq "Configure") {
  Configure-Hardware $state
  exit 0
}
if ($Mode -eq "Preflight") {
  Show-Preflight $state
  exit 0
}

$bootstrap = if (Test-Path -LiteralPath $bootstrapSecretPath) {
  Read-ProtectedSecret $bootstrapSecretPath
} else { "" }

if ($Mode -eq "Status") {
  Show-Status $state $bootstrap
  exit 0
}
if ($Mode -eq "Verify") {
  if (-not $bootstrap) { throw "Shared Fabric credential is unavailable" }
  Show-Verification $state $bootstrap
  exit 0
}
if ($Mode -eq "CopyCredential") {
  if (-not $bootstrap) { throw "Shared Fabric credential is unavailable" }
  Set-Clipboard -Value $bootstrap
  Write-Host "Copied the shared Fabric credential without printing it."
  Write-Host "Paste it into $fabricOrigin/fabric, then clear the clipboard."
  exit 0
}
if ($Mode -eq "Stop") {
  Stop-Test $state $bootstrap
  exit 0
}

New-Item -ItemType Directory -Path $StateRoot, $secretRoot, $logRoot -Force | Out-Null
Build-Systems
Show-Preflight $state
$bootstrap = Read-ProtectedSecret $bootstrapSecretPath
$session = New-FabricSession $state $bootstrap
$adapterCredential = New-AdapterCredential $state $bootstrap $session.sessionId
try {
  Start-Adapter $state $adapterCredential $session.sessionId
  $active = Bind-And-Start $state $bootstrap $session.sessionId
} catch {
  Write-Warning "Startup failed; applying smart-plug safe shutdown."
  Stop-Test $state $bootstrap
  throw
}

Write-Host "READY session $($active.sessionId) [$($active.state)]"
Write-Host "UI $fabricOrigin/fabric"
Write-Host "The adapter began OFF. Use the classroom_plug card for explicit on/off control."
if (-not $NoOpenConsole) {
  & (Join-Path $repositoryRoot "tools\hardware\interaction-fabric-console.ps1") `
    -Mode Open `
    -FabricPort $FabricPort `
    -StateRoot $SharedFabricRoot
}

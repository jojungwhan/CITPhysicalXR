#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Preflight", "Start", "Status", "Verify", "CopyCredential", "Stop")]
  [string]$Mode = "Start",
  [string]$ExternalRepositoryRoot = "",
  [string]$ExternalPython = "",
  [string]$BridgeDll = "",
  [ValidateSet("sdk", "s1-app")]
  [string]$RobotTransport = "sdk",
  [ValidateSet("ap", "sta", "rndis")]
  [string]$Connection = "sta",
  [ValidateSet("tcp", "udp")]
  [string]$Protocol = "tcp",
  [string]$RobotIp = "",
  [string]$LocalIp = "",
  [string]$SerialNumber = "",
  [ValidateSet("left", "right", "any")]
  [string]$Hand = "right",
  [ValidateRange(0.05, 0.35)]
  [double]$MaxSpeed = 0.35,
  [ValidateRange(5.0, 35.0)]
  [double]$MaxYaw = 35.0,
  [switch]$InvertStrafe,
  [switch]$InvertYaw,
  [switch]$Live,
  [switch]$ConnectOnly,
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8767,
  [string]$StateRoot = "",
  [string]$SharedFabricRoot = "",
  [string]$SiteId = "cit-local",
  [string]$RoomId = "robotics-lab",
  [string]$HostId = "",
  [string]$LeapNodeId = "leap-motion-01",
  [string]$RobotNodeId = "robomaster-s1-01",
  [string]$FabricSessionId = "",
  [switch]$FleetInputOnly,
  [switch]$SkipBuild,
  [switch]$NoOpenConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($ConnectOnly -and -not $Live) {
  throw "ConnectOnly is available only for the physical Live adapter"
}
if ($FleetInputOnly -and -not $Live) {
  throw "FleetInputOnly requires the physical Live Leap adapter"
}
if ($FleetInputOnly -and (-not $FabricSessionId -or $ConnectOnly)) {
  throw "FleetInputOnly requires FabricSessionId and cannot be combined with ConnectOnly"
}

$sourceCatalogPath = Join-Path $PSScriptRoot "external-sources.generated.json"
if (-not (Test-Path -LiteralPath $sourceCatalogPath -PathType Leaf)) {
  throw "Generated external-source catalog is missing; run pnpm generate"
}
$sourceCatalog = [IO.File]::ReadAllText($sourceCatalogPath, [Text.Encoding]::UTF8) |
  ConvertFrom-Json
$expectedRevision = [string]$sourceCatalog.sources.'robomaster-gesture-control'.revision
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $ExternalRepositoryRoot) {
  $ExternalRepositoryRoot = Join-Path (Split-Path $repositoryRoot -Parent) "robomaster-gesture-control-reference"
}
$ExternalRepositoryRoot = [IO.Path]::GetFullPath($ExternalRepositoryRoot)
if (-not $ExternalPython) {
  $ExternalPython = Join-Path (Split-Path $repositoryRoot -Parent) "robomasterCITCourse\.venv-robot\Scripts\python.exe"
}
$ExternalPython = [IO.Path]::GetFullPath($ExternalPython)
if (-not $BridgeDll) {
  $BridgeDll = Join-Path $ExternalRepositoryRoot "build\leap_hand_bridge.dll"
}
$BridgeDll = [IO.Path]::GetFullPath($BridgeDll)
if (-not $StateRoot) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\robomaster-leap-hardware-test"
}
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
if ($SharedFabricRoot) {
  $SharedFabricRoot = [IO.Path]::GetFullPath($SharedFabricRoot)
}
if (-not $HostId) {
  $HostId = "$($env:COMPUTERNAME.ToLowerInvariant())-robotics"
}

$identifierPattern = '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
foreach ($entry in @{
    SiteId = $SiteId
    RoomId = $RoomId
    HostId = $HostId
    LeapNodeId = $LeapNodeId
    RobotNodeId = $RobotNodeId
  }.GetEnumerator()) {
  if ($entry.Value -notmatch $identifierPattern) {
    throw "$($entry.Key) must be a CIT identifier"
  }
}
if ($FabricSessionId -and $FabricSessionId -notmatch $identifierPattern) {
  throw "FabricSessionId must be a CIT identifier"
}

$statePath = Join-Path $StateRoot "state.json"
$secretRoot = Join-Path $StateRoot "secrets"
$logRoot = Join-Path $StateRoot "logs"
$runtimeDataRoot = Join-Path $StateRoot "runtime"
$bootstrapSecretPath = if ($SharedFabricRoot) {
  Join-Path $SharedFabricRoot "secrets\fabric-bootstrap.dpapi"
} else {
  Join-Path $secretRoot "fabric-bootstrap.dpapi"
}
$leapAdapterSecretPath = Join-Path $secretRoot "leap-adapter.dpapi"
$robotAdapterSecretPath = Join-Path $secretRoot "robomaster-adapter.dpapi"
$activationPath = Join-Path $StateRoot "input-active.signal"
$leapStopPath = Join-Path $StateRoot "leap-stop.request"
$fabricOrigin = "http://127.0.0.1:$FabricPort"
$fabricAdapterUrl = "ws://127.0.0.1:$FabricPort/api/v1/adapters/connect"

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
  Assert-Path $Path "Protected credential"
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
  $json = $State | ConvertTo-Json -Depth 8
  [IO.File]::WriteAllText($statePath, $json, [Text.UTF8Encoding]::new($false))
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

function Stop-ExactProcess([object]$ProcessId, [string]$RequiredFragment) {
  if ($null -eq $ProcessId) { return }
  $numericId = [int]$ProcessId
  $commandLine = Get-ProcessCommandLine $numericId
  if ($null -eq $commandLine) { return }
  if (-not $commandLine.Contains($RequiredFragment, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Ignoring stale PID $numericId because it is not the expected process"
    return
  }
  Stop-Process -Id $numericId
  Wait-Process -Id $numericId -Timeout 15 -ErrorAction SilentlyContinue
}

function Wait-Until(
  [scriptblock]$Condition,
  [string]$FailureMessage,
  [int]$TimeoutSeconds = 30
) {
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
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

function Start-HiddenProcess(
  [string]$Executable,
  [string[]]$Arguments,
  [string]$WorkingDirectory,
  [string]$LogPrefix,
  [hashtable]$Environment = @{}
) {
  $parameters = @{
    FilePath = $Executable
    ArgumentList = $Arguments
    WorkingDirectory = $WorkingDirectory
    WindowStyle = "Hidden"
    RedirectStandardOutput = (Join-Path $logRoot "$LogPrefix.stdout.log")
    RedirectStandardError = (Join-Path $logRoot "$LogPrefix.stderr.log")
    PassThru = $true
  }
  if ($Environment.Count -gt 0) { $parameters.Environment = $Environment }
  return Start-Process @parameters
}

function Show-Preflight {
  Assert-Path $repositoryRoot "CIT repository"
  Assert-Path $ExternalRepositoryRoot "Upstream RoboMaster/Leap repository"
  Assert-Path $ExternalPython "External RoboMaster Python"
  foreach ($name in @("git", "uv", "pnpm.cmd")) {
    Write-Host "PASS tool $name -> $(Resolve-Executable $name)"
  }
  $revision = (& (Resolve-Executable "git") -C $ExternalRepositoryRoot rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0 -or $revision -ne $expectedRevision) {
    throw "Upstream checkout must be pinned to $expectedRevision; found $revision"
  }
  Write-Host "PASS upstream revision $revision"
  & $ExternalPython -c "from robomaster_gesture.robot_adapter import CommandPump, DryRunRobot; print('PASS upstream Python imports')" 2>$null
  if ($LASTEXITCODE -ne 0) {
    # The module is found through the checkout root, not an installed wheel.
    $environmentPath = $env:PYTHONPATH
    try {
      $env:PYTHONPATH = $ExternalRepositoryRoot
      & $ExternalPython -c "from robomaster_gesture.robot_adapter import CommandPump, DryRunRobot; print('PASS upstream Python imports')"
      if ($LASTEXITCODE -ne 0) { throw "External Python cannot import the upstream package" }
    } finally {
      $env:PYTHONPATH = $environmentPath
    }
  }
  if ($Live) {
    Assert-Path $BridgeDll "Leap bridge DLL"
    $leapCDll = Join-Path (Split-Path $BridgeDll -Parent) "LeapC.dll"
    Assert-Path $leapCDll "LeapC runtime DLL beside the bridge"
    $leapService = Get-Service -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match 'Leap|Ultraleap' -or $_.DisplayName -match 'Leap|Ultraleap' } |
      Select-Object -First 1
    if ($null -eq $leapService -or $leapService.Status -ne "Running") {
      throw "The Ultraleap tracking service is not running"
    }
    Write-Host "PASS Ultraleap service $($leapService.DisplayName) is running"
    if (-not $FleetInputOnly -and $RobotTransport -eq "sdk") {
      & $ExternalPython -c "import cv2, robomaster; print('PASS DJI SDK and OpenCV camera imports')"
      if ($LASTEXITCODE -ne 0) {
        throw "The DJI RoboMaster SDK or OpenCV camera dependency is unavailable"
      }
    } elseif (-not $FleetInputOnly -and $env:OS -ne "Windows_NT") {
      throw "The stock S1 app transport is Windows-only"
    }
    Write-Host $(if ($FleetInputOnly) { "PASS Leap input-only mode; no RoboMaster process or motor capability will start" } else { "PASS LIVE was explicitly selected; Fabric will still require arm then start" })
  } else {
    Write-Host "PASS simulation mode: demo input and upstream DryRunRobot; no motor command can leave this machine"
    if (-not (Test-Path -LiteralPath $BridgeDll)) {
      Write-Host "INFO Leap bridge DLL is absent; this does not block simulation"
    }
  }
  $listener = Get-ListeningProcessId $FabricPort
  Write-Host $(if ($null -eq $listener) { "PASS Fabric port $FabricPort is available" } else { "INFO Fabric port $FabricPort is already in use" })
  if ($SharedFabricRoot) {
    Assert-Path $bootstrapSecretPath "Shared Fabric credential; start the unified Fabric console first"
    Write-Host "PASS shared Fabric root $SharedFabricRoot"
  }
}

function Build-Systems {
  if ($SkipBuild) { return }
  Invoke-External `
    (Resolve-Executable "uv") `
    @("sync", "--all-packages", "--frozen", "--inexact") `
    $repositoryRoot
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

function Start-Fabric([hashtable]$State, [string]$BootstrapCredential) {
  $listenerId = Get-ListeningProcessId $FabricPort
  if ($null -ne $listenerId) {
    try {
      $health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 5
      if ($Live -and $health.physicalActuation -ne "enabled") {
        throw "Existing Fabric physical mode is $($health.physicalActuation); live hardware requires enabled"
      }
      $null = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/auth/whoami" -Credential $BootstrapCredential
    } catch {
      throw "Port $FabricPort is not the matching CIT Fabric instance: $($_.Exception.Message)"
    }
    $ownedExisting = (
      -not $SharedFabricRoot -and
      $State.ContainsKey("fabricPid") -and
      [int]$State.fabricPid -eq $listenerId -and
      ($State.ContainsKey("fabricOwned") -and $State.fabricOwned)
    )
    $State.fabricPid = $listenerId
    $State.fabricOwned = [bool]$ownedExisting
    Save-State $State
    return
  }
  if ($SharedFabricRoot) {
    throw "The shared Fabric is not listening on port $FabricPort; start tools/hardware/interaction-fabric-console.ps1 first"
  }
  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  Assert-Path $runtimePython "CIT virtual-environment Python"
  $environment = @{
    CITXR_DATA_DIRECTORY = $runtimeDataRoot
    CITXR_PUBLIC_ORIGIN = $fabricOrigin
    CITXR_ALLOWED_HOSTS = "127.0.0.1,localhost"
    CITXR_FABRIC_BOOTSTRAP_TOKEN = $BootstrapCredential
    CITXR_ALLOW_PHYSICAL_FABRIC = if ($Live) { "true" } else { "false" }
  }
  $process = Start-HiddenProcess `
    -Executable $runtimePython `
    -Arguments @(
      "-m", "uvicorn", "cit_runtime.fabric_service:create_persistent_fabric_app", "--factory",
      "--host", "127.0.0.1", "--port", [string]$FabricPort
    ) `
    -WorkingDirectory $repositoryRoot `
    -LogPrefix "cit-fabric" `
    -Environment $environment
  $State.fabricLauncherPid = $process.Id
  $State.fabricOwned = $true
  Save-State $State
  Wait-Until {
    try {
      $null = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/auth/whoami" -Credential $BootstrapCredential
      return $true
    } catch { return $false }
  } "CIT Fabric did not become ready" 45
  $State.fabricPid = Get-ListeningProcessId $FabricPort
  Save-State $State
}

function New-FabricSession([hashtable]$State, [string]$BootstrapCredential) {
  if ($FabricSessionId) {
    $session = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/sessions/$FabricSessionId" -Credential $BootstrapCredential
    if ([string]$session.coursePackId -ne "device-monitoring") {
      throw "FabricSessionId must identify the shared device-monitoring session"
    }
    if ([string]$session.siteId -ne $SiteId -or [string]$session.roomId -ne $RoomId) {
      throw "FabricSessionId does not belong to the requested CIT site and room"
    }
    if ([string]$session.state -in @("stopped", "emergency_stopped", "failed")) {
      throw "FabricSessionId is no longer available for Leap input attachment"
    }
    $State.sessionId = $FabricSessionId
    $State.fleetInputOnly = [bool]$FleetInputOnly
    Save-State $State
    return $session
  }
  $session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions" -Credential $BootstrapCredential -Body @{
    coursePackId = "gesture-ground-robot"
    coursePackVersion = "1.0.0"
    siteId = $SiteId
    roomId = $RoomId
    mode = if ($Live) { "physical" } else { "simulation" }
  }
  $State.sessionId = $session.sessionId
  $State.fleetInputOnly = $false
  Save-State $State
  return $session
}

function New-AdapterCredential(
  [hashtable]$State,
  [string]$BootstrapCredential,
  [string]$SessionId,
  [string]$PluginId,
  [string]$IdentityPrefix,
  [string]$SecretPath
) {
  $identityId = "$IdentityPrefix-$($SessionId.Substring(0, [Math]::Min(16, $SessionId.Length)))"
  $permissions = @("fabric.adapters.connect", "fabric.events.publish", "fabric.nodes.write")
  if ($PluginId -eq "cit.robomaster-s1") { $permissions += "fabric.media.publish" }
  $response = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/auth/identities" -Credential $BootstrapCredential -Body @{
    identityId = $identityId
    actorType = "adapter"
    roles = @("plugin.$PluginId")
    permissions = $permissions
    siteId = $SiteId
    roomId = $RoomId
    sessionId = $SessionId
    ttlSeconds = 86400
  }
  Save-ProtectedSecret $SecretPath ([string]$response.token)
  Save-State $State
  return [string]$response.token
}

function Start-Adapter(
  [hashtable]$State,
  [string]$LeapCredential,
  [string]$RobotCredential,
  [string]$SessionId
) {
  foreach ($path in @($activationPath, $leapStopPath)) {
    if (Test-Path -LiteralPath $path) { [IO.File]::Delete($path) }
  }
  if ($FleetInputOnly) {
    if ($State.ContainsKey("robotAdapterPid") -or $State.ContainsKey("leapAdapterPid")) {
      # Removing the activation file asks the owned robot bridge to execute its
      # bounded stop before process replacement. Do not race that watchdog.
      Start-Sleep -Milliseconds 1200
    }
    Stop-ExactProcess $(if ($State.ContainsKey("robotAdapterPid")) { $State.robotAdapterPid } else { $null }) "cit_robomaster_leap.robot_main"
    Stop-ExactProcess $(if ($State.ContainsKey("leapAdapterPid")) { $State.leapAdapterPid } else { $null }) "cit_robomaster_leap.leap_main"
    $State.Remove("robotAdapterPid")
    $State.Remove("leapAdapterPid")
  }
  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  $commonArguments = @(
    "--adapter-url", $fabricAdapterUrl,
    "--fabric-origin", $fabricOrigin,
    "--session-id", $SessionId,
    "--site-id", $SiteId,
    "--room-id", $RoomId,
    "--host-id", $HostId,
    "--activation-file", $activationPath,
    "--repository", $ExternalRepositoryRoot,
    "--external-python", $ExternalPython,
    "--max-speed", $MaxSpeed.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--max-yaw", $MaxYaw.ToString([Globalization.CultureInfo]::InvariantCulture)
  )
  $expectedNodeIds = @($LeapNodeId)
  if (-not $FleetInputOnly) {
    $robotArguments = @(
      "-m", "cit_robomaster_leap.robot_main"
    ) + $commonArguments + @(
      "--node-id", $RobotNodeId,
      "--robot-mode", $(if ($Live) { $RobotTransport } else { "dry-run" }),
      "--connection", $Connection,
      "--protocol", $Protocol,
      "--publish-camera"
    )
    if ($RobotIp) { $robotArguments += @("--robot-ip", $RobotIp) }
    if ($LocalIp) { $robotArguments += @("--local-ip", $LocalIp) }
    if ($SerialNumber) { $robotArguments += @("--serial-number", $SerialNumber) }
    $robotProcess = Start-HiddenProcess `
      -Executable $runtimePython `
      -Arguments $robotArguments `
      -WorkingDirectory $repositoryRoot `
      -LogPrefix "robomaster-adapter" `
      -Environment @{ CIT_FABRIC_ADAPTER_TOKEN = $RobotCredential }
    $State.robotAdapterPid = $robotProcess.Id
    $expectedNodeIds += $RobotNodeId
  }
  $leapArguments = @(
    "-m", "cit_robomaster_leap.leap_main"
  ) + $commonArguments + @(
    "--node-id", $LeapNodeId,
    "--input-mode", $(if ($Live) { "leap" } else { "demo" }),
    "--hand", $Hand,
    "--stop-file", $leapStopPath
  )
  if ($Live) { $leapArguments += @("--bridge-dll", $BridgeDll) }
  if ($InvertStrafe) { $leapArguments += "--invert-strafe" }
  if ($InvertYaw) { $leapArguments += "--invert-yaw" }
  $leapProcess = Start-HiddenProcess `
    -Executable $runtimePython `
    -Arguments $leapArguments `
    -WorkingDirectory $repositoryRoot `
    -LogPrefix "leap-adapter" `
    -Environment @{ CIT_FABRIC_ADAPTER_TOKEN = $LeapCredential }
  $State.leapAdapterPid = $leapProcess.Id
  Save-State $State
  Wait-Until {
    try {
      $nodes = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential (Read-ProtectedSecret $bootstrapSecretPath)))
      $connected = @($nodes | Where-Object { $_.nodeId -in $expectedNodeIds -and $_.connectionState -eq "connected" })
      if ($connected.Count -ne $expectedNodeIds.Count) { return $false }
      if ($FleetInputOnly) {
        return @($connected | Where-Object {
            @($_.publishedCapabilities | ForEach-Object { $_.name }) -contains "interaction.intent.flight_sequence_start"
          }).Count -eq 1
      }
      return $true
    } catch { return $false }
  } "The selected independent Leap/RoboMaster adapters did not register; inspect $logRoot" 45
}

function Bind-Roles(
  [hashtable]$State,
  [string]$BootstrapCredential,
  [string]$SessionId
) {
  if ($FleetInputOnly) {
    $session = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId" -Credential $BootstrapCredential
    $roleBindings = @(Expand-Sequence $session.roleBindings)
    $existingRole = @($roleBindings | Where-Object {
        $_.nodeId -eq $LeapNodeId -and $_.role -like "fleet_sequence_input_*"
      } | Select-Object -First 1)
    $occupiedRoles = @($roleBindings | ForEach-Object { [string]$_.role })
    $role = if ($existingRole.Count -gt 0) {
      [string]$existingRole[0].role
    } else {
      @(1..4 | ForEach-Object { "fleet_sequence_input_$_" } | Where-Object {
          $_ -notin $occupiedRoles
        } | Select-Object -First 1)[0]
    }
    if (-not $role) { throw "No free fleet input role is available for Leap Motion" }
    if ($existingRole.Count -eq 0) {
      $null = Invoke-JsonApi -Method PUT -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId/roles/$role" -Credential $BootstrapCredential -Body @{
        nodeId = $LeapNodeId
      }
    }
    $State.fleetInputRole = $role
    $State.fleetInputOnly = $true
    Save-State $State
    return Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId" -Credential $BootstrapCredential
  }
  foreach ($binding in @(
      @{ role = "gesture_input"; nodeId = $LeapNodeId },
      @{ role = "student_robot"; nodeId = $RobotNodeId }
    )) {
    $null = Invoke-JsonApi -Method PUT -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId/roles/$($binding.role)" -Credential $BootstrapCredential -Body @{
      nodeId = $binding.nodeId
    }
  }
  return Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId" -Credential $BootstrapCredential
}

function Bind-And-Start(
  [hashtable]$State,
  [string]$BootstrapCredential,
  [string]$SessionId
) {
  $null = Bind-Roles $State $BootstrapCredential $SessionId
  if ($Live) {
    $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId/arm" -Credential $BootstrapCredential
  }
  $session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$SessionId/start" -Credential $BootstrapCredential
  [IO.File]::WriteAllText($activationPath, "active`n", [Text.Encoding]::ASCII)
  $State.live = [bool]$Live
  $State.connectOnly = $false
  $State.inputActivatedAt = [DateTimeOffset]::UtcNow.ToString('o')
  Save-State $State
  return $session
}

function Show-Status([hashtable]$State, [string]$BootstrapCredential) {
  Write-Host "Fabric: $fabricOrigin"
  Write-Host "Fabric ownership: $(if ($SharedFabricRoot) { "shared ($SharedFabricRoot)" } elseif ($State.ContainsKey('fabricOwned') -and $State.fabricOwned) { 'standalone launcher' } else { 'external or unknown' })"
  Write-Host "Upstream: $ExternalRepositoryRoot @ $expectedRevision"
  $modeLabel = if ($State.ContainsKey('connectOnly') -and $State.connectOnly) {
    "LIVE physical (connected and disarmed)"
  } elseif ($State.ContainsKey('live') -and $State.live) {
    "LIVE physical"
  } else {
    "simulation"
  }
  Write-Host "Mode: $modeLabel"
  Write-Host "Fabric PID: $(if ($State.ContainsKey('fabricPid')) { $State.fabricPid } else { 'not recorded' })"
  Write-Host "Adapter PID: $(if ($State.ContainsKey('adapterPid')) { $State.adapterPid } else { 'not recorded' })"
  Write-Host "Session: $(if ($State.ContainsKey('sessionId')) { $State.sessionId } else { 'not created' })"
  if ($BootstrapCredential -and (Get-ListeningProcessId $FabricPort)) {
    $health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 5
    Write-Host "Physical actuation: $($health.physicalActuation)"
    $nodes = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential $BootstrapCredential))
    foreach ($node in $nodes | Where-Object { $_.nodeId -in @($LeapNodeId, $RobotNodeId) }) {
      Write-Host "Node: $($node.displayName) [$($node.connectionState)/$($node.healthState)]"
    }
  }
  Write-Host "Logs: $logRoot"
}

function Show-Verification([hashtable]$State, [string]$BootstrapCredential) {
  if (-not $State.ContainsKey("sessionId")) { throw "No RoboMaster/Leap session exists" }
  $sessionId = [string]$State.sessionId
  $events = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/events?sessionId=$sessionId&limit=500" -Credential $BootstrapCredential))
  $lifecycle = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/commands/lifecycle?limit=500" -Credential $BootstrapCredential))
  $gestures = @($events | Where-Object { $_.event.topic -eq "interaction.gesture.velocity" })
  $robotEvents = @($events | Where-Object { $_.event.topic -eq "telemetry.motion.commanded" })
  $succeeded = @($lifecycle | Where-Object {
      $_.lifecycle.sessionId -eq $sessionId -and
      $_.lifecycle.stage -eq "SUCCEEDED" -and
      $_.lifecycle.targetNodeId -eq $RobotNodeId
    })
  Write-Host "Gesture events: $($gestures.Count)"
  Write-Host "Robot command events: $($robotEvents.Count)"
  Write-Host "Succeeded robot commands: $($succeeded.Count)"
  if ($gestures.Count -ge 1 -and $robotEvents.Count -ge 1 -and $succeeded.Count -ge 1) {
    Write-Host "PASS gesture -> Fabric flow -> bounded robot adapter lifecycle is recorded"
  } else {
    Write-Host $(if ($Live) { "PENDING make the open-hand then pinch gesture while holding the instructor dead-man policy" } else { "PENDING the simulation pulse has not completed; inspect adapter logs" })
  }
}

function Stop-Test([hashtable]$State, [string]$BootstrapCredential) {
  if (Test-Path -LiteralPath $activationPath) { [IO.File]::Delete($activationPath) }
  if ($BootstrapCredential -and (Get-ListeningProcessId $FabricPort)) {
    try {
      if ($State.ContainsKey("fabricOwned") -and $State.fabricOwned) {
        $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/safety/stop-all" -Credential $BootstrapCredential
      } elseif (
        -not ($State.ContainsKey("fleetInputOnly") -and $State.fleetInputOnly) -and
        $State.ContainsKey("sessionId") -and
        $State.sessionId
      ) {
        $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$($State.sessionId)/stop" -Credential $BootstrapCredential
      }
    } catch {
      Write-Warning "Fabric session/global stop failed: $($_.Exception.Message)"
    }
  }
  Start-Sleep -Milliseconds 1200
  Stop-ExactProcess $(if ($State.ContainsKey("leapAdapterPid")) { $State.leapAdapterPid } else { $null }) "cit_robomaster_leap.leap_main"
  Stop-ExactProcess $(if ($State.ContainsKey("robotAdapterPid")) { $State.robotAdapterPid } else { $null }) "cit_robomaster_leap.robot_main"
  # Compatibility with state created before independent process migration.
  Stop-ExactProcess $(if ($State.ContainsKey("adapterPid")) { $State.adapterPid } else { $null }) "cit_robomaster_leap"
  if ($State.ContainsKey("fabricOwned") -and $State.fabricOwned) {
    $processIds = @()
    if ($State.ContainsKey("fabricPid")) { $processIds += $State.fabricPid }
    if ($State.ContainsKey("fabricLauncherPid")) { $processIds += $State.fabricLauncherPid }
    foreach ($processId in $processIds | Select-Object -Unique) {
      Stop-ExactProcess $processId "cit_runtime.fabric_service:create_persistent_fabric_app"
    }
  }
  Write-Host "Stopped adapter-owned processes. Runtime data and DPAPI credentials remain at $StateRoot."
}

if ($Mode -eq "Preflight") {
  Show-Preflight
  exit 0
}

$state = Load-State
$bootstrap = if (Test-Path -LiteralPath $bootstrapSecretPath) {
  Read-ProtectedSecret $bootstrapSecretPath
} else { "" }

if ($Mode -eq "Status") {
  Show-Status $state $bootstrap
  exit 0
}
if ($Mode -eq "Verify") {
  Show-Verification $state $bootstrap
  exit 0
}
if ($Mode -eq "CopyCredential") {
  if (-not $bootstrap) {
    throw "No Fabric UI credential exists; start the hardware stack first"
  }
  Set-Clipboard -Value $bootstrap
  Write-Host "Copied the local Fabric credential to the Windows clipboard without printing it."
  Write-Host "Paste it into the Fabric UI, connect, then clear the clipboard with: Set-Clipboard -Value ''"
  exit 0
}
if ($Mode -eq "Stop") {
  Stop-Test $state $bootstrap
  exit 0
}

New-Item -ItemType Directory -Path $StateRoot, $secretRoot, $logRoot, $runtimeDataRoot -Force | Out-Null
Show-Preflight
Build-Systems
$bootstrap = if ($SharedFabricRoot) {
  Read-ProtectedSecret $bootstrapSecretPath
} else {
  Ensure-BootstrapCredential
}
Start-Fabric $state $bootstrap
$session = New-FabricSession $state $bootstrap
$leapCredential = New-AdapterCredential $state $bootstrap $session.sessionId "cit.leap-motion" "cit-leap" $leapAdapterSecretPath
$robotCredential = if ($FleetInputOnly) {
  ""
} else {
  New-AdapterCredential $state $bootstrap $session.sessionId "cit.robomaster-s1" "cit-robot" $robotAdapterSecretPath
}
try {
  Start-Adapter $state $leapCredential $robotCredential $session.sessionId
  if ($FleetInputOnly) {
    $active = Bind-Roles $state $bootstrap $session.sessionId
    [IO.File]::WriteAllText($activationPath, "active`n", [Text.Encoding]::ASCII)
    $state.live = $true
    $state.connectOnly = $false
    $state.inputActivatedAt = [DateTimeOffset]::UtcNow.ToString('o')
    Save-State $state
  } elseif ($ConnectOnly) {
    $active = Bind-Roles $state $bootstrap $session.sessionId
    $state.live = $true
    $state.connectOnly = $true
    $state.Remove("inputActivatedAt")
    Save-State $state
  } else {
    $active = Bind-And-Start $state $bootstrap $session.sessionId
  }
} catch {
  Write-Warning "Startup failed; applying the local emergency-stop path."
  Stop-Test $state $bootstrap
  throw
}

Write-Host "READY session $($active.sessionId) [$($active.state)]"
Write-Host "UI $fabricOrigin/fabric"
Write-Host "Classroom controls open with automatic local sign-in."
Write-Host $(if ($FleetInputOnly) { "FLEET INPUT ONLY: open hand then pinch publishes one start intent; no RoboMaster process was started and the fleet still requires tutor arming." } elseif ($ConnectOnly) { "CONNECTED AND DISARMED: no activation file was created and no movement command can run until the tutor starts the lesson." } elseif ($Live) { "LIVE: robot is armed; release pinch or use Emergency stop immediately to halt." } else { "SIMULATION: a bounded demo pulse and stop are running through the upstream DryRunRobot." })
if (-not $NoOpenConsole) {
  $consoleStateRoot = if ($SharedFabricRoot) { $SharedFabricRoot } else { $StateRoot }
  & (Join-Path $repositoryRoot "tools\hardware\interaction-fabric-console.ps1") `
    -Mode Open `
    -FabricPort $FabricPort `
    -StateRoot $consoleStateRoot
}

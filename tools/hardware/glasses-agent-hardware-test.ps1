#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Preflight", "Start", "Status", "Verify", "Stop")]
  [string]$Mode = "Start",
  [string]$AgentMeshRoot = "",
  [string]$StateRoot = "",
  [ValidateRange(1, 65535)]
  [int]$FabricPort = 8766,
  [string]$AgentMeshHubUrl = "http://127.0.0.1:7342",
  [string]$HubTaskName = "AgentMesh Hub",
  [string]$NodeTaskName = "AgentMesh Node",
  [string]$BridgeDeviceId = "cit-fabric-bridge-local",
  [string]$SiteId = "cit-local",
  [string]$RoomId = "hardware-lab",
  [string]$BridgeHostId = "",
  [string]$AgentMeshSessionId = "",
  [switch]$SelectMostRecentAgentSession,
  [switch]$ProvisionWearables,
  [switch]$SkipBuild,
  [switch]$NoOpenConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $AgentMeshRoot) {
  $AgentMeshRoot = Join-Path (Split-Path $repositoryRoot -Parent) "glasses2CLI"
}
$AgentMeshRoot = [IO.Path]::GetFullPath($AgentMeshRoot)
if (-not $StateRoot) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\glasses-hardware-test"
}
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
if (-not $BridgeHostId) {
  $BridgeHostId = "$($env:COMPUTERNAME.ToLowerInvariant())-windows"
}

$identifierPattern = '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
foreach ($entry in @{
    BridgeDeviceId = $BridgeDeviceId
    SiteId = $SiteId
    RoomId = $RoomId
    BridgeHostId = $BridgeHostId
  }.GetEnumerator()) {
  if ($entry.Value -notmatch $identifierPattern) {
    throw "$($entry.Key) must be a CIT identifier"
  }
}
if ($AgentMeshSessionId -and $AgentMeshSessionId -notmatch $identifierPattern) {
  throw "AgentMeshSessionId must be an Agent Mesh identifier"
}
if ($AgentMeshHubUrl -ne "http://127.0.0.1:7342") {
  throw "This hardware-test launcher currently requires the loopback Agent Mesh Hub URL"
}

$statePath = Join-Path $StateRoot "state.json"
$secretRoot = Join-Path $StateRoot "secrets"
$logRoot = Join-Path $StateRoot "logs"
$runtimeDataRoot = Join-Path $StateRoot "runtime"
$bootstrapSecretPath = Join-Path $secretRoot "fabric-bootstrap.dpapi"
$adapterSecretPath = Join-Path $secretRoot "fabric-adapter.dpapi"
$agentMeshSecretPath = Join-Path $secretRoot "agent-mesh-bridge.dpapi"
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
  $ciphertext = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
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
    throw "Refusing to stop PID $numericId because it is not the expected process"
  }
  Stop-Process -Id $numericId
  Wait-Process -Id $numericId -Timeout 15 -ErrorAction SilentlyContinue
}

function Wait-Until([scriptblock]$Condition, [string]$FailureMessage, [int]$TimeoutSeconds = 30) {
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

function Test-JsonApi([string]$Uri, [string]$Credential) {
  try {
    $null = Invoke-JsonApi -Method GET -Uri $Uri -Credential $Credential
    return $true
  } catch {
    return $false
  }
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
  $stdout = Join-Path $logRoot "$LogPrefix.stdout.log"
  $stderr = Join-Path $logRoot "$LogPrefix.stderr.log"
  $parameters = @{
    FilePath = $Executable
    ArgumentList = $Arguments
    WorkingDirectory = $WorkingDirectory
    WindowStyle = "Hidden"
    RedirectStandardOutput = $stdout
    RedirectStandardError = $stderr
    PassThru = $true
  }
  if ($Environment.Count -gt 0) { $parameters.Environment = $Environment }
  return Start-Process @parameters
}

function Show-Preflight {
  Assert-Path $repositoryRoot "CIT repository"
  Assert-Path $AgentMeshRoot "Agent Mesh repository"
  foreach ($name in @("node", "pnpm.cmd", "uv", "adb")) {
    $path = Resolve-Executable $name
    Write-Host "PASS tool $name -> $path"
  }
  $hub = Get-ListeningProcessId 7342
  Write-Host $(if ($null -eq $hub) { "BLOCKED Agent Mesh Hub port 7342 is closed" } else { "PASS Agent Mesh Hub listens on 7342" })
  $fabric = Get-ListeningProcessId $FabricPort
  Write-Host $(if ($null -eq $fabric) { "PASS Fabric port $FabricPort is available" } else { "INFO Fabric port $FabricPort is already in use" })
  $brain = Get-ListeningProcessId 8765
  if ($null -ne $brain) { Write-Host "PASS preserved existing port 8765 listener (Fabric will use $FabricPort)" }
  $adbLines = & (Resolve-Executable "adb") devices
  $attached = @($adbLines | Select-Object -Skip 1 | Where-Object { $_ -match "\tdevice$" })
  Write-Host $(if ($attached.Count -eq 0) { "INFO no authorized Android device is attached; existing provisioned glasses may still be used" } else { "PASS $($attached.Count) authorized Android device(s) attached" })
  $task = Get-ScheduledTask -TaskName $HubTaskName -ErrorAction SilentlyContinue
  Write-Host $(if ($null -eq $task) { "BLOCKED scheduled task '$HubTaskName' was not found" } else { "PASS scheduled task '$HubTaskName' exists ($($task.State))" })
  $nodeTask = Get-ScheduledTask -TaskName $NodeTaskName -ErrorAction SilentlyContinue
  Write-Host $(if ($null -eq $nodeTask) { "BLOCKED scheduled task '$NodeTaskName' was not found" } else { "PASS scheduled task '$NodeTaskName' exists ($($nodeTask.State))" })
  Write-Host "PASS physical Fabric actuation remains disabled by this launcher"
}

function Build-Systems {
  if ($SkipBuild) { return }
  $pnpm = Resolve-Executable "pnpm.cmd"
  $uv = Resolve-Executable "uv"
  Invoke-External $pnpm @("install", "--frozen-lockfile") $AgentMeshRoot
  Invoke-External $pnpm @("build") $AgentMeshRoot
  Invoke-External $pnpm @("install", "--frozen-lockfile") $repositoryRoot
  Invoke-External $uv @("sync", "--all-packages", "--frozen") $repositoryRoot
  Invoke-External $pnpm @("build") $repositoryRoot
}

function Ensure-AgentMeshCredential([hashtable]$State) {
  if (Test-Path -LiteralPath $agentMeshSecretPath) {
    return Read-ProtectedSecret $agentMeshSecretPath
  }
  $bootstrapPath = Join-Path $secretRoot "agent-mesh-$([Guid]::NewGuid().ToString('N')).token"
  try {
    Invoke-External (Resolve-Executable "pnpm.cmd") @(
      "--silent", "agentmesh", "hub", "issue-device-token",
      "--device-id", $BridgeDeviceId,
      "--name", "CIT Fabric bridge",
      "--kind", "test_client",
      "--scopes", "read",
      "--token-file", $bootstrapPath,
      "--hub", $AgentMeshHubUrl
    ) $AgentMeshRoot
    $credential = [IO.File]::ReadAllText($bootstrapPath, [Text.Encoding]::UTF8).Trim()
    Save-ProtectedSecret $agentMeshSecretPath $credential
    $State.bridgeDeviceId = $BridgeDeviceId
    Save-State $State
    return $credential
  } finally {
    if (Test-Path -LiteralPath $bootstrapPath) { [IO.File]::Delete($bootstrapPath) }
  }
}

function Start-MirrorHub([hashtable]$State, [string]$AgentMeshCredential) {
  $listenerId = Get-ListeningProcessId 7342
  if ($null -ne $listenerId) {
    $commandLine = Get-ProcessCommandLine $listenerId
    if ($commandLine -and $commandLine.Contains("--cit-fabric-bridge-device $BridgeDeviceId", [StringComparison]::OrdinalIgnoreCase)) {
      $State.hubPid = $listenerId
      if (-not ($State.ContainsKey("hubTransient") -and $State.hubTransient)) {
        $State.hubTransient = $false
      }
      Save-State $State
      return
    }
  }

  $task = Get-ScheduledTask -TaskName $HubTaskName -ErrorAction Stop
  $action = @($task.Actions)
  if ($action.Count -ne 1 -or -not ([string]$action[0].Arguments).Contains("hub start", [StringComparison]::OrdinalIgnoreCase)) {
    throw "The Hub task does not contain one recognizable hub-start action"
  }
  $State.hubTaskWasRunning = ([string]$task.State -eq "Running")
  if ([string]$task.State -eq "Running") {
    Stop-ScheduledTask -TaskName $HubTaskName
    Wait-Until { $null -eq (Get-ListeningProcessId 7342) } "The scheduled Hub did not release port 7342"
  } elseif ($null -ne $listenerId) {
    throw "Port 7342 is owned by a process outside the scheduled Hub task"
  }

  try {
    $arguments = @(([string]$action[0].Arguments) -split ' ')
    $arguments += @("--cit-fabric-bridge-device", $BridgeDeviceId)
    $hubProcess = Start-HiddenProcess `
      -Executable ([string]$action[0].Execute) `
      -Arguments $arguments `
      -WorkingDirectory ([string]$action[0].WorkingDirectory) `
      -LogPrefix "agent-mesh-hub"
    $State.hubPid = $hubProcess.Id
    $State.hubTransient = $true
    Save-State $State
    Wait-Until { Test-JsonApi "$AgentMeshHubUrl/api/v1/wearables/cit-fabric/discovery" $AgentMeshCredential } "The mirror-enabled Agent Mesh Hub did not become ready" 60
  } catch {
    if ($State.hubTaskWasRunning) { Start-ScheduledTask -TaskName $HubTaskName }
    throw
  }
}

function Start-AgentMeshNode([hashtable]$State, [string]$AgentMeshCredential) {
  $task = Get-ScheduledTask -TaskName $NodeTaskName -ErrorAction Stop
  if ([string]$task.State -ne "Running") {
    $State.nodeTaskWasRunning = $false
    $State.nodeTaskStartedByLauncher = $true
    Save-State $State
    Start-ScheduledTask -TaskName $NodeTaskName
    Wait-Until { [string](Get-ScheduledTask -TaskName $NodeTaskName).State -eq "Running" } "The Agent Mesh Node task did not start"
  } elseif (-not ($State.ContainsKey("nodeTaskStartedByLauncher") -and $State.nodeTaskStartedByLauncher)) {
    $State.nodeTaskWasRunning = $true
    $State.nodeTaskStartedByLauncher = $false
    Save-State $State
  }
  Wait-Until {
    try {
      $discovery = Invoke-JsonApi -Method GET -Uri "$AgentMeshHubUrl/api/v1/wearables/cit-fabric/discovery" -Credential $AgentMeshCredential
      return @(Expand-Sequence $discovery.sessions | Where-Object { $_.controlStatus -in @("managed", "observed") }).Count -gt 0
    } catch {
      return $false
    }
  } "The Agent Mesh Node did not publish a controllable Claude or Codex session" 60
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
    if (-not (Test-JsonApi "$fabricOrigin/api/v1/fabric/auth/whoami" $BootstrapCredential)) {
      throw "Port $FabricPort is occupied by a process that is not this CIT Fabric instance"
    }
    $State.fabricPid = $listenerId
    Save-State $State
    return
  }
  $environment = @{
    CITXR_DATA_DIRECTORY = $runtimeDataRoot
    CITXR_PUBLIC_ORIGIN = $fabricOrigin
    CITXR_ALLOWED_HOSTS = "127.0.0.1,localhost"
    CITXR_FABRIC_BOOTSTRAP_TOKEN = $BootstrapCredential
  }
  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  Assert-Path $runtimePython "CIT virtual-environment Python"
  $fabricProcess = Start-HiddenProcess `
    -Executable $runtimePython `
    -Arguments @(
        "-m", "uvicorn", "cit_runtime.fabric_service:create_persistent_fabric_app", "--factory",
      "--host", "127.0.0.1", "--port", [string]$FabricPort
    ) `
    -WorkingDirectory $repositoryRoot `
    -LogPrefix "cit-fabric" `
    -Environment $environment
  $State.fabricPid = $fabricProcess.Id
  Save-State $State
  Wait-Until { Test-JsonApi "$fabricOrigin/api/v1/fabric/auth/whoami" $BootstrapCredential } "CIT Fabric did not become ready"
}

function Ensure-FabricSession([hashtable]$State, [string]$BootstrapCredential) {
  if ($State.ContainsKey("sessionId") -and $State.sessionId) {
    try {
      $existing = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/sessions/$($State.sessionId)" -Credential $BootstrapCredential
      if ($existing.state -notin @("stopped", "emergency_stopped", "failed")) {
        return $existing
      }
      $State.Remove("sessionId")
    } catch {
      $State.Remove("sessionId")
    }
  }
  $session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions" -Credential $BootstrapCredential -Body @{
    coursePackId = "glasses-agent-control"
    coursePackVersion = "1.0.0"
    siteId = $SiteId
    roomId = $RoomId
    mode = "simulation"
  }
  $State.sessionId = $session.sessionId
  foreach ($key in @("agentNodeId", "agentMeshSessionId", "wearableNodeId")) {
    $State.Remove($key)
  }
  Save-State $State
  return $session
}

function Ensure-AdapterCredential(
  [hashtable]$State,
  [string]$BootstrapCredential,
  [string]$SessionId
) {
  if (
    (Test-Path -LiteralPath $adapterSecretPath) -and
    $State.ContainsKey("adapterSessionId") -and
    $State.adapterSessionId -eq $SessionId
  ) {
    $credential = Read-ProtectedSecret $adapterSecretPath
    if (Test-JsonApi "$fabricOrigin/api/v1/fabric/auth/whoami" $credential) {
      return $credential
    }
  }
  $identityId = "cit-agent-mesh-$($SessionId.Substring(0, [Math]::Min(16, $SessionId.Length)))"
  $response = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/auth/identities" -Credential $BootstrapCredential -Body @{
    identityId = $identityId
    actorType = "adapter"
    roles = @("plugin.cit.agent-mesh-bridge")
    permissions = @("fabric.adapters.connect", "fabric.events.publish", "fabric.nodes.write")
    siteId = $SiteId
    roomId = $RoomId
    sessionId = $SessionId
    ttlSeconds = 86400
  }
  Save-ProtectedSecret $adapterSecretPath ([string]$response.token)
  $State.adapterIdentityId = $identityId
  $State.adapterSessionId = $SessionId
  Save-State $State
  return [string]$response.token
}

function Start-Bridge(
  [hashtable]$State,
  [string]$AdapterCredential,
  [string]$AgentMeshCredential,
  [string]$SessionId
) {
  if ($State.ContainsKey("bridgePid") -and $null -ne (Get-ProcessCommandLine ([int]$State.bridgePid))) {
    if (-not ($AgentMeshSessionId -or $SelectMostRecentAgentSession)) { return }
    Stop-ExactProcess $State.bridgePid "agent-mesh-bridge/dist/main.js"
    $State.Remove("bridgePid")
    Save-State $State
  }
  $bridgeDatabasePath = Join-Path $StateRoot "agent-mesh-bridge-$SessionId.sqlite3"
  $environment = @{
    CIT_FABRIC_ADAPTER_URL = $fabricAdapterUrl
    CIT_FABRIC_ADAPTER_TOKEN = $AdapterCredential
    CIT_FABRIC_SESSION_ID = $SessionId
    CIT_AGENT_MESH_URL = $AgentMeshHubUrl
    CIT_AGENT_MESH_DEVICE_TOKEN = $AgentMeshCredential
    CIT_BRIDGE_DATABASE_PATH = $bridgeDatabasePath
    CIT_SITE_ID = $SiteId
    CIT_ROOM_ID = $RoomId
    CIT_BRIDGE_HOST_ID = $BridgeHostId
  }
  $bridgeProcess = Start-HiddenProcess `
    -Executable (Resolve-Executable "node") `
    -Arguments @("apps/agent-mesh-bridge/dist/main.js") `
    -WorkingDirectory $repositoryRoot `
    -LogPrefix "agent-mesh-bridge" `
    -Environment $environment
  $State.bridgePid = $bridgeProcess.Id
  Save-State $State
}

function Get-CapabilityNames([object]$Node, [string]$Property) {
  return @($Node.$Property | ForEach-Object { [string]$_.name })
}

function Bind-ReadyNodes([hashtable]$State, [string]$BootstrapCredential) {
  $nodes = @()
  $agentSelectionRequested = [bool]($AgentMeshSessionId -or $SelectMostRecentAgentSession)
  Wait-Until {
    try {
      $response = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes?siteId=$SiteId&roomId=$RoomId" -Credential $BootstrapCredential
      $script:nodes = @(Expand-Sequence $response)
      $registered = @($script:nodes | Where-Object { $_.pluginId -eq "cit.agent-mesh-bridge" })
      if ($registered.Count -eq 0) { return $false }
      if (-not $agentSelectionRequested) { return $true }
      $readyAgents = @($registered | Where-Object {
          (Get-CapabilityNames $_ "consumedCapabilities") -contains "agent.prompt.submit" -and
          $_.connectionState -in @("connected", "degraded") -and
          (-not $AgentMeshSessionId -or $_.metadata.agentMeshSessionId -eq $AgentMeshSessionId)
        })
      return $readyAgents.Count -gt 0
    } catch {
      return $false
    }
  } "The Agent Mesh bridge did not register a selectable Fabric agent node" 60

  $wearables = @($script:nodes | Where-Object {
      $_.pluginId -eq "cit.agent-mesh-bridge" -and
      (Get-CapabilityNames $_ "publishedCapabilities") -contains "interaction.intent.agent_prompt" -and
      $_.connectionState -eq "connected"
    } | Sort-Object lastSeenAt -Descending)
  $agents = @($script:nodes | Where-Object {
      $_.pluginId -eq "cit.agent-mesh-bridge" -and
      (Get-CapabilityNames $_ "consumedCapabilities") -contains "agent.prompt.submit" -and
      $_.connectionState -in @("connected", "degraded")
    } | Sort-Object { $_.metadata.agentMeshLastActivityAt } -Descending)

  $wearable = $wearables | Select-Object -First 1
  $agent = $null
  if ($AgentMeshSessionId) {
    $agent = $agents | Where-Object { $_.metadata.agentMeshSessionId -eq $AgentMeshSessionId } | Select-Object -First 1
    if ($null -eq $agent) { throw "No connected Fabric agent node matches AgentMeshSessionId '$AgentMeshSessionId'" }
  } elseif ($SelectMostRecentAgentSession) {
    $agent = $agents | Select-Object -First 1
  }

  if ($null -ne $agent) {
    $null = Invoke-JsonApi -Method PUT -Uri "$fabricOrigin/api/v1/fabric/sessions/$($State.sessionId)/roles/coding_agent" -Credential $BootstrapCredential -Body @{ nodeId = $agent.nodeId }
    $State.agentNodeId = $agent.nodeId
    $State.agentMeshSessionId = $agent.metadata.agentMeshSessionId
  } else {
    $State.Remove("agentNodeId")
    $State.Remove("agentMeshSessionId")
  }
  if ($null -ne $wearable) {
    $null = Invoke-JsonApi -Method PUT -Uri "$fabricOrigin/api/v1/fabric/sessions/$($State.sessionId)/roles/primary_glasses" -Credential $BootstrapCredential -Body @{ nodeId = $wearable.nodeId }
    $State.wearableNodeId = $wearable.nodeId
  } else {
    $State.Remove("wearableNodeId")
  }
  Save-State $State

  $session = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/sessions/$($State.sessionId)" -Credential $BootstrapCredential
  if ($session.state -eq "ready") {
    $session = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$($State.sessionId)/start" -Credential $BootstrapCredential
  }
  return @{
    session = $session
    wearable = $wearable
    agent = $agent
    allNodes = @($script:nodes | Where-Object { $_.pluginId -eq "cit.agent-mesh-bridge" })
  }
}

function Show-Status([hashtable]$State, [string]$BootstrapCredential = "") {
  Write-Host "State root: $StateRoot"
  Write-Host "Agent Mesh Hub: $(if ($null -eq (Get-ListeningProcessId 7342)) { 'offline' } else { 'listening' })"
  Write-Host "CIT Fabric: $(if ($null -eq (Get-ListeningProcessId $FabricPort)) { 'offline' } else { $fabricOrigin })"
  Write-Host "Physical actuation: disabled"
  if ($State.ContainsKey("sessionId")) { Write-Host "Fabric session: $($State.sessionId)" }
  if ($State.ContainsKey("agentMeshSessionId")) { Write-Host "Assigned Agent Mesh session: $($State.agentMeshSessionId)" }
  if ($BootstrapCredential -and $State.ContainsKey("sessionId") -and (Get-ListeningProcessId $FabricPort)) {
    try {
      $session = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/sessions/$($State.sessionId)" -Credential $BootstrapCredential
      Write-Host "Session state: $($session.state)"
      $response = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes?siteId=$SiteId&roomId=$RoomId" -Credential $BootstrapCredential
      $nodes = @(Expand-Sequence $response | Where-Object { $_.pluginId -eq "cit.agent-mesh-bridge" })
      foreach ($node in $nodes) {
        Write-Host "Node: $($node.displayName) [$($node.connectionState)/$($node.healthState)]"
      }
    } catch {
      Write-Host "INFO Fabric status requires a current bootstrap credential"
    }
  }
}

function Show-Verification([hashtable]$State, [string]$BootstrapCredential) {
  if (-not $BootstrapCredential) { throw "No protected Fabric bootstrap credential is available" }
  if (-not $State.ContainsKey("sessionId")) { throw "No hardware-test Fabric session exists" }
  if ($null -eq (Get-ListeningProcessId $FabricPort)) { throw "CIT Fabric is not listening on port $FabricPort" }

  $sessionId = [string]$State.sessionId
  $session = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/sessions/$sessionId" -Credential $BootstrapCredential
  $eventResponse = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/events?sessionId=$sessionId&afterSequence=0&limit=100" -Credential $BootstrapCredential
  $lifecycleResponse = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/commands/lifecycle?afterSequence=0&limit=100" -Credential $BootstrapCredential
  $events = @(Expand-Sequence $eventResponse)
  $lifecycles = @(Expand-Sequence $lifecycleResponse | Where-Object { $_.lifecycle.sessionId -eq $sessionId })
  $intents = @($events | Where-Object { $_.event.topic -eq "interaction.intent.agent_prompt" })
  $outputs = @($events | Where-Object { $_.event.topic -eq "agent.output.completed" })
  $promptSuccess = @($lifecycles | Where-Object {
      $_.lifecycle.stage -eq "SUCCEEDED" -and $_.lifecycle.code -eq "AGENT_MESH_ALREADY_DISPATCHED"
    })
  $displaySuccess = @($lifecycles | Where-Object {
      $_.lifecycle.stage -eq "SUCCEEDED" -and $_.lifecycle.code -eq "DISPLAY_ALREADY_PROJECTED"
    })

  Write-Host "Fabric session: $sessionId [$($session.state)]"
  Write-Host "Role bindings: $(@(Expand-Sequence $session.roleBindings).Count)"
  Write-Host "Canonical intent events: $($intents.Count)"
  Write-Host "Canonical completion events: $($outputs.Count)"
  Write-Host "No-duplicate prompt confirmations: $($promptSuccess.Count)"
  Write-Host "No-duplicate display confirmations: $($displaySuccess.Count)"
  if (
    $session.state -eq "active" -and
    $intents.Count -ge 1 -and
    $outputs.Count -ge 1 -and
    $promptSuccess.Count -ge 1 -and
    $displaySuccess.Count -ge 1
  ) {
    Write-Host "PASS one physical glasses-to-agent round trip is recorded without duplicate prompt or display delivery"
  } else {
    Write-Host "PENDING the physical round trip has not yet satisfied every acceptance signal"
  }
}

function Stop-Test([hashtable]$State) {
  $bootstrap = if (Test-Path -LiteralPath $bootstrapSecretPath) { Read-ProtectedSecret $bootstrapSecretPath } else { "" }
  if ($bootstrap -and $State.ContainsKey("sessionId") -and (Get-ListeningProcessId $FabricPort)) {
    try {
      $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$($State.sessionId)/stop" -Credential $bootstrap
    } catch {
      Write-Warning "Could not mark the Fabric session stopped: $($_.Exception.Message)"
    }
  }
  Stop-ExactProcess $(if ($State.ContainsKey("bridgePid")) { $State.bridgePid } else { $null }) "agent-mesh-bridge/dist/main.js"
  Stop-ExactProcess $(if ($State.ContainsKey("fabricPid")) { $State.fabricPid } else { $null }) "cit_runtime.fabric_service:create_persistent_fabric_app"
  if ($State.ContainsKey("hubTransient") -and $State.hubTransient) {
    Stop-ExactProcess $(if ($State.ContainsKey("hubPid")) { $State.hubPid } else { $null }) "--cit-fabric-bridge-device $BridgeDeviceId"
  }
  if ($State.ContainsKey("nodeTaskStartedByLauncher") -and $State.nodeTaskStartedByLauncher) {
    $nodeTask = Get-ScheduledTask -TaskName $NodeTaskName -ErrorAction SilentlyContinue
    if ($null -ne $nodeTask -and [string]$nodeTask.State -eq "Running") {
      Stop-ScheduledTask -TaskName $NodeTaskName
      Wait-Until { [string](Get-ScheduledTask -TaskName $NodeTaskName).State -eq "Ready" } "The Agent Mesh Node task did not stop"
    }
  }
  if ($State.ContainsKey("hubTaskWasRunning") -and $State.hubTaskWasRunning) {
    Start-ScheduledTask -TaskName $HubTaskName
    Wait-Until { $null -ne (Get-ListeningProcessId 7342) } "The normal Agent Mesh Hub task did not restart"
  }
  $State.stoppedAt = [DateTimeOffset]::UtcNow.ToString('o')
  Save-State $State
  Write-Host "Stopped the CIT hardware-test processes and restored the normal Agent Mesh Hub task."
}

if ($Mode -eq "Preflight") {
  Show-Preflight
  exit 0
}
if ($Mode -eq "Status") {
  $state = Load-State
  $bootstrap = if (Test-Path -LiteralPath $bootstrapSecretPath) { Read-ProtectedSecret $bootstrapSecretPath } else { "" }
  Show-Status $state $bootstrap
  exit 0
}
if ($Mode -eq "Verify") {
  $state = Load-State
  $bootstrap = if (Test-Path -LiteralPath $bootstrapSecretPath) { Read-ProtectedSecret $bootstrapSecretPath } else { "" }
  Show-Verification $state $bootstrap
  exit 0
}

New-Item -ItemType Directory -Path $StateRoot, $secretRoot, $logRoot, $runtimeDataRoot -Force | Out-Null
$state = Load-State

if ($Mode -eq "Stop") {
  Stop-Test $state
  exit 0
}

Show-Preflight
Build-Systems
if ($ProvisionWearables) {
  Invoke-External (Resolve-Executable "pnpm.cmd") @("setup:wearables") $AgentMeshRoot
}

try {
  $agentMeshCredential = Ensure-AgentMeshCredential $state
  Start-MirrorHub $state $agentMeshCredential
  Start-AgentMeshNode $state $agentMeshCredential
  $bootstrapCredential = Ensure-BootstrapCredential
  Start-Fabric $state $bootstrapCredential
  $session = Ensure-FabricSession $state $bootstrapCredential
  $adapterCredential = Ensure-AdapterCredential $state $bootstrapCredential $session.sessionId
  Start-Bridge $state $adapterCredential $agentMeshCredential $session.sessionId
  $binding = Bind-ReadyNodes $state $bootstrapCredential
} catch {
  Write-Warning "Hardware-test startup failed; restoring the normal Hub task."
  Stop-Test $state
  throw
}

Write-Host ""
Write-Host "CIT glasses hardware test is prepared."
Write-Host "Console: $fabricOrigin/fabric"
Write-Host "Fabric session: $($binding.session.sessionId) [$($binding.session.state)]"
if ($null -eq $binding.wearable) {
  Write-Host "ACTION REQUIRED: open/wear G2 or open the Meta phone bridge, wait for it to poll, then rerun this Start command."
} else {
  Write-Host "Glasses node: $($binding.wearable.displayName) [$($binding.wearable.connectionState)]"
}
if ($null -eq $binding.agent) {
  Write-Host "ACTION REQUIRED: rerun with -AgentMeshSessionId <exact-id> or -SelectMostRecentAgentSession."
  Write-Host "Available agent sessions:"
  foreach ($node in @($binding.allNodes | Where-Object { (Get-CapabilityNames $_ "consumedCapabilities") -contains "agent.prompt.submit" })) {
    Write-Host "  $($node.metadata.agentMeshSessionId)  $($node.displayName)  $($node.connectionState)"
  }
} else {
  Write-Host "Agent session: $($binding.agent.metadata.agentMeshSessionId)"
}
Write-Host "Expected safe prompt: Reply exactly CIT_HARDWARE_OK. Do not use tools or modify files."
Write-Host "Stop/rollback: pwsh -NoProfile -File `"$PSCommandPath`" -Mode Stop"
if (-not $NoOpenConsole) {
  Start-Process -FilePath "$fabricOrigin/fabric" | Out-Null
}

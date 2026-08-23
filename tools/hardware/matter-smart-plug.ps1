#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("ControllerStart", "ConfigureWifi", "Commission", "Start", "Status", "Stop")]
  [string]$Mode = "Start",
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8766,
  [ValidateRange(1024, 65535)]
  [int]$MatterPort = 5580,
  [string]$SharedFabricRoot = "",
  [string]$StateRoot = "",
  [string]$SiteId = "local-site",
  [string]$RoomId = "local-room",
  [string]$HostId = $env:COMPUTERNAME,
  [switch]$DisableBluetooth,
  [switch]$SkipBuild,
  [switch]$NoOpenConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$citStateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR"
if (-not $SharedFabricRoot) {
  $SharedFabricRoot = Join-Path $citStateRoot "interaction-fabric"
}
if (-not $StateRoot) {
  $StateRoot = Join-Path $citStateRoot "matter"
}
$siteProfilePath = Join-Path $citStateRoot "site\site.json"
if (Test-Path -LiteralPath $siteProfilePath -PathType Leaf) {
  try {
    $siteProfile = Get-Content -LiteralPath $siteProfilePath -Raw | ConvertFrom-Json -AsHashtable
    if (-not $PSBoundParameters.ContainsKey("SiteId") -and $siteProfile.siteId) {
      $SiteId = [string]$siteProfile.siteId
    }
    if (-not $PSBoundParameters.ContainsKey("RoomId") -and $siteProfile.roomId) {
      $RoomId = [string]$siteProfile.roomId
    }
  } catch {
    throw "The CIT business-site profile is invalid; run the business installer again."
  }
}
foreach ($entry in @(@("SiteId", $SiteId), @("RoomId", $RoomId), @("HostId", $HostId))) {
  if ([string]$entry[1] -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
    throw "$($entry[0]) must be a CIT identifier."
  }
}

$SharedFabricRoot = [IO.Path]::GetFullPath($SharedFabricRoot)
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$controllerStorage = Join-Path $StateRoot "controller"
$secretRoot = Join-Path $StateRoot "secrets"
$logRoot = Join-Path $StateRoot "logs"
$activationRoot = Join-Path $StateRoot "active"
$statePath = Join-Path $StateRoot "state.json"
$bootstrapSecretPath = Join-Path $SharedFabricRoot "secrets\fabric-bootstrap.dpapi"
$fabricOrigin = "http://127.0.0.1:$FabricPort"
$fabricAdapterUrl = "ws://127.0.0.1:$FabricPort/api/v1/adapters/connect"
$matterOrigin = "http://127.0.0.1:$MatterPort"
$matterServerUrl = "ws://127.0.0.1:$MatterPort/ws"
$controllerMarker = "matter-server/dist/esm/MatterServer.js"
$adapterMarker = "cit_matter_smart_plug"

function Assert-Path([string]$Path, [string]$Description) {
  if (-not (Test-Path -LiteralPath $Path)) { throw "$Description was not found at $Path" }
}

function Resolve-Executable([string]$Name) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($null -eq $command) { throw "Required executable '$Name' was not found" }
  return $command.Source
}

function Invoke-External([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory) {
  Push-Location $WorkingDirectory
  try {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable exited with code $LASTEXITCODE" }
  } finally {
    Pop-Location
  }
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
  Assert-Path $Path "Protected local credential"
  $ciphertext = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8).Trim()
  return ConvertFrom-SecretValue (ConvertTo-SecureString -String $ciphertext)
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
    ($State | ConvertTo-Json -Depth 12),
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

function Stop-ExactProcess([object]$ProcessId, [string]$Marker, [string]$Description) {
  if ($null -eq $ProcessId) { return }
  $numericId = [int]$ProcessId
  $commandLine = Get-ProcessCommandLine $numericId
  if ($null -eq $commandLine) { return }
  if (-not $commandLine.Contains($Marker, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Ignoring PID $numericId because it is not the expected $Description process."
    return
  }
  Stop-Process -Id $numericId
  Wait-Process -Id $numericId -Timeout 15 -ErrorAction SilentlyContinue
}

function Wait-Until([scriptblock]$Condition, [string]$FailureMessage, [int]$TimeoutSeconds = 45) {
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
    TimeoutSec = 15
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

function Build-Systems {
  if ($SkipBuild) { return }
  Invoke-External (Resolve-Executable "uv") @("sync", "--all-packages", "--frozen") $repositoryRoot
  Invoke-External (Resolve-Executable "pnpm.cmd") @("install", "--frozen-lockfile") $repositoryRoot
  Invoke-External (Resolve-Executable "pnpm.cmd") @("build") $repositoryRoot
}

function Test-MatterHealth {
  try {
    $health = Invoke-RestMethod -Uri "$matterOrigin/health" -TimeoutSec 2
    return $health.version -eq "1.4.0"
  } catch {
    return $false
  }
}

function Start-Controller([hashtable]$State) {
  $listenerId = Get-ListeningProcessId $MatterPort
  if ($null -ne $listenerId) {
    if (-not (Test-MatterHealth)) {
      throw "Port $MatterPort is occupied by a service that is not the pinned CIT Matter controller."
    }
    $State.controllerPid = $listenerId
    Save-State $State
    return
  }
  $node = Resolve-Executable "node"
  $controllerEntry = Join-Path $repositoryRoot "apps\matter-controller\node_modules\matter-server\dist\esm\MatterServer.js"
  Assert-Path $controllerEntry "Pinned local Matter controller"
  $controllerEnvironment = @{
    STORAGE_PATH = $controllerStorage
    PORT = [string]$MatterPort
    LISTEN_ADDRESS = "127.0.0.1"
    DEFAULT_FABRIC_LABEL = "CIT-$SiteId"
    DISABLE_OTA = "true"
    DISABLE_DASHBOARD = "true"
    DISABLE_THREAD_DIAGNOSTICS = "true"
    LOG_LEVEL = "warning"
  }
  if (-not $DisableBluetooth) {
    $controllerEnvironment.BLUETOOTH_ADAPTER = "0"
  }
  $process = Start-Process `
    -FilePath $node `
    -ArgumentList @("node_modules/matter-server/dist/esm/MatterServer.js") `
    -WorkingDirectory (Join-Path $repositoryRoot "apps\matter-controller") `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot "matter-controller.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "matter-controller.stderr.log") `
    -Environment $controllerEnvironment `
    -PassThru
  $State.controllerLauncherPid = $process.Id
  $State.bluetoothRequested = -not [bool]$DisableBluetooth
  Save-State $State
  Wait-Until { Test-MatterHealth } "The local Matter controller did not become ready; inspect $logRoot" 60
  $State.controllerPid = Get-ListeningProcessId $MatterPort
  Save-State $State
}

function Invoke-AdminWithStdin(
  [ValidateSet("configure-wifi", "commission")]
  [string]$Operation,
  [string]$InputJson,
  [int]$TimeoutMilliseconds
) {
  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  Assert-Path $runtimePython "CIT virtual-environment Python"
  if ($InputJson.Length -gt 4096) { throw "Matter setup input exceeded its size limit." }
  $startInfo = [Diagnostics.ProcessStartInfo]::new()
  $startInfo.FileName = $runtimePython
  $startInfo.WorkingDirectory = $repositoryRoot
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true
  $startInfo.RedirectStandardInput = $true
  $startInfo.RedirectStandardOutput = $true
  $startInfo.RedirectStandardError = $true
  foreach ($argument in @(
      "-m", "cit_matter_smart_plug.admin", $Operation,
      "--server-url", $matterServerUrl
    )) {
    $startInfo.ArgumentList.Add($argument)
  }
  $process = [Diagnostics.Process]::new()
  $process.StartInfo = $startInfo
  if (-not $process.Start()) { throw "The fixed Matter administration process could not start." }
  $stdoutTask = $process.StandardOutput.ReadToEndAsync()
  $stderrTask = $process.StandardError.ReadToEndAsync()
  $process.StandardInput.Write($InputJson)
  $process.StandardInput.Close()
  if (-not $process.WaitForExit($TimeoutMilliseconds)) {
    $process.Kill($true)
    $process.WaitForExit()
    throw "Matter $Operation timed out. Put the plug back in pairing mode and try again."
  }
  $stdout = $stdoutTask.GetAwaiter().GetResult()
  $stderr = $stderrTask.GetAwaiter().GetResult()
  $exitCode = $process.ExitCode
  $process.Dispose()
  if ($exitCode -ne 0) {
    $diagnostic = @($stderr -split "\r?\n" | Where-Object { $_ }) | Select-Object -Last 1
    throw $(if ($diagnostic) { $diagnostic } else { "Matter $Operation failed." })
  }
  return $stdout | ConvertFrom-Json -AsHashtable
}

function Get-MatterInventory {
  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  Assert-Path $runtimePython "CIT virtual-environment Python"
  $raw = & $runtimePython -m cit_matter_smart_plug.admin inventory --server-url $matterServerUrl
  if ($LASTEXITCODE -ne 0 -or -not $raw) { throw "The local Matter inventory is unavailable." }
  return ($raw | Out-String) | ConvertFrom-Json -AsHashtable
}

function Assert-Fabric([string]$Bootstrap) {
  Assert-Path $bootstrapSecretPath "Shared Fabric credential; start Classroom Control first"
  if (-not (Get-ListeningProcessId $FabricPort)) {
    throw "Shared Fabric is not listening on port $FabricPort; start Classroom Control first."
  }
  $null = Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/auth/whoami" -Credential $Bootstrap
  $health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 5
  if ($health.physicalActuation -ne "enabled") {
    throw "Matter plug connection requires Classroom Control with physical devices enabled."
  }
}

function New-AdapterSession([hashtable]$Plug, [string]$Bootstrap) {
  return Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions" -Credential $Bootstrap -Body @{
    coursePackId = "smart-plug-control"
    coursePackVersion = "1.0.0"
    siteId = $SiteId
    roomId = $RoomId
    mode = "physical"
  }
}

function New-AdapterCredential([hashtable]$Plug, [string]$Bootstrap, [string]$SessionId) {
  $identitySuffix = ([string]$Plug.nodeId -replace '[^A-Za-z0-9._-]', '-').Substring(0, [Math]::Min(48, ([string]$Plug.nodeId).Length))
  $identityId = "cit-matter-$identitySuffix-$($SessionId.Substring(0, 8))"
  $response = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/auth/identities" -Credential $Bootstrap -Body @{
    identityId = $identityId
    actorType = "adapter"
    roles = @("plugin.cit.matter-smart-plug")
    permissions = @("fabric.adapters.connect", "fabric.events.publish", "fabric.nodes.write")
    siteId = $SiteId
    roomId = $RoomId
    sessionId = $SessionId
    ttlSeconds = 86400
  }
  $secretPath = Join-Path $secretRoot "$($Plug.nodeId)-fabric-adapter.dpapi"
  Save-ProtectedSecret $secretPath ([string]$response.token)
  return [string]$response.token
}

function Start-OneAdapter([hashtable]$Plug, [string]$Credential, [string]$SessionId) {
  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  $activationPath = Join-Path $activationRoot "$($Plug.nodeId).flag"
  [IO.File]::WriteAllText($activationPath, "connected`n", [Text.Encoding]::ASCII)
  $adapterEnvironment = @{
    CIT_FABRIC_ADAPTER_TOKEN = $Credential
    CIT_MATTER_ADAPTER_URL = $fabricAdapterUrl
    CIT_MATTER_SESSION_ID = $SessionId
    CIT_MATTER_SITE_ID = $SiteId
    CIT_MATTER_ROOM_ID = $RoomId
    CIT_MATTER_HOST_ID = $HostId
    CIT_MATTER_CIT_NODE_ID = [string]$Plug.nodeId
    CIT_MATTER_ACTIVATION_FILE = $activationPath
    CIT_MATTER_SERVER_URL = $matterServerUrl
    CIT_MATTER_NODE_ID = [string]$Plug.matterNodeId
    CIT_MATTER_ENDPOINT_ID = [string]$Plug.endpointId
    CIT_MATTER_DISPLAY_NAME = [string]$Plug.displayName
    CIT_MATTER_VENDOR_NAME = $(if ($Plug.vendorName) { [string]$Plug.vendorName } else { "Matter" })
    CIT_MATTER_PRODUCT_NAME = $(if ($Plug.productName) { [string]$Plug.productName } else { "On/Off Plug-in Unit" })
  }
  return Start-Process `
    -FilePath $runtimePython `
    -ArgumentList @("-m", "cit_matter_smart_plug") `
    -WorkingDirectory $repositoryRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot "$($Plug.nodeId).stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "$($Plug.nodeId).stderr.log") `
    -Environment $adapterEnvironment `
    -PassThru
}

function Stop-Adapters([hashtable]$State, [string]$Bootstrap) {
  $records = if ($State.ContainsKey("adapters")) { @(Expand-Sequence $State.adapters) } else { @() }
  foreach ($record in $records) {
    if ($record.activationPath -and (Test-Path -LiteralPath $record.activationPath)) {
      [IO.File]::Delete([string]$record.activationPath)
    }
  }
  foreach ($record in $records) {
    if ($record.adapterPid) {
      Wait-Process -Id ([int]$record.adapterPid) -Timeout 12 -ErrorAction SilentlyContinue
      Stop-ExactProcess $record.adapterPid $adapterMarker "Matter adapter"
    }
  }
  foreach ($record in $records) {
    if ($Bootstrap -and $record.sessionId -and (Get-ListeningProcessId $FabricPort)) {
      try {
        $null = Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions/$($record.sessionId)/stop" -Credential $Bootstrap
      } catch {
        Write-Warning "Could not close the inactive Matter session for $($record.nodeId)."
      }
    }
  }
  $State.adapters = @()
  Save-State $State
}

function Start-Adapters([hashtable]$State, [string]$Bootstrap) {
  Stop-Adapters $State $Bootstrap
  $inventory = Get-MatterInventory
  $plugs = @($inventory.plugs | Where-Object { $_.available })
  if ($plugs.Count -eq 0) {
    throw "No available commissioned Matter smart plugs were found. Add a plug from Classroom Control."
  }
  $records = [Collections.Generic.List[hashtable]]::new()
  foreach ($plug in $plugs) {
    $session = New-AdapterSession $plug $Bootstrap
    $credential = New-AdapterCredential $plug $Bootstrap ([string]$session.sessionId)
    $process = Start-OneAdapter $plug $credential ([string]$session.sessionId)
    $record = @{
      nodeId = [string]$plug.nodeId
      sessionId = [string]$session.sessionId
      adapterPid = $process.Id
      activationPath = Join-Path $activationRoot "$($plug.nodeId).flag"
    }
    $records.Add($record)
    $State.adapters = @($records)
    Save-State $State
    Wait-Until {
      try {
        $nodes = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential $Bootstrap))
        return @($nodes | Where-Object {
          $_.nodeId -eq [string]$plug.nodeId -and $_.connectionState -eq "connected"
        }).Count -eq 1
      } catch { return $false }
    } "Matter smart-plug adapter $($plug.nodeId) did not register; inspect $logRoot" 60
    $null = Invoke-JsonApi -Method PUT -Uri "$fabricOrigin/api/v1/fabric/sessions/$($session.sessionId)/roles/classroom_plug" -Credential $Bootstrap -Body @{
      nodeId = [string]$plug.nodeId
    }
  }
  $State.adapters = @($records)
  Save-State $State
  Wait-Until {
    try {
      $nodes = @(Expand-Sequence (Invoke-JsonApi -Method GET -Uri "$fabricOrigin/api/v1/fabric/nodes" -Credential $Bootstrap))
      $connected = @($nodes | Where-Object {
          $_.pluginId -eq "cit.matter-smart-plug" -and $_.connectionState -eq "connected"
        })
      return $connected.Count -ge $records.Count
    } catch { return $false }
  } "Matter smart-plug adapters did not register; inspect $logRoot" 60
  Write-Host "READY $($records.Count) cloud-free Matter plug endpoint(s) connected and forced to the off safe state."
}

function Show-Status([hashtable]$State) {
  Write-Host "Matter controller: $(if (Test-MatterHealth) { 'ready on loopback' } else { 'offline' })"
  Write-Host "Matter storage: $controllerStorage"
  if (Test-MatterHealth) {
    try {
      $inventory = Get-MatterInventory
      Write-Host "Wi-Fi credentials configured: $($inventory.controller.wifiCredentialsSet)"
      Write-Host "Bluetooth commissioning enabled: $($inventory.controller.bluetoothEnabled)"
      Write-Host "Commissioned plug endpoints: $(@($inventory.plugs).Count)"
      foreach ($plug in @($inventory.plugs)) {
        Write-Host "  $($plug.displayName) [$($plug.nodeId)] available=$($plug.available)"
      }
    } catch {
      Write-Warning $_.Exception.Message
    }
  }
  $adapterCount = if ($State.ContainsKey("adapters")) { @(Expand-Sequence $State.adapters).Count } else { 0 }
  Write-Host "Recorded Fabric adapters: $adapterCount"
  Write-Host "No proprietary vendor account, API, cloud, device ID, or local key is used by this path."
}

New-Item -ItemType Directory -Path $StateRoot, $controllerStorage, $secretRoot, $logRoot, $activationRoot -Force | Out-Null
$state = Load-State

if ($Mode -notin @("Status", "Stop")) { Build-Systems }
if ($Mode -eq "ControllerStart") {
  Start-Controller $state
  Show-Status $state
  exit 0
}
if ($Mode -eq "Status") {
  Show-Status $state
  exit 0
}

$bootstrap = if (Test-Path -LiteralPath $bootstrapSecretPath) {
  Read-ProtectedSecret $bootstrapSecretPath
} else { "" }

if ($Mode -eq "Stop") {
  Stop-Adapters $state $bootstrap
  if ($state.ContainsKey("controllerPid")) {
    Stop-ExactProcess $state.controllerPid $controllerMarker "Matter controller"
  }
  foreach ($key in @("controllerPid", "controllerLauncherPid")) { $state.Remove($key) }
  Save-State $state
  Write-Host "Stopped CIT Matter adapters and the local controller. Commissioned fabric data remains."
  exit 0
}

Start-Controller $state
if ($Mode -eq "ConfigureWifi") {
  $inputJson = [Console]::In.ReadToEnd()
  if (-not $inputJson.Trim()) { throw "Wi-Fi configuration must be supplied through standard input." }
  $null = Invoke-AdminWithStdin "configure-wifi" $inputJson 30000
  Write-Host "Saved classroom Wi-Fi credentials only in the local Matter controller."
  exit 0
}

Assert-Fabric $bootstrap
if ($Mode -eq "Commission") {
  $inputJson = [Console]::In.ReadToEnd()
  if (-not $inputJson.Trim()) { throw "Matter setup code must be supplied through standard input." }
  $result = Invoke-AdminWithStdin "commission" $inputJson 260000
  Write-Host "Commissioned $(@($result.plugs).Count) standard Matter plug endpoint(s) into the local CIT fabric."
}
Start-Adapters $state $bootstrap
Show-Status $state
if (-not $NoOpenConsole) {
  & (Join-Path $repositoryRoot "tools\hardware\interaction-fabric-console.ps1") `
    -Mode Open `
    -FabricPort $FabricPort `
    -StateRoot $SharedFabricRoot
}

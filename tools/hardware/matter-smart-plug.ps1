#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("ControllerStart", "ConfigureWifi", "Commission", "ListSetupCodes", "Rename", "Start", "Status", "Stop")]
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
$setupCodeRegistryPath = Join-Path $secretRoot "known-setup-codes.dpapi"
$bootstrapSecretPath = Join-Path $SharedFabricRoot "secrets\fabric-bootstrap.dpapi"
$fabricOrigin = "http://127.0.0.1:$FabricPort"
$fabricAdapterUrl = "ws://127.0.0.1:$FabricPort/api/v1/adapters/connect"
$matterOrigin = "http://127.0.0.1:$MatterPort"
$matterServerUrl = "ws://127.0.0.1:$MatterPort/ws"
$controllerMarker = "matter-server/dist/esm/MatterServer.js"
$adapterMarker = "cit_matter_smart_plug"
$bleProxyMarker = "matter-ble-proxy"
$controllerStartupAttempts = 3

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

function Normalize-MatterSetupCode([string]$SetupCode) {
  $normalized = $SetupCode.Trim()
  $hasControlCharacters = @(
    $normalized.ToCharArray() |
      Where-Object { [int]$_ -lt 32 -or [int]$_ -eq 127 }
  ).Count -gt 0
  if (
    $normalized.Length -lt 11 -or
    $normalized.Length -gt 103 -or
    $hasControlCharacters
  ) {
    throw "The protected Matter setup-code registry is invalid."
  }
  if ($normalized.StartsWith("MT:", [StringComparison]::OrdinalIgnoreCase)) {
    return $normalized
  }
  $digits = [regex]::Replace($normalized, '\D', '')
  if ($digits.Length -notin @(11, 21)) {
    throw "The protected Matter setup-code registry is invalid."
  }
  return $digits
}

function Normalize-MatterPlugName([string]$Name) {
  $normalized = $Name.Trim()
  $hasControlCharacters = @(
    $normalized.ToCharArray() |
      Where-Object { [int]$_ -lt 32 -or [int]$_ -eq 127 }
  ).Count -gt 0
  if (
    $normalized -ne $Name -or
    $normalized.Length -lt 1 -or
    $normalized.Length -gt 64 -or
    $hasControlCharacters
  ) {
    throw "CIT_MATTER_ERROR|MATTER_PLUG_NAME_INVALID|Enter a name between 1 and 64 printable characters."
  }
  return $normalized
}

function Read-MatterSetupCodeRegistry {
  $registry = [ordered]@{ schemaVersion = "1.0"; entries = @() }
  if (-not (Test-Path -LiteralPath $setupCodeRegistryPath -PathType Leaf)) {
    return $registry
  }
  try {
    $document = Read-ProtectedSecret $setupCodeRegistryPath |
      ConvertFrom-Json -AsHashtable
    $sourceEntries = if ($document -is [Collections.IDictionary]) {
      if ($document.schemaVersion -ne "1.0") { throw "Unsupported registry schema." }
      @($document.entries)
    } else {
      @($document)
    }
    $entries = [Collections.Generic.List[hashtable]]::new()
    foreach ($source in $sourceEntries) {
      $setupCode = if ($source -is [string]) { $source } else { [string]$source.setupCode }
      $matterNodeIds = @(
        if ($source -isnot [string] -and $source.ContainsKey("matterNodeIds")) {
          $source.matterNodeIds
        }
      )
      $validatedNodeIds = @(
        $matterNodeIds |
          ForEach-Object { [string]$_ } |
          Where-Object { $_ -match '^[1-9][0-9]{0,19}$' } |
          Select-Object -Unique
      )
      if ($validatedNodeIds.Count -ne $matterNodeIds.Count) {
        throw "Invalid Matter node mapping."
      }
      $validatedEntry = @{
          setupCode = Normalize-MatterSetupCode $setupCode
          matterNodeIds = $validatedNodeIds
      }
      if ($source -isnot [string] -and $source.ContainsKey("name") -and $null -ne $source.name) {
        $validatedEntry.name = Normalize-MatterPlugName ([string]$source.name)
      }
      $entries.Add($validatedEntry)
    }
    $registry.entries = @($entries)
    return $registry
  } catch {
    throw "The protected Matter setup-code registry is invalid."
  }
}

function Save-MatterSetupCodeRegistry([Collections.IDictionary]$Registry) {
  $payload = $Registry | ConvertTo-Json -Depth 6 -Compress
  Save-ProtectedSecret $setupCodeRegistryPath $payload
}

function Register-MatterSetupCode([string]$SetupCode, [object[]]$MatterNodeIds) {
  $normalized = Normalize-MatterSetupCode $SetupCode
  $registry = Read-MatterSetupCodeRegistry
  $entry = @($registry.entries | Where-Object { $_.setupCode -eq $normalized }) |
    Select-Object -First 1
  if ($null -eq $entry) {
    $entry = @{ setupCode = $normalized; matterNodeIds = @() }
    $registry.entries = @($registry.entries) + $entry
  }
  $mapped = [Collections.Generic.List[string]]::new()
  foreach ($nodeId in @($entry.matterNodeIds) + $MatterNodeIds) {
    $value = [string]$nodeId
    if ($value -notmatch '^[1-9][0-9]{0,19}$') {
      throw "Matter returned an invalid node identifier."
    }
    if (-not $mapped.Contains($value)) { $mapped.Add($value) }
  }
  $entry.matterNodeIds = @($mapped)
  Save-MatterSetupCodeRegistry $registry
}

function Set-MatterPlugName([string]$MatterNodeId, [string]$Name) {
  if ($MatterNodeId -notmatch '^[1-9][0-9]{0,19}$') {
    throw "CIT_MATTER_ERROR|MATTER_PLUG_NODE_INVALID|The Matter plug identifier is invalid."
  }
  $normalizedName = Normalize-MatterPlugName $Name
  $registry = Read-MatterSetupCodeRegistry
  $matches = @(
    $registry.entries |
      Where-Object { @($_.matterNodeIds) -contains $MatterNodeId }
  )
  if ($matches.Count -ne 1) {
    throw "CIT_MATTER_ERROR|MATTER_PLUG_NOT_REGISTERED|That Matter plug is not registered on this computer."
  }
  $matches[0].name = $normalizedName
  Save-MatterSetupCodeRegistry $registry
  return $registry
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

function Test-ExactProcess([object]$ProcessId, [string]$Marker) {
  if ($null -eq $ProcessId) { return $false }
  $commandLine = Get-ProcessCommandLine ([int]$ProcessId)
  return (
    $null -ne $commandLine -and
    $commandLine.Contains($Marker, [StringComparison]::OrdinalIgnoreCase)
  )
}

function Get-DescendantProcessIds([int]$ProcessId) {
  $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  $pending = [Collections.Generic.Queue[int]]::new()
  $result = [Collections.Generic.List[int]]::new()
  $pending.Enqueue($ProcessId)
  while ($pending.Count -gt 0) {
    $parentId = $pending.Dequeue()
    foreach ($child in @($processes | Where-Object { $_.ParentProcessId -eq $parentId })) {
      $childId = [int]$child.ProcessId
      $result.Add($childId)
      $pending.Enqueue($childId)
    }
  }
  return @($result)
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
  Invoke-External (Resolve-Executable "uv") `
    @("sync", "--all-packages", "--frozen", "--inexact") `
    $repositoryRoot
  Invoke-External (Resolve-Executable "pnpm.cmd") @("install", "--frozen-lockfile") $repositoryRoot
  Invoke-External (Resolve-Executable "pnpm.cmd") @("build") $repositoryRoot
}

function Resolve-MatterPrimaryInterface {
  try {
    $candidates = foreach ($adapter in @(Get-NetAdapter -Physical -ErrorAction Stop)) {
      if ($adapter.Status -ne "Up") { continue }
      $configuration = Get-NetIPConfiguration -InterfaceIndex $adapter.ifIndex -ErrorAction Stop
      if ($null -eq $configuration.IPv4DefaultGateway) { continue }
      $ipInterface = Get-NetIPInterface `
        -AddressFamily IPv4 `
        -InterfaceIndex $adapter.ifIndex `
        -ErrorAction Stop
      [pscustomobject]@{
        Name = [string]$adapter.Name
        Metric = [int]$ipInterface.InterfaceMetric
      }
    }
    $selected = $candidates | Sort-Object Metric, Name | Select-Object -First 1
    if ($null -ne $selected) { return [string]$selected.Name }
  } catch {
    Write-Warning "Could not resolve the primary physical LAN interface; Matter will auto-select it."
  }
  return ""
}

function Test-MatterHealth {
  try {
    $health = Invoke-RestMethod -Uri "$matterOrigin/health" -TimeoutSec 2
    return $health.version -eq "1.4.0"
  } catch {
    return $false
  }
}

function Read-MatterControllerErrorLog([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return "" }
  try {
    return [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
  } catch {
    return ""
  }
}

function Test-RetryableMatterPortFailure([string]$ErrorLogPath) {
  $errorLog = Read-MatterControllerErrorLog $ErrorLogPath
  return (
    $errorLog.Contains("listen EACCES: permission denied", [StringComparison]::OrdinalIgnoreCase) -and
    $errorLog -match '0\.0\.0\.0:\d+'
  )
}

function Stop-BleProxy([hashtable]$State) {
  if ($State.ContainsKey("bleProxyPid")) {
    $rootId = [int]$State.bleProxyPid
    $processIds = @($rootId) + @(Get-DescendantProcessIds $rootId)
    [array]::Reverse($processIds)
    foreach ($processId in $processIds) {
      if (Test-ExactProcess $processId $bleProxyMarker) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
      }
    }
    $State.Remove("bleProxyPid")
    Save-State $State
  }
}

function Test-BleProxyReady([hashtable]$State) {
  if (-not $State.ContainsKey("bleProxyPid")) { return $false }
  if (-not (Test-ExactProcess $State.bleProxyPid $bleProxyMarker)) { return $false }
  $rootId = [int]$State.bleProxyPid
  $processIds = @($rootId) + @(Get-DescendantProcessIds $rootId)
  $connection = Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue |
    Where-Object {
      $_.RemotePort -eq $MatterPort -and $_.OwningProcess -in $processIds
    } |
    Select-Object -First 1
  return $null -ne $connection
}

function Start-BleProxy([hashtable]$State) {
  if ($DisableBluetooth) {
    Stop-BleProxy $State
    return
  }
  if (Test-BleProxyReady $State) { return }
  Stop-BleProxy $State
  $proxyExecutable = Join-Path $repositoryRoot ".venv\Scripts\matter-ble-proxy.exe"
  Assert-Path $proxyExecutable "Pinned Windows Matter BLE proxy"
  $process = Start-Process `
    -FilePath $proxyExecutable `
    -ArgumentList @(
      "--server", "ws://127.0.0.1:$MatterPort/ble",
      "--log-level", "INFO"
    ) `
    -WorkingDirectory $repositoryRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot "matter-ble-proxy.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "matter-ble-proxy.stderr.log") `
    -PassThru
  $State.bleProxyPid = $process.Id
  Save-State $State
  try {
    Wait-Until {
      Test-BleProxyReady $State
    } "The Windows Matter BLE proxy did not connect; inspect $logRoot" 30
  } catch {
    Stop-BleProxy $State
    throw
  }
}

function Start-Controller([hashtable]$State) {
  $desiredBleMode = if ($DisableBluetooth) { "disabled" } else { "proxy" }
  $listenerId = Get-ListeningProcessId $MatterPort
  if ($null -ne $listenerId) {
    if (-not (Test-MatterHealth)) {
      throw "Port $MatterPort is occupied by a service that is not the pinned CIT Matter controller."
    }
    if ($State.ContainsKey("bleMode") -and $State.bleMode -eq $desiredBleMode) {
      $State.controllerPid = $listenerId
      Save-State $State
      Start-BleProxy $State
      return
    }
    Stop-BleProxy $State
    Stop-ExactProcess $listenerId $controllerMarker "Matter controller"
    Wait-Until {
      $null -eq (Get-ListeningProcessId $MatterPort)
    } "The previous Matter controller did not release port $MatterPort" 30
  }
  if (
    $State.ContainsKey("controllerLauncherPid") -and
    (Test-ExactProcess $State.controllerLauncherPid $controllerMarker)
  ) {
    Stop-ExactProcess $State.controllerLauncherPid $controllerMarker "stale Matter controller"
    $State.Remove("controllerLauncherPid")
    $State.Remove("controllerPid")
    Save-State $State
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
  $primaryInterface = Resolve-MatterPrimaryInterface
  if ($primaryInterface) {
    $controllerEnvironment.PRIMARY_INTERFACE = $primaryInterface
  }
  if ($desiredBleMode -eq "proxy") {
    $controllerEnvironment.BLE_PROXY = "true"
  }
  $controllerStdoutPath = Join-Path $logRoot "matter-controller.stdout.log"
  $controllerStderrPath = Join-Path $logRoot "matter-controller.stderr.log"
  $controllerReady = $false
  for ($attempt = 1; $attempt -le $controllerStartupAttempts; $attempt++) {
    [IO.File]::WriteAllText($controllerStdoutPath, "", [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($controllerStderrPath, "", [Text.UTF8Encoding]::new($false))
    $process = Start-Process `
      -FilePath $node `
      -ArgumentList @("node_modules/matter-server/dist/esm/MatterServer.js") `
      -WorkingDirectory (Join-Path $repositoryRoot "apps\matter-controller") `
      -WindowStyle Hidden `
      -RedirectStandardOutput $controllerStdoutPath `
      -RedirectStandardError $controllerStderrPath `
      -Environment $controllerEnvironment `
      -PassThru
    $State.controllerLauncherPid = $process.Id
    $State.bluetoothRequested = -not [bool]$DisableBluetooth
    $State.bleMode = $desiredBleMode
    Save-State $State

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(60)
    do {
      if (Test-MatterHealth) {
        $controllerReady = $true
        break
      }
      if (Test-RetryableMatterPortFailure $controllerStderrPath) { break }
      if ($process.HasExited) { break }
      Start-Sleep -Milliseconds 250
    } while ([DateTimeOffset]::UtcNow -lt $deadline)

    if ($controllerReady) { break }

    $retryablePortFailure = Test-RetryableMatterPortFailure $controllerStderrPath
    Stop-ExactProcess $process.Id $controllerMarker "Matter controller"
    $State.Remove("controllerLauncherPid")
    $State.Remove("controllerPid")
    Save-State $State
    if ($retryablePortFailure -and $attempt -lt $controllerStartupAttempts) {
      Write-Warning (
        "Matter controller selected a Windows-reserved operational port; " +
        "retrying startup ($attempt/$controllerStartupAttempts)."
      )
      continue
    }
    throw "The local Matter controller did not become ready; inspect $logRoot"
  }
  if (-not $controllerReady) {
    throw "The local Matter controller did not become ready; inspect $logRoot"
  }
  $State.controllerPid = Get-ListeningProcessId $MatterPort
  Save-State $State
  Start-BleProxy $State
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

function Get-LatestSmartPlugCourse([string]$Bootstrap) {
  $coursePacks = @(
    Expand-Sequence (
      Invoke-JsonApi `
        -Method GET `
        -Uri "$fabricOrigin/api/v1/fabric/course-packs" `
        -Credential $Bootstrap
    )
  )
  $coursePack = $coursePacks |
    Where-Object { $_.coursePackId -eq "smart-plug-control" } |
    Sort-Object { [version]$_.version } -Descending |
    Select-Object -First 1
  if ($null -eq $coursePack) {
    throw "The smart-plug control course is not installed in Classroom Control."
  }
  return $coursePack
}

function New-AdapterSession(
  [string]$Bootstrap,
  [object]$CoursePack
) {
  return Invoke-JsonApi -Method POST -Uri "$fabricOrigin/api/v1/fabric/sessions" -Credential $Bootstrap -Body @{
    coursePackId = [string]$CoursePack.coursePackId
    coursePackVersion = [string]$CoursePack.version
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
  $coursePack = Get-LatestSmartPlugCourse $Bootstrap
  $records = [Collections.Generic.List[hashtable]]::new()
  foreach ($plug in $plugs) {
    $session = New-AdapterSession $Bootstrap $coursePack
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
      Write-Host "Bluetooth radio: $($inventory.controller.bluetoothStatus)"
      if ($State.ContainsKey("bleMode") -and $State.bleMode -eq "proxy") {
        Write-Host "Windows BLE proxy link: $(if (Test-BleProxyReady $State) { 'connected' } else { 'offline' })"
      }
      Write-Host "Commissioned plug endpoints: $(@($inventory.plugs).Count)"
      foreach ($plug in @($inventory.plugs)) {
        Write-Host "  $($plug.displayName) [$($plug.nodeId)] available=$($plug.available) electricalTelemetry=$($plug.electricalTelemetry)"
      }
    } catch {
      Write-Warning $_.Exception.Message
    }
  }
  $adapterRecords = @(
    if ($State.ContainsKey("adapters")) {
      Expand-Sequence $State.adapters
    }
  )
  $adapterCount = $adapterRecords.Count
  $runningAdapterCount = 0
  foreach ($record in $adapterRecords) {
    $running = $record.adapterPid -and (Test-ExactProcess $record.adapterPid $adapterMarker)
    if ($running) { $runningAdapterCount++ }
    Write-Host "  Fabric adapter $($record.nodeId): $(if ($running) { 'running' } else { 'offline' })"
  }
  Write-Host "Recorded Fabric adapters: $adapterCount"
  Write-Host "Running Fabric adapters: $runningAdapterCount"
  Write-Host "Offline Fabric adapter records: $($adapterCount - $runningAdapterCount)"
  Write-Host "No proprietary vendor account, API, cloud, device ID, or local key is used by this path."
}

New-Item -ItemType Directory -Path $StateRoot, $controllerStorage, $secretRoot, $logRoot, $activationRoot -Force | Out-Null
$state = Load-State

if ($Mode -notin @("ListSetupCodes", "Rename", "Status", "Stop")) { Build-Systems }
if ($Mode -eq "ListSetupCodes") {
  $registry = Read-MatterSetupCodeRegistry
  Write-Output ($registry | ConvertTo-Json -Depth 6 -Compress)
  exit 0
}
if ($Mode -eq "Rename") {
  $inputJson = [Console]::In.ReadToEnd()
  if (-not $inputJson.Trim()) {
    throw "CIT_MATTER_ERROR|MATTER_PLUG_NAME_INVALID|A Matter plug identifier and name are required."
  }
  try {
    $renameInput = $inputJson | ConvertFrom-Json -AsHashtable
    if (
      $renameInput -isnot [Collections.IDictionary] -or
      @($renameInput.Keys).Count -ne 2 -or
      -not $renameInput.ContainsKey("matterNodeId") -or
      -not $renameInput.ContainsKey("name")
    ) {
      throw "CIT_MATTER_ERROR|MATTER_PLUG_NAME_INVALID|A Matter plug identifier and name are required."
    }
    $registry = Set-MatterPlugName ([string]$renameInput.matterNodeId) ([string]$renameInput.name)
    Write-Output ($registry | ConvertTo-Json -Depth 6 -Compress)
    exit 0
  } catch {
    if ($_.Exception.Message.Contains("CIT_MATTER_ERROR|")) { throw }
    throw "CIT_MATTER_ERROR|MATTER_PLUG_NAME_INVALID|A Matter plug identifier and valid name are required."
  }
}
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
  Stop-BleProxy $state
  if ($state.ContainsKey("controllerPid")) {
    Stop-ExactProcess $state.controllerPid $controllerMarker "Matter controller"
  }
  if ($state.ContainsKey("controllerLauncherPid")) {
    Stop-ExactProcess $state.controllerLauncherPid $controllerMarker "Matter controller launcher"
  }
  foreach ($key in @("controllerPid", "controllerLauncherPid", "bleMode")) {
    $state.Remove($key)
  }
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
  $inventory = Get-MatterInventory
  if (-not $inventory.controller.wifiCredentialsSet) {
    [Console]::Error.WriteLine(
      "CIT_MATTER_ERROR|MATTER_WIFI_NOT_CONFIGURED|Save the classroom 2.4 GHz Wi-Fi before adding a Matter plug."
    )
    exit 1
  }
  $inputJson = [Console]::In.ReadToEnd()
  if (-not $inputJson.Trim()) { throw "Matter setup code must be supplied through standard input." }
  $result = Invoke-AdminWithStdin "commission" $inputJson 260000
  $commissioningInput = $inputJson | ConvertFrom-Json -AsHashtable
  Register-MatterSetupCode `
    ([string]$commissioningInput.setupCode) `
    @($result.plugs | ForEach-Object { [string]$_.matterNodeId })
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

#Requires -Version 7.4

[CmdletBinding()]
param(
  [string]$StateRoot = "",
  [string]$Brain2DevicesRoot = "",
  [string]$RoboMasterRoot = "",
  [string]$AgentMeshRoot = "",
  [switch]$SkipWifiScan
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$WarningPreference = "SilentlyContinue"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$workspaceRoot = Split-Path $repositoryRoot -Parent
if (-not $StateRoot) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
}
if (-not $Brain2DevicesRoot) {
  $Brain2DevicesRoot = Join-Path $workspaceRoot "brain2devices"
}
if (-not $RoboMasterRoot) {
  $RoboMasterRoot = Join-Path $workspaceRoot "robomaster-gesture-control-reference"
}
if (-not $AgentMeshRoot) {
  $AgentMeshRoot = Join-Path $workspaceRoot "glasses2CLI"
}
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$Brain2DevicesRoot = [IO.Path]::GetFullPath($Brain2DevicesRoot)
$RoboMasterRoot = [IO.Path]::GetFullPath($RoboMasterRoot)
$AgentMeshRoot = [IO.Path]::GetFullPath($AgentMeshRoot)
$warnings = [Collections.Generic.List[string]]::new()
$script:presentPnpDevices = $null

function Test-LocalTcpPort([int]$Port) {
  $client = [Net.Sockets.TcpClient]::new()
  try {
    $task = $client.ConnectAsync("127.0.0.1", $Port)
    return $task.Wait(450) -and $client.Connected
  } catch {
    return $false
  } finally {
    $client.Dispose()
  }
}

function Get-PresentDevices([string]$Pattern) {
  if ($null -eq $script:presentPnpDevices) {
    try {
      $script:presentPnpDevices = @(Get-PnpDevice -PresentOnly -ErrorAction Stop)
    } catch {
      $script:presentPnpDevices = @()
    }
  }
  return @(
    $script:presentPnpDevices |
      Where-Object { [string]$_.FriendlyName -match $Pattern }
  )
}

function Invoke-AdbText(
  [string]$AdbPath,
  [string]$Serial,
  [string[]]$Arguments
) {
  try {
    $output = (& $AdbPath -s $Serial @Arguments 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { return "" }
    return [string]$output
  } catch {
    return ""
  }
}

function Test-AdbPackage(
  [string]$AdbPath,
  [string]$Serial,
  [string]$PackageName
) {
  return (Invoke-AdbText $AdbPath $Serial @("shell", "pm", "path", $PackageName)) -match "(?m)^package:"
}

function Test-AdbPackageRunning(
  [string]$AdbPath,
  [string]$Serial,
  [string]$PackageName
) {
  return (Invoke-AdbText $AdbPath $Serial @("shell", "pidof", $PackageName)) -match "^\d+(?:\s+\d+)*$"
}

function Get-AndroidBridgeDevices([string]$AdbPath) {
  if (-not $AdbPath) { return @() }
  try {
    $lines = @(& $AdbPath devices -l 2>$null)
    if ($LASTEXITCODE -ne 0) { return @() }
  } catch {
    return @()
  }

  $devices = [Collections.Generic.List[object]]::new()
  foreach ($line in $lines) {
    $trimmed = ([string]$line).Trim()
    if (-not $trimmed -or $trimmed.StartsWith("List of devices", [StringComparison]::OrdinalIgnoreCase)) {
      continue
    }
    $parts = @($trimmed -split "\s+")
    if ($parts.Count -lt 2 -or $parts[0] -match "^emulator-") { continue }
    $serial = [string]$parts[0]
    $adbState = [string]$parts[1]
    if ($adbState -notin @("device", "unauthorized", "offline")) { continue }

    $isUsb = $trimmed -match "(?:^|\s)usb:"
    $isWifi = -not $isUsb -and (
      $serial -match "^(?:\d{1,3}\.){3}\d{1,3}:\d+$" -or
      $serial -match "\._adb-tls-connect\._tcp" -or
      $serial -match "^[^\s:]+:\d+$"
    )
    $connectionPath = if ($isUsb) { "android_usb" } elseif ($isWifi) { "android_wifi" } else { "android" }
    $transport = if ($isUsb) { "Android phone / USB" } elseif ($isWifi) { "Android phone / Wi-Fi" } else { "Android phone / ADB" }
    $linkState = if ($isUsb) { "attached" } else { "connected" }
    $authorized = $adbState -eq "device"
    $model = ""
    if ($authorized) {
      $model = Invoke-AdbText $AdbPath $serial @("shell", "getprop", "ro.product.model")
      $model = ($model -replace "[^\p{L}\p{Nd} ._()+-]", " ").Trim()
      if ($model.Length -gt 60) { $model = $model.Substring(0, 60).Trim() }
    }
    $hasEvenApp = $authorized -and (Test-AdbPackage $AdbPath $serial "com.even.sg")
    $hasAgentMeshApp = $authorized -and (Test-AdbPackage $AdbPath $serial "dev.agentmesh.mobile")
    $hasMetaCameraApp = $authorized -and (Test-AdbPackage $AdbPath $serial "com.meta.wearable.dat.externalsampleapps.cameraaccess")
    $devices.Add([pscustomobject]@{
      displayName = if ($model) { "Android phone · $model" } else { "Android phone" }
      transport = $transport
      connectionPath = $connectionPath
      linkState = $linkState
      authorized = $authorized
      adbState = $adbState
      hasEvenApp = $hasEvenApp
      evenAppRunning = $hasEvenApp -and (Test-AdbPackageRunning $AdbPath $serial "com.even.sg")
      hasAgentMeshApp = $hasAgentMeshApp
      agentMeshAppRunning = $hasAgentMeshApp -and (Test-AdbPackageRunning $AdbPath $serial "dev.agentmesh.mobile")
      hasMetaCameraApp = $hasMetaCameraApp
      metaCameraAppRunning = $hasMetaCameraApp -and (Test-AdbPackageRunning $AdbPath $serial "com.meta.wearable.dat.externalsampleapps.cameraaccess")
    })
  }
  return @($devices)
}

function Get-AgentMeshWearableEvidence([string]$Root) {
  if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return @() }
  $pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
  if ($null -eq $pnpmCommand) { return @() }
  try {
    Push-Location -LiteralPath $Root
    try {
      $raw = (& $pnpmCommand.Source --silent agentmesh --output json hub list-devices --hub http://127.0.0.1:7342 --allow-insecure-http 2>$null | Out-String)
      if ($LASTEXITCODE -ne 0 -or -not $raw.Trim()) { return @() }
      $document = $raw | ConvertFrom-Json -Depth 20
    } finally {
      Pop-Location
    }
    $records = if ($document.PSObject.Properties.Name -contains "devices") { @($document.devices) } else { @() }
    $now = [DateTimeOffset]::UtcNow
    $latestByDevice = @{}
    foreach ($record in $records) {
      $kind = [string]$record.kind
      if ($kind -notin @("even_g2", "ray_ban")) { continue }
      try { $expiresAt = [DateTimeOffset]::Parse([string]$record.expiresAt) } catch { continue }
      if ($expiresAt -le $now) { continue }
      $revoked = $record.PSObject.Properties.Name -contains "revokedAt" -and [bool]$record.revokedAt
      if ($revoked) { continue }
      $deviceId = [string]$record.deviceId
      if (-not $deviceId) { continue }
      $key = "$kind|$deviceId"
      $lastUsedAt = $null
      if ($record.PSObject.Properties.Name -contains "lastUsedAt" -and $record.lastUsedAt) {
        try { $lastUsedAt = [DateTimeOffset]::Parse([string]$record.lastUsedAt) } catch { $lastUsedAt = $null }
      }
      if (-not $latestByDevice.ContainsKey($key) -or (
          $null -ne $lastUsedAt -and
          ($null -eq $latestByDevice[$key].lastUsedAt -or $lastUsedAt -gt $latestByDevice[$key].lastUsedAt)
        )) {
        $latestByDevice[$key] = [pscustomobject]@{ kind = $kind; lastUsedAt = $lastUsedAt }
      }
    }
    return @(
      $latestByDevice.Values |
        Sort-Object kind |
        ForEach-Object {
          $recent = $null -ne $_.lastUsedAt -and
            ($now - $_.lastUsedAt).TotalSeconds -ge -30 -and
            ($now - $_.lastUsedAt).TotalSeconds -le 120
          [pscustomobject]@{ kind = $_.kind; recentlyActive = $recent }
        }
    )
  } catch {
    return @()
  }
}

function Get-SelectableAgentSessionCount([string]$Root) {
  if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return 0 }
  $pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
  if ($null -eq $pnpmCommand) { return 0 }

  try {
    Push-Location -LiteralPath $Root
    try {
      # The local CLI loads its own scoped control credential. Capture and discard
      # the complete response so workspace/session details never enter this report.
      $raw = (& $pnpmCommand.Source --silent agentmesh --output json session list 2>$null | Out-String)
      if ($LASTEXITCODE -ne 0 -or -not $raw.Trim()) { return 0 }
      $document = $raw | ConvertFrom-Json -Depth 20
    } finally {
      Pop-Location
    }

    $unavailableStates = @("failed", "stopping", "stopped", "disconnected")
    return @(
      $document.sessions |
        Where-Object {
          $controlStatus = [string]$_.controlStatus
          $state = [string]$_.state
          $controlStatus -in @("managed", "observed") -and
            $state -notin $unavailableStates
        }
    ).Count
  } catch {
    return 0
  }
}

function Get-RoboMasterBroadcastCount([int]$TimeoutMilliseconds = 2200) {
  $addresses = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $listener = $null
  try {
    $listener = [Net.Sockets.UdpClient]::new(45678)
    $listener.Client.ReceiveTimeout = 350
    $deadline = [DateTimeOffset]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
      $remote = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
      try {
        $payload = $listener.Receive([ref]$remote)
        if ($payload.Length -gt 0 -and $payload.Length -le 1024) {
          $null = $addresses.Add($remote.Address.ToString())
        }
      } catch [Net.Sockets.SocketException] {
        if ($_.Exception.SocketErrorCode -ne [Net.Sockets.SocketError]::TimedOut) { throw }
      }
    }
  } catch [Net.Sockets.SocketException] {
    $script:warnings.Add("RoboMaster STA broadcast port 45678 is already in use; close the DJI desktop app or use an explicit robot address before SDK discovery.")
  } finally {
    if ($null -ne $listener) { $listener.Dispose() }
  }
  return $addresses.Count
}

function New-Candidate(
  [string]$Id,
  [string]$Name,
  [string]$Transport,
  [ValidateSet("found", "ready", "setup_required", "not_found")]
  [string]$Status,
  [string]$Detail,
  [Nullable[int]]$SignalPercent = $null,
  [ValidateSet("", "usb", "bluetooth", "wifi", "android", "android_usb", "android_wifi", "local_service")]
  [string]$ConnectionPath = "",
  [ValidateSet("", "attached", "connected", "recently_active", "visible", "paired", "provisioned", "ready")]
  [string]$LinkState = ""
) {
  $candidate = [ordered]@{
    candidateId = $Id
    displayName = $Name
    transport = $Transport
    status = $Status
    detail = $Detail
  }
  if ($null -ne $SignalPercent) { $candidate.signalPercent = [int]$SignalPercent }
  if ($ConnectionPath) { $candidate.connectionPath = $ConnectionPath }
  if ($LinkState) { $candidate.linkState = $LinkState }
  return $candidate
}

function New-Integration(
  [string]$Id,
  [string]$Name,
  [ValidateSet("interaction", "sensor", "robot", "drone", "smart_device", "coding_agent")]
  [string]$Category,
  [ValidateSet("not_scanned", "connected", "found", "ready", "setup_required", "not_found", "unavailable")]
  [string]$Status,
  [string]$Summary,
  [string]$ConnectionMethod,
  [object[]]$Candidates,
  [string[]]$SetupSteps,
  [string]$SafetyNote,
  [string]$SetupCommand = "",
  [string]$ActionId = "",
  [string]$ActionLabel = "",
  [bool]$RequiresGroundedConfirmation = $false
) {
  $integration = [ordered]@{
    integrationId = $Id
    displayName = $Name
    category = $Category
    status = $Status
    summary = $Summary
    connectionMethod = $ConnectionMethod
    connectedNodeIds = @()
    candidates = @($Candidates)
    setupSteps = @($SetupSteps)
    requiresGroundedConfirmation = $RequiresGroundedConfirmation
    safetyNote = $SafetyNote
  }
  if ($SetupCommand) { $integration.setupCommand = $SetupCommand }
  if ($ActionId) { $integration.actionId = $ActionId }
  if ($ActionLabel) { $integration.actionLabel = $ActionLabel }
  return $integration
}

$integrations = [Collections.Generic.List[object]]::new()

# G2 and Meta share Agent Mesh, but every source of connection evidence remains
# profile-specific. ADB serials, Bluetooth addresses, device IDs, and token
# material are intentionally reduced to generic candidates before serialization.
$agentMeshListening = Test-LocalTcpPort 7342
$adbCommand = Get-Command adb -ErrorAction SilentlyContinue
$androidBridges = @(
  if ($null -ne $adbCommand) {
    Get-AndroidBridgeDevices -AdbPath $adbCommand.Source
  }
)
$agentMeshWearables = @(
  if ($agentMeshListening) {
    Get-AgentMeshWearableEvidence -Root $AgentMeshRoot
  }
)
$g2Wearables = @($agentMeshWearables | Where-Object kind -eq "even_g2")
$metaWearables = @($agentMeshWearables | Where-Object kind -eq "ray_ban")
$g2BluetoothDevices = @(Get-PresentDevices '(?i)Even Realities|Even G[12]')
$metaBluetoothDevices = @(Get-PresentDevices '(?i)Ray[ -]?Ban|Meta.*Glasses')
$androidPnpDevices = @(
  Get-PresentDevices '(?i)Android|ADB Interface|MTP USB|Portable Device' |
    Sort-Object FriendlyName -Unique
)

$g2Candidates = @()
for ($index = 0; $index -lt $androidBridges.Count; $index++) {
  $bridge = $androidBridges[$index]
  $g2PhoneReady = $bridge.authorized -and $bridge.hasEvenApp
  $g2Candidates += New-Candidate `
    -Id "g2-android-$($index + 1)" `
    -Name ([string]$bridge.displayName) `
    -Transport ([string]$bridge.transport) `
    -Status $(if ($g2PhoneReady) { "found" } else { "setup_required" }) `
    -ConnectionPath ([string]$bridge.connectionPath) `
    -LinkState ([string]$bridge.linkState) `
    -Detail $(if (-not $bridge.authorized) {
      "The phone is attached, but Android debugging is $($bridge.adbState). Unlock it and approve this tutor computer."
    } elseif ($bridge.hasEvenApp) {
      "The Even app is installed$(if ($bridge.evenAppRunning) { ' and running' } else { '' }). This confirms the Android path; recent Agent Mesh activity confirms the G2 companion path."
    } else {
      "The phone is authorized, but the Even app was not found. Install or open the approved G2 companion path, then scan again."
    })
}
if ($androidBridges.Count -eq 0) {
  for ($index = 0; $index -lt $androidPnpDevices.Count; $index++) {
    $g2Candidates += New-Candidate `
      -Id "g2-android-usb-pnp-$($index + 1)" `
      -Name "Android USB device $($index + 1)" `
      -Transport "Android phone / USB" `
      -Status "setup_required" `
      -ConnectionPath "android_usb" `
      -LinkState "attached" `
      -Detail "Windows sees an Android USB device, but ADB is unavailable or not authorized. Unlock the phone and approve USB debugging for connection diagnostics."
  }
}
for ($index = 0; $index -lt $g2BluetoothDevices.Count; $index++) {
  $g2Candidates += New-Candidate `
    -Id "g2-bluetooth-$($index + 1)" `
    -Name $(if ($g2BluetoothDevices[$index].FriendlyName) { [string]$g2BluetoothDevices[$index].FriendlyName } else { "Even G2 Bluetooth device" }) `
    -Transport "Bluetooth" `
    -Status "found" `
    -ConnectionPath "bluetooth" `
    -LinkState "connected" `
    -Detail "Windows currently reports a matching Bluetooth device present. The companion or Agent Mesh check-in still confirms application readiness."
}
for ($index = 0; $index -lt $g2Wearables.Count; $index++) {
  $g2Candidates += New-Candidate `
    -Id "g2-agent-mesh-$($index + 1)" `
    -Name "Provisioned G2 companion $($index + 1)" `
    -Transport "Android companion / Agent Mesh" `
    -Status $(if ($g2Wearables[$index].recentlyActive) { "found" } else { "ready" }) `
    -ConnectionPath "android" `
    -LinkState $(if ($g2Wearables[$index].recentlyActive) { "recently_active" } else { "provisioned" }) `
    -Detail $(if ($g2Wearables[$index].recentlyActive) { "A G2 companion used Agent Mesh within the current two-minute connection window." } else { "A G2 companion identity is configured but has not checked in during the current connection window." })
}
$g2PhoneReadyCount = @($androidBridges | Where-Object { $_.authorized -and $_.hasEvenApp }).Count
$g2RecentCount = @($g2Wearables | Where-Object recentlyActive).Count
$g2Status = if ($g2RecentCount -gt 0 -or $g2PhoneReadyCount -gt 0 -or $g2BluetoothDevices.Count -gt 0) {
  "found"
} elseif ($g2Wearables.Count -gt 0 -or $agentMeshListening) {
  "ready"
} else { "setup_required" }
$g2Summary = if ($g2RecentCount -gt 0) {
  "$g2RecentCount G2 companion profile(s) recently active through Agent Mesh."
} elseif ($g2PhoneReadyCount -gt 0) {
  "$g2PhoneReadyCount authorized Android phone path(s) have the Even app installed; use the glasses once to confirm a live G2 check-in."
} elseif ($g2BluetoothDevices.Count -gt 0) {
  "$($g2BluetoothDevices.Count) matching G2 Bluetooth device(s) are present in Windows."
} elseif ($g2Wearables.Count -gt 0) {
  "$($g2Wearables.Count) G2 companion profile(s) configured, but none recently active."
} elseif ($androidBridges.Count -gt 0 -or $androidPnpDevices.Count -gt 0) {
  "An Android phone is attached, but the G2 companion path still needs setup or authorization."
} elseif ($agentMeshListening) {
  "Agent Mesh is running; no G2 phone or recently active G2 profile was found."
} else {
  "No direct G2 Bluetooth, Android, or Agent Mesh connection evidence was found."
}
$integrations.Add((New-Integration `
  -Id "even-realities-g2" `
  -Name "Even Realities G2" `
  -Category "interaction" `
  -Status $g2Status `
  -Summary $g2Summary `
  -ConnectionMethod "Android, Bluetooth, or Agent Mesh" `
  -Candidates $g2Candidates `
  -SetupSteps @(
    "Start the provisioned Even companion bridge on the phone or classroom host.",
    "Wear the G2 and confirm that its interaction appears in Agent Mesh.",
    "Use the Coding agents card's Connect button; CIT then identifies the G2 by its device profile."
  ) `
  -SetupCommand 'pnpm hardware:glasses:windows -- -Mode Start -SharedFabricRoot "$env:LOCALAPPDATA\CITPhysicalXR\interaction-fabric"' `
  -SafetyNote "Only semantic interactions and bounded display text enter the Fabric; raw microphone data is not discovered."))

$metaCandidates = @()
for ($index = 0; $index -lt $androidBridges.Count; $index++) {
  $bridge = $androidBridges[$index]
  $metaPhoneReady = $bridge.authorized -and ($bridge.hasAgentMeshApp -or $bridge.hasMetaCameraApp)
  $installedParts = @()
  if ($bridge.hasAgentMeshApp) { $installedParts += "Agent Mesh companion$(if ($bridge.agentMeshAppRunning) { ' running' } else { '' })" }
  if ($bridge.hasMetaCameraApp) { $installedParts += "Meta camera companion$(if ($bridge.metaCameraAppRunning) { ' running' } else { '' })" }
  $metaCandidates += New-Candidate `
    -Id "meta-android-$($index + 1)" `
    -Name ([string]$bridge.displayName) `
    -Transport ([string]$bridge.transport) `
    -Status $(if ($metaPhoneReady) { "found" } else { "setup_required" }) `
    -ConnectionPath ([string]$bridge.connectionPath) `
    -LinkState ([string]$bridge.linkState) `
    -Detail $(if (-not $bridge.authorized) {
      "The phone is attached, but Android debugging is $($bridge.adbState). Unlock it and approve this tutor computer."
    } elseif ($metaPhoneReady) {
      "$($installedParts -join ' and ') detected. This confirms the Android path; recent Agent Mesh or camera activity confirms the glasses path."
    } else {
      "The phone is authorized, but no approved Meta CIT companion package was found. Run the Meta phone setup, then scan again."
    })
}
if ($androidBridges.Count -eq 0) {
  for ($index = 0; $index -lt $androidPnpDevices.Count; $index++) {
    $metaCandidates += New-Candidate `
      -Id "meta-android-usb-pnp-$($index + 1)" `
      -Name "Android USB device $($index + 1)" `
      -Transport "Android phone / USB" `
      -Status "setup_required" `
      -ConnectionPath "android_usb" `
      -LinkState "attached" `
      -Detail "Windows sees an Android USB device, but ADB is unavailable or not authorized. Unlock the phone and approve USB debugging for connection diagnostics."
  }
}
for ($index = 0; $index -lt $metaBluetoothDevices.Count; $index++) {
  $metaCandidates += New-Candidate `
    -Id "meta-bluetooth-$($index + 1)" `
    -Name $(if ($metaBluetoothDevices[$index].FriendlyName) { [string]$metaBluetoothDevices[$index].FriendlyName } else { "Meta Ray-Ban Bluetooth device" }) `
    -Transport "Bluetooth" `
    -Status "found" `
    -ConnectionPath "bluetooth" `
    -LinkState "connected" `
    -Detail "Windows currently reports a matching Bluetooth device present. The approved Android companion still confirms Meta application and media readiness."
}
for ($index = 0; $index -lt $metaWearables.Count; $index++) {
  $metaCandidates += New-Candidate `
    -Id "meta-agent-mesh-$($index + 1)" `
    -Name "Provisioned Meta companion $($index + 1)" `
    -Transport "Android companion / Agent Mesh" `
    -Status $(if ($metaWearables[$index].recentlyActive) { "found" } else { "ready" }) `
    -ConnectionPath "android" `
    -LinkState $(if ($metaWearables[$index].recentlyActive) { "recently_active" } else { "provisioned" }) `
    -Detail $(if ($metaWearables[$index].recentlyActive) { "A Meta companion used Agent Mesh within the current two-minute connection window." } else { "A Meta companion identity is configured but has not checked in during the current connection window." })
}
$metaPhoneReadyCount = @($androidBridges | Where-Object { $_.authorized -and ($_.hasAgentMeshApp -or $_.hasMetaCameraApp) }).Count
$metaRecentCount = @($metaWearables | Where-Object recentlyActive).Count
$metaStatus = if ($metaRecentCount -gt 0 -or $metaPhoneReadyCount -gt 0 -or $metaBluetoothDevices.Count -gt 0) {
  "found"
} elseif ($metaWearables.Count -gt 0 -or $agentMeshListening) {
  "ready"
} else { "setup_required" }
$metaSummary = if ($metaRecentCount -gt 0) {
  "$metaRecentCount Meta companion profile(s) recently active through Agent Mesh."
} elseif ($metaPhoneReadyCount -gt 0) {
  "$metaPhoneReadyCount authorized Android phone path(s) have an approved Meta CIT companion installed."
} elseif ($metaBluetoothDevices.Count -gt 0) {
  "$($metaBluetoothDevices.Count) matching Meta/Ray-Ban Bluetooth device(s) are present in Windows."
} elseif ($metaWearables.Count -gt 0) {
  "$($metaWearables.Count) Meta companion profile(s) configured, but none recently active."
} elseif ($androidBridges.Count -gt 0 -or $androidPnpDevices.Count -gt 0) {
  "An Android phone is attached, but the Meta companion path still needs setup or authorization."
} elseif ($agentMeshListening) {
  "Agent Mesh is running; no Meta phone or recently active Meta profile was found."
} else {
  "No direct Meta Bluetooth, Android, or Agent Mesh connection evidence was found."
}
$integrations.Add((New-Integration `
  -Id "meta-rayban" `
  -Name "Meta Ray-Ban" `
  -Category "interaction" `
  -Status $metaStatus `
  -Summary $metaSummary `
  -ConnectionMethod "Android, Bluetooth, or Agent Mesh" `
  -Candidates $metaCandidates `
  -SetupSteps @(
    "Start the approved Meta phone bridge and keep the phone on the classroom network.",
    "Wear the glasses and confirm that their interaction appears in Agent Mesh.",
    "Use the Coding agents card's Connect button; camera streaming remains an explicit separate media connection."
  ) `
  -SetupCommand 'pnpm hardware:glasses:windows -- -Mode Start -SharedFabricRoot "$env:LOCALAPPDATA\CITPhysicalXR\interaction-fabric"' `
  -SafetyNote "Agent Mesh carries semantic interactions only. Camera media uses the explicit media companion and is never recorded by discovery."))

# Local coding-agent executables. Running sessions appear only after Agent Mesh
# registers them, so installed is reported as ready rather than connected.
$agentCandidates = @()
foreach ($agent in @(
    @{ id = "codex-cli"; name = "Codex CLI"; command = "codex" },
    @{ id = "claude-code-cli"; name = "Claude Code CLI"; command = "claude" }
  )) {
  $installed = $null -ne (Get-Command $agent.command -ErrorAction SilentlyContinue)
  if ($installed) {
    $agentCandidates += New-Candidate `
      -Id $agent.id `
      -Name $agent.name `
      -Transport "Supervised local process" `
      -Status "ready" `
      -ConnectionPath "local_service" `
      -LinkState "ready" `
      -Detail "The executable is installed; start or select an approved workspace session to expose it to CIT."
  }
}
$selectableAgentSessionCount = if ($agentMeshListening) {
  Get-SelectableAgentSessionCount -Root $AgentMeshRoot
} else {
  0
}
if ($selectableAgentSessionCount -gt 0) {
  $agentCandidates += New-Candidate `
    -Id "agent-mesh-live-sessions" `
    -Name "$selectableAgentSessionCount active Agent Mesh session(s)" `
    -Transport "Local scoped control plane" `
    -Status "found" `
    -ConnectionPath "local_service" `
    -LinkState "connected" `
    -Detail "At least one approved live session can be attached to the Interaction Fabric; private workspace and prompt details were discarded."
}
$agentStatus = if ($agentCandidates.Count -gt 0) { "ready" } else { "setup_required" }
$installedAgentCount = @($agentCandidates | Where-Object candidateId -in @("codex-cli", "claude-code-cli")).Count
$agentSummary = if ($selectableAgentSessionCount -gt 0) {
  "$selectableAgentSessionCount approved live coding-agent session(s) available to connect."
} elseif ($installedAgentCount -gt 0) {
  "$installedAgentCount supported coding-agent executable(s) installed, but no live approved session is available."
} else {
  "No supported coding-agent executable was found on PATH."
}
$integrations.Add((New-Integration `
  -Id "coding-agents" `
  -Name "Codex and Claude coding agents" `
  -Category "coding_agent" `
  -Status $agentStatus `
  -Summary $agentSummary `
  -ConnectionMethod "Local supervised process" `
  -Candidates $agentCandidates `
  -SetupSteps @(
    "Start Codex or Claude in the approved lesson workspace.",
    "Start the glasses/Agent Mesh adapter and choose that session in the classroom UI."
  ) `
  -SetupCommand 'pnpm hardware:glasses:windows -- -Mode Start -SelectMostRecentAgentSession -SharedFabricRoot "$env:LOCALAPPDATA\CITPhysicalXR\interaction-fabric"' `
  -ActionId $(if ($selectableAgentSessionCount -gt 0) { "cit.glasses-agent.connect" } else { "" }) `
  -ActionLabel $(if ($selectableAgentSessionCount -gt 0) { "Connect glasses and agent" } else { "" }) `
  -SafetyNote "Discovery never starts an agent or grants filesystem, shell, or device credentials."))

# Leap Motion is detectable without opening the camera stream.
$leapDevices = @(Get-PresentDevices '(?i)Leap Motion|Ultraleap')
$leapServices = @(
  Get-Service -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '(?i)Leap|Ultraleap' -or $_.DisplayName -match '(?i)Leap|Ultraleap' }
)
$leapServiceRunning = @($leapServices | Where-Object Status -eq "Running").Count -gt 0
$leapBridge = Join-Path $RoboMasterRoot "build\leap_hand_bridge.dll"
$leapCandidates = @()
for ($index = 0; $index -lt $leapDevices.Count; $index++) {
  $leapCandidates += New-Candidate `
    -Id "leap-usb-$($index + 1)" `
    -Name $(if ($leapDevices[$index].FriendlyName) { [string]$leapDevices[$index].FriendlyName } else { "Leap Motion controller $($index + 1)" }) `
    -Transport "USB" `
    -Status $(if ($leapServiceRunning) { "found" } else { "setup_required" }) `
    -ConnectionPath "usb" `
    -LinkState "attached" `
    -Detail $(if ($leapServiceRunning) { "USB hardware and the Ultraleap tracking service are available." } else { "USB hardware is present, but the Ultraleap tracking service is not running." })
}
$leapCandidates += @(
  $leapServices | ForEach-Object {
    New-Candidate `
      -Id "leap-service:$($_.Name)" `
      -Name ([string]$_.DisplayName) `
      -Transport "Ultraleap Windows service" `
      -Status $(if ($_.Status -eq "Running") { "ready" } else { "setup_required" }) `
      -ConnectionPath "local_service" `
      -LinkState $(if ($_.Status -eq "Running") { "ready" } else { "provisioned" }) `
      -Detail $(if ($_.Status -eq "Running") { "The tracking service is running and ready for an attached controller." } else { "The tracking service is installed but stopped." })
  }
)
$leapStatus = if ($leapDevices.Count -gt 0 -and $leapServiceRunning -and (Test-Path -LiteralPath $leapBridge)) {
  "found"
} elseif ($leapServiceRunning -and (Test-Path -LiteralPath $leapBridge)) {
  "ready"
} else {
  "setup_required"
}
$integrations.Add((New-Integration `
  -Id "leap-motion" `
  -Name "Leap Motion" `
  -Category "interaction" `
  -Status $leapStatus `
  -Summary $(if ($leapDevices.Count -gt 0) { "$($leapDevices.Count) Leap/Ultraleap USB device(s) found; tracking service is $(if ($leapServiceRunning) { 'running' } else { 'stopped' })." } elseif ($leapServiceRunning) { "Ultraleap software is ready; no controller is visible over USB." } else { "No Leap controller or running Ultraleap service was found." }) `
  -ConnectionMethod "USB / Ultraleap service" `
  -Candidates $leapCandidates `
  -SetupSteps @(
    "Plug the controller directly into USB and start Ultraleap Tracking.",
    "Run the RoboMaster/Leap preflight before a lesson."
  ) `
  -SetupCommand 'pnpm hardware:robot:windows -- -Mode Preflight -Live -SharedFabricRoot "$env:LOCALAPPDATA\CITPhysicalXR\interaction-fabric" -FabricPort 8766' `
  -SafetyNote "The scan does not open the tracking stream and never creates a robot command."))

# RoboMaster detection is intentionally conservative: a generic LAN host is not
# called a robot. A matching DJI/RNDIS interface or network profile is evidence;
# otherwise only software readiness is reported.
$robotInterfaces = @(
  Get-NetAdapter -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Status -eq "Up" -and
      ($_.Name -match '(?i)RoboMaster|DJI' -or $_.InterfaceDescription -match '(?i)RoboMaster|DJI|RNDIS')
    }
)
$robotProfiles = @(
  Get-NetConnectionProfile -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '(?i)RoboMaster|DJI' }
)
$robotBroadcastCount = Get-RoboMasterBroadcastCount
$robotEvidenceCount = @($robotInterfaces).Count + @($robotProfiles).Count + $robotBroadcastCount
$robotCheckoutReady = Test-Path -LiteralPath (Join-Path $RoboMasterRoot "robomaster_gesture\__init__.py")
$robotCandidates = @()
for ($index = 0; $index -lt $robotInterfaces.Count; $index++) {
  $interface = $robotInterfaces[$index]
  $isUsbRobotLink = [string]$interface.InterfaceDescription -match '(?i)RNDIS|USB'
  $robotCandidates += New-Candidate `
    -Id "robomaster-interface-$($index + 1)" `
    -Name $(if ($interface.Name) { [string]$interface.Name } else { "RoboMaster network interface $($index + 1)" }) `
    -Transport $(if ($isUsbRobotLink) { "USB / RNDIS" } else { "Wi-Fi" }) `
    -Status "found" `
    -ConnectionPath $(if ($isUsbRobotLink) { "usb" } else { "wifi" }) `
    -LinkState "connected" `
    -Detail "A DJI-specific network interface is active; the connect-only preflight must still verify the robot."
}
for ($index = 0; $index -lt $robotProfiles.Count; $index++) {
  $robotCandidates += New-Candidate `
    -Id "robomaster-wifi-profile-$($index + 1)" `
    -Name "RoboMaster Wi-Fi link $($index + 1)" `
    -Transport "Wi-Fi" `
    -Status "found" `
    -ConnectionPath "wifi" `
    -LinkState "connected" `
    -Detail "Windows is currently connected through a DJI/RoboMaster network profile; the adapter handshake still confirms the robot."
}
for ($index = 0; $index -lt $robotBroadcastCount; $index++) {
  $robotCandidates += New-Candidate `
    -Id "robomaster-sta-broadcast-$($index + 1)" `
    -Name "RoboMaster STA announcement $($index + 1)" `
    -Transport "Wi-Fi / local network" `
    -Status "found" `
    -ConnectionPath "wifi" `
    -LinkState "visible" `
    -Detail "A robot announced itself on the DJI STA discovery port; no discovery or movement packet was sent by CIT."
}
$integrations.Add((New-Integration `
  -Id "robomaster-s1" `
  -Name "DJI RoboMaster S1" `
  -Category "robot" `
  -Status $(if ($robotEvidenceCount -gt 0) { "found" } elseif ($robotCheckoutReady) { "ready" } else { "setup_required" }) `
  -Summary $(if ($robotEvidenceCount -gt 0) { "$robotEvidenceCount DJI-specific network link(s) found." } elseif ($robotCheckoutReady) { "The characterized RoboMaster wrapper is installed; no unambiguous robot link is visible." } else { "The RoboMaster wrapper checkout is unavailable." }) `
  -ConnectionMethod "Wi-Fi, USB/RNDIS, or DJI app bridge" `
  -Candidates $robotCandidates `
  -SetupSteps @(
    "Power the robot on with its wheels raised for the first test.",
    "Choose STA, AP, RNDIS, or the stock S1 app transport.",
    "Run connect-only verification before enabling a physical lesson."
  ) `
  -SetupCommand 'pnpm hardware:robot:windows -- -Mode Preflight -Live -SharedFabricRoot "$env:LOCALAPPDATA\CITPhysicalXR\interaction-fabric" -FabricPort 8766' `
  -ActionId $(if ($robotBroadcastCount -gt 0 -and $leapStatus -eq "found") { "cit.robomaster-leap.connect" } else { "" }) `
  -ActionLabel $(if ($robotBroadcastCount -gt 0 -and $leapStatus -eq "found") { "Connect robot and Leap" } else { "" }) `
  -SafetyNote "A network match is not treated as proof of a robot. Only the adapter handshake can confirm it, and movement stays disarmed."))

# BOLT advertises a classroom-unique SB-XXXX name over BLE. Windows PnP
# presence is useful setup evidence, but it is not an adapter handshake and
# must never select a nearby robot or initiate a BLE connection on its own.
$spheroDevices = @(
  Get-PresentDevices '(?i)(?:Sphero(?: BOLT)?|(?:^|\s)BOLT(?:\s|$)|\bSB-[0-9A-F]{4}\b)'
)
$spheroCandidates = @()
for ($index = 0; $index -lt $spheroDevices.Count; $index++) {
  $spheroCandidates += New-Candidate `
    -Id "sphero-bolt-bluetooth-$($index + 1)" `
    -Name $(if ($spheroDevices[$index].FriendlyName) { [string]$spheroDevices[$index].FriendlyName } else { "Sphero BOLT $($index + 1)" }) `
    -Transport "Bluetooth Low Energy" `
    -Status "found" `
    -ConnectionPath "bluetooth" `
    -LinkState "visible" `
    -Detail "Windows reports a matching BOLT device. Its exact SB-XXXX name must still be selected by a CIT adapter before it becomes a lesson node."
}
$integrations.Add((New-Integration `
  -Id "sphero-bolt" `
  -Name "Sphero BOLT" `
  -Category "robot" `
  -Status $(if ($spheroDevices.Count -gt 0) { "found" } else { "setup_required" }) `
  -Summary $(if ($spheroDevices.Count -gt 0) { "$($spheroDevices.Count) Windows-visible Sphero BOLT device(s) found; no robot was connected or moved." } else { "No Windows-visible Sphero BOLT was found. Charge and wake the robot, then scan again." }) `
  -ConnectionMethod "Bluetooth Low Energy (BLE)" `
  -Candidates $spheroCandidates `
  -SetupSteps @(
    "Charge BOLT, wake it in its cradle, and keep the displayed SB-XXXX name visible.",
    "Close Sphero Edu, Sphero Play, or another program that is currently connected to this robot.",
    "Scan again, then select the exact SB-XXXX name through the CIT Sphero adapter when available."
  ) `
  -SafetyNote "Discovery reads Windows Bluetooth presence only. It never connects, wakes, rolls, aims, or changes LEDs."))

# Reuse Brain2Devices' characterized, credential-free Windows radio scan. It
# performs netsh/PnP inspection only and explicitly sends no SDK/flight packet.
$brainListening = Test-LocalTcpPort 8765
$telloCandidates = @()
$visibleTello = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$wifiRadioCount = 0
$savedTelloProfiles = 0
$telloScanAvailable = $false
$radioHelper = Join-Path $Brain2DevicesRoot "src\brain2devices\scripts\connect_tello_radios.ps1"
if ((Test-Path -LiteralPath $radioHelper) -and -not $SkipWifiScan) {
  $scanResultPath = Join-Path ([IO.Path]::GetTempPath()) "cit-tello-scan-$([Guid]::NewGuid().ToString('N')).json"
  try {
    & $radioHelper -Action Scan -TimeoutSeconds 20 -ResultPath $scanResultPath 2>$null | Out-Null
    $rawScan = [IO.File]::ReadAllText($scanResultPath, [Text.Encoding]::UTF8)
    $scan = $rawScan | ConvertFrom-Json -AsHashtable
    if (-not $scan.ok) { throw [InvalidOperationException]::new([string]$scan.error) }
    $telloScanAvailable = $true
    foreach ($radio in @($scan.adapters)) {
      $wifiRadioCount++
      $savedTelloProfiles += @($radio.saved_tello_profiles).Count
      $networkText = if ($radio.network_name) { "Currently joined to $($radio.network_name)." } else { "Not currently joined to an aircraft." }
      $telloCandidates += New-Candidate `
        -Id "tello-radio:$($radio.interface_name)" `
        -Name "$($radio.interface_name) · $($radio.interface_description)" `
        -Transport "USB Wi-Fi" `
        -Status $(if ($radio.route_ready) { "found" } else { "ready" }) `
        -ConnectionPath "wifi" `
        -LinkState $(if ($radio.route_ready) { "connected" } else { "ready" }) `
        -Detail "$networkText $(@($radio.saved_tello_profiles).Count) saved Tello profile(s)."
      foreach ($network in @($radio.visible_tello_networks)) {
        $null = $visibleTello.Add([string]$network)
        $signal = $null
        if ($radio.visible_tello_signals -and $radio.visible_tello_signals.ContainsKey([string]$network)) {
          $signal = [int]$radio.visible_tello_signals[[string]$network]
        }
        $telloCandidates += New-Candidate `
          -Id "tello-ssid:$($radio.interface_name):$network" `
          -Name ([string]$network) `
          -Transport "Tello Wi-Fi" `
          -Status "found" `
          -ConnectionPath "wifi" `
          -LinkState "visible" `
          -Detail "A powered, grounded aircraft network is visible to $($radio.interface_name)." `
          -SignalPercent $signal
      }
    }
  } catch {
    $warnings.Add("Tello Wi-Fi scan was unavailable: $([string]$_.Exception.Message). No SDK or flight command was sent.")
  } finally {
    if (Test-Path -LiteralPath $scanResultPath) {
      Remove-Item -LiteralPath $scanResultPath -Force
    }
  }
}

$brainState = $null
if ($brainListening) {
  try {
    $brainState = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/state" -TimeoutSec 4
  } catch {
    $warnings.Add("Brain2Devices is listening but its read-only state endpoint did not respond.")
  }
}
$connectedDrones = if ($null -ne $brainState -and $null -ne $brainState.fleet) {
  @($brainState.fleet.drones | Where-Object { $_.connection -in @("connected", "degraded") }).Count
} else { 0 }
for ($index = 0; $index -lt $connectedDrones; $index++) {
  $telloCandidates += New-Candidate `
    -Id "tello-sdk-session-$($index + 1)" `
    -Name "Connected Tello SDK session $($index + 1)" `
    -Transport "Wi-Fi / Brain2Devices" `
    -Status "found" `
    -ConnectionPath "wifi" `
    -LinkState "connected" `
    -Detail "Brain2Devices reports an active aircraft session; flight remains disarmed until a separate instructor safety step."
}
$primaryTelloRouteReady = (
  $null -ne $brainState -and
  $null -ne $brainState.drone -and
  $null -ne $brainState.drone.address -and
  [bool]$brainState.drone.address.resolved_ip_address
)
$telloStatus = if ($connectedDrones -gt 0 -or $visibleTello.Count -gt 0) {
  "found"
} elseif ($wifiRadioCount -gt 0) {
  "ready"
} elseif ($telloScanAvailable) {
  "not_found"
} else {
  "setup_required"
}
$telloSummary = if ($connectedDrones -gt 0) {
  "$connectedDrones Tello SDK session(s) are connected in Brain2Devices; start the CIT adapter before using lesson flows."
} elseif ($visibleTello.Count -gt 0) {
  "$($visibleTello.Count) powered Tello network(s) found across $wifiRadioCount physical Wi-Fi adapter(s)."
} elseif ($wifiRadioCount -gt 0) {
  "$wifiRadioCount physical Wi-Fi adapter(s) ready; no powered TELLO-* or RMTT-* network is visible."
} else {
  "No physical Wi-Fi adapter is available for a Tello route."
}
$telloAction = ""
$telloActionLabel = ""
if ($brainListening -and $visibleTello.Count -gt 0) {
  $telloAction = "brain2devices.tello.connect-all"
  $telloActionLabel = "Connect grounded drones"
} elseif ($brainListening -and $connectedDrones -eq 0 -and $primaryTelloRouteReady) {
  $telloAction = "brain2devices.tello.connect-primary"
  $telloActionLabel = "Connect current Tello route"
}
$integrations.Add((New-Integration `
  -Id "tello-drones" `
  -Name "DJI / Ryze Tello drones" `
  -Category "drone" `
  -Status $telloStatus `
  -Summary $telloSummary `
  -ConnectionMethod "One Wi-Fi route per aircraft" `
  -Candidates $telloCandidates `
  -SetupSteps @(
    "Remove propellers for the first connection test and power on each grounded aircraft.",
    "Use one physical USB Wi-Fi adapter per stock Tello, or unique station-mode addresses.",
    "Start Brain2Devices, scan again, then connect the grounded fleet."
  ) `
  -SetupCommand 'pnpm hardware:brain:windows -- -Mode Start' `
  -ActionId $telloAction `
  -ActionLabel $telloActionLabel `
  -RequiresGroundedConfirmation ($telloAction -ne "") `
  -SafetyNote "Discovery and connection send no takeoff, movement, landing, or emergency command. Flight remains a separate armed lesson step."))

# MindWave is visible through its vendor-provided loopback TGC boundary. A port
# check says TGC is listening; it does not claim that EEG is currently fresh.
$tgcListening = Test-LocalTcpPort 13854
$mindwaveDevices = @(Get-PresentDevices '(?i)MindWave|NeuroSky|ThinkGear')
$headsetConnected = $null -ne $brainState -and $brainState.headset.connection -in @("connected", "degraded")
$mindwaveCandidates = @()
for ($index = 0; $index -lt $mindwaveDevices.Count; $index++) {
  $mindwaveCandidates += New-Candidate `
    -Id "mindwave-paired-$($index + 1)" `
    -Name "Paired MindWave device $($index + 1)" `
    -Transport "Bluetooth / ThinkGear Connector" `
    -Status $(if ($tgcListening) { "found" } else { "setup_required" }) `
    -ConnectionPath "bluetooth" `
    -LinkState "connected" `
    -Detail $(if ($tgcListening) { "A paired device and the ThinkGear Connector endpoint are present." } else { "A paired device is present, but ThinkGear Connector is not listening." })
}
if ($tgcListening) {
  $mindwaveCandidates += New-Candidate `
    -Id "thinkgear-connector" `
    -Name "ThinkGear Connector" `
    -Transport "Local Bluetooth bridge" `
    -Status "ready" `
    -ConnectionPath "local_service" `
    -LinkState "ready" `
    -Detail "The vendor connector is listening locally; fresh Brain2Devices telemetry confirms the headset stream."
}
if ($headsetConnected) {
  $mindwaveCandidates += New-Candidate `
    -Id "mindwave-brain2devices-session" `
    -Name "MindWave data session" `
    -Transport "Bluetooth / Brain2Devices" `
    -Status "found" `
    -ConnectionPath "bluetooth" `
    -LinkState "connected" `
    -Detail "Brain2Devices reports the headset connected or degraded; inspect signal quality before teaching."
}
$mindwaveStatus = if ($headsetConnected -or ($mindwaveDevices.Count -gt 0 -and $tgcListening)) {
  "found"
} elseif ($tgcListening) {
  "ready"
} else {
  "setup_required"
}
$integrations.Add((New-Integration `
  -Id "mindwave-mobile2" `
  -Name "MindWave Mobile 2" `
  -Category "sensor" `
  -Status $mindwaveStatus `
  -Summary $(if ($headsetConnected) { "Brain2Devices reports a connected headset." } elseif ($tgcListening) { "ThinkGear Connector is listening; headset streaming has not yet been confirmed." } else { "ThinkGear Connector is not listening on localhost:13854." }) `
  -ConnectionMethod "Bluetooth through ThinkGear Connector" `
  -Candidates $mindwaveCandidates `
  -SetupSteps @(
    "Pair MindWave Mobile 2 in Windows Bluetooth settings.",
    "Start ThinkGear Connector and select the headset's outgoing COM port.",
    "Start Brain2Devices, then connect the headset."
  ) `
  -SetupCommand 'pnpm hardware:brain:windows -- -Mode Start' `
  -ActionId $(if ($brainListening -and $tgcListening -and -not $headsetConnected) { "brain2devices.mindwave.connect" } else { "" }) `
  -ActionLabel $(if ($brainListening -and $tgcListening -and -not $headsetConnected) { "Connect headset" } else { "" }) `
  -SafetyNote "Only vendor-labelled semantic metrics are surfaced. Discovery stores no raw biosignal samples."))

# Matter smart plugs use the CIT-owned local controller and the public Matter
# commissioning code printed on the product. No vendor account, local key, or
# cloud API is queried by discovery.
$matterControllerReady = $false
$matterInventory = $null
try {
  $matterHealth = Invoke-RestMethod -Uri "http://127.0.0.1:5580/health" -TimeoutSec 2
  $matterControllerReady = $matterHealth.version -eq "1.4.0"
  $runtimePython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
  if ($matterControllerReady -and (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
    $rawInventory = (& $runtimePython -m cit_matter_smart_plug.admin inventory --server-url ws://127.0.0.1:5580/ws 2>$null | Out-String)
    if ($LASTEXITCODE -eq 0 -and $rawInventory.Trim()) {
      $matterInventory = $rawInventory | ConvertFrom-Json -AsHashtable
    }
  }
} catch {
  $matterControllerReady = $false
}
$matterPlugs = if ($null -ne $matterInventory) { @($matterInventory.plugs) } else { @() }
$availableMatterPlugs = @($matterPlugs | Where-Object { $_.available })
$matterCandidates = @(
  $matterPlugs | ForEach-Object {
    New-Candidate `
      -Id ([string]$_.nodeId) `
      -Name ([string]$_.displayName) `
      -Transport "Local Matter / IPv6" `
      -Status $(if ($_.available) { "ready" } else { "found" }) `
      -ConnectionPath "wifi" `
      -LinkState $(if ($_.available) { "connected" } else { "provisioned" }) `
      -Detail $(if ($_.available) { "Commissioned to the local CIT fabric and reachable without a vendor cloud." } else { "Commissioned, but currently offline. Check power and the classroom network." })
  }
)
$matterStatus = if ($availableMatterPlugs.Count -gt 0) {
  "ready"
} elseif ($matterControllerReady) {
  "setup_required"
} else {
  "setup_required"
}
$integrations.Add((New-Integration `
  -Id "matter-smart-plugs" `
  -Name "Matter smart plugs (cloud-free)" `
  -Category "smart_device" `
  -Status $matterStatus `
  -Summary $(if ($availableMatterPlugs.Count -gt 0) { "$($availableMatterPlugs.Count) commissioned Matter plug endpoint(s) are reachable through the local CIT controller." } elseif ($matterControllerReady) { "The local Matter controller is ready. Put a Matter-certified plug in pairing mode and add its printed setup code below." } else { "The local Matter controller is not running yet. The CIT classroom launcher starts it automatically." }) `
  -ConnectionMethod "Local Matter over Wi-Fi / IPv6" `
  -Candidates $matterCandidates `
  -SetupSteps @(
    "Use a plug whose packaging or label explicitly shows the Matter logo and setup code.",
    "Connect this Windows computer to the classroom network and put the plug in pairing mode.",
    "Enter the printed Matter setup code in Classroom Control; no vendor app or account is required."
  ) `
  -ActionId $(if ($availableMatterPlugs.Count -gt 0) { "cit.matter-smart-plug.connect" } else { "" }) `
  -ActionLabel $(if ($availableMatterPlugs.Count -gt 0) { "Connect commissioned plugs" } else { "" }) `
  -SafetyNote "Commissioning never turns a load on. Connecting a commissioned plug places the approved outlet in the off safe state."))

# LEGO remains configuration-bound by advertised hub name; a broad BLE nearest-
# device selection would be unsafe in a classroom with several identical hubs.
$legoDevices = @(Get-PresentDevices '(?i)LEGO|SPIKE|MINDSTORMS|Technic Hub|Pybricks')
$legoProfilePath = Join-Path (Split-Path $StateRoot -Parent) "lego-pybricks\profile.json"
$legoConfigured = Test-Path -LiteralPath $legoProfilePath -PathType Leaf
$legoCandidates = @()
for ($index = 0; $index -lt $legoDevices.Count; $index++) {
  $legoCandidates += New-Candidate `
    -Id "lego-paired-$($index + 1)" `
    -Name $(if ($legoDevices[$index].FriendlyName) { [string]$legoDevices[$index].FriendlyName } else { "Paired LEGO hub $($index + 1)" }) `
    -Transport "Bluetooth" `
    -Status "found" `
    -ConnectionPath "bluetooth" `
    -LinkState "connected" `
    -Detail "A matching paired device is present; bind it by its classroom hub name before connecting."
}
$integrations.Add((New-Integration `
  -Id "lego-hubs" `
  -Name "LEGO SPIKE and MINDSTORMS" `
  -Category "robot" `
  -Status $(if ($legoDevices.Count -gt 0) { "found" } elseif ($legoConfigured) { "ready" } else { "setup_required" }) `
  -Summary $(if ($legoDevices.Count -gt 0) { "$($legoDevices.Count) paired LEGO/Pybricks device(s) found." } elseif ($legoConfigured) { "An exact-name LEGO profile is ready; power on the configured hub before connecting." } else { "No paired LEGO/Pybricks hub was found; BLE scanning does not auto-select a nearest hub." }) `
  -ConnectionMethod "Bluetooth / Pybricks" `
  -Candidates $legoCandidates `
  -SetupSteps @(
    "Install Pybricks firmware on the supported hub.",
    "Give each classroom hub a unique advertised name and bind that exact name in configuration.",
    "Keep motors raised or disconnected for the first framed-protocol test."
  ) `
  -ActionId $(if ($legoConfigured) { "cit.lego-pybricks.connect" } else { "" }) `
  -ActionLabel $(if ($legoConfigured) { "Connect configured hub" } else { "" }) `
  -SafetyNote "Discovery never chooses the nearest anonymous BLE hub and never arms a motor."))

$report = [ordered]@{
  schemaVersion = "1.0"
  scanId = [Guid]::NewGuid().ToString()
  scannedAt = [DateTimeOffset]::UtcNow.ToString("o")
  hostId = if ($env:COMPUTERNAME) { $env:COMPUTERNAME } else { "windows-host" }
  platform = "windows"
  physicalActuationEnabled = $false
  integrations = @($integrations)
  warnings = @($warnings)
}
[Console]::Out.Write(($report | ConvertTo-Json -Depth 12 -Compress))

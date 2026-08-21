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
  try {
    return @(
      Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Where-Object { [string]$_.FriendlyName -match $Pattern }
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

function Get-TuyaBroadcastCount([int]$TimeoutMilliseconds = 1800) {
  $addresses = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $listeners = [Collections.Generic.List[Net.Sockets.UdpClient]]::new()
  try {
    foreach ($port in @(6666, 6667, 7000)) {
      $listener = $null
      try {
        $listener = [Net.Sockets.UdpClient]::new()
        $listener.ExclusiveAddressUse = $false
        $listener.Client.SetSocketOption(
          [Net.Sockets.SocketOptionLevel]::Socket,
          [Net.Sockets.SocketOptionName]::ReuseAddress,
          $true
        )
        $listener.Client.Bind([Net.IPEndPoint]::new([Net.IPAddress]::Any, $port))
        $listeners.Add($listener)
        $listener = $null
      } catch {
        if ($null -ne $listener) { $listener.Dispose() }
      }
    }
    if ($listeners.Count -eq 0) { return 0 }

    $deadline = [DateTimeOffset]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
      foreach ($listener in $listeners) {
        try {
          while ($listener.Available -gt 0) {
            $remote = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
            $payload = $listener.Receive([ref]$remote)
            if (
              $payload.Length -gt 0 -and
              $payload.Length -le 65535 -and
              -not [Net.IPAddress]::IsLoopback($remote.Address)
            ) {
              $null = $addresses.Add($remote.Address.ToString())
            }
          }
        } catch [Net.Sockets.SocketException] {
          continue
        }
      }
      Start-Sleep -Milliseconds 40
    }
  } finally {
    foreach ($listener in $listeners) { $listener.Dispose() }
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
  [Nullable[int]]$SignalPercent = $null
) {
  $candidate = [ordered]@{
    candidateId = $Id
    displayName = $Name
    transport = $Transport
    status = $Status
    detail = $Detail
  }
  if ($null -ne $SignalPercent) { $candidate.signalPercent = [int]$SignalPercent }
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

# Glasses and their phone/Agent Mesh bridge. Device identifiers are deliberately
# not returned; the Fabric adapter supplies pseudonymous node IDs after attach.
$agentMeshListening = Test-LocalTcpPort 7342
$adbCommand = Get-Command adb -ErrorAction SilentlyContinue
$androidCount = 0
if ($null -ne $adbCommand) {
  try {
    $androidCount = @(
      & $adbCommand.Source devices 2>$null |
        Select-Object -Skip 1 |
        Where-Object { $_ -match "\tdevice$" }
    ).Count
  } catch {
    $androidCount = 0
  }
}
$glassesCandidates = @()
for ($index = 1; $index -le $androidCount; $index++) {
  $glassesCandidates += New-Candidate `
    -Id "android-bridge-$index" `
    -Name "Authorized Android bridge $index" `
    -Transport "USB / ADB" `
    -Status "found" `
    -Detail "An authorized phone bridge is attached; open the glasses companion before connecting its CIT adapter."
}
$glassesStatus = if ($androidCount -gt 0) { "found" } elseif ($agentMeshListening) { "ready" } else { "setup_required" }
$glassesSummary = if ($androidCount -gt 0) {
  "$androidCount authorized phone bridge(s) found; Agent Mesh is $(if ($agentMeshListening) { 'running' } else { 'not running' })."
} elseif ($agentMeshListening) {
  "Agent Mesh is running; no authorized Android phone is attached right now."
} else {
  "The phone/Agent Mesh bridge is not ready on this computer."
}
$integrations.Add((New-Integration `
  -Id "even-meta-glasses" `
  -Name "Even G2 and Meta glasses" `
  -Category "interaction" `
  -Status $glassesStatus `
  -Summary $glassesSummary `
  -ConnectionMethod "Phone bridge / Agent Mesh" `
  -Candidates $glassesCandidates `
  -SetupSteps @(
    "Connect the provisioned phone by USB or use its existing network bridge.",
    "Open or wear the glasses so the companion reports a recent device.",
    "Start the glasses adapter; CIT will list each wearable separately."
  ) `
  -SetupCommand 'pnpm hardware:glasses:windows -- -Mode Start -SharedFabricRoot "$env:LOCALAPPDATA\CITPhysicalXR\interaction-fabric"' `
  -SafetyNote "Only semantic intents and bounded display text enter the Fabric; raw audio and camera media are not discovered."))

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
    -Detail $(if ($leapServiceRunning) { "USB hardware and the Ultraleap tracking service are available." } else { "USB hardware is present, but the Ultraleap tracking service is not running." })
}
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
for ($index = 0; $index -lt $robotEvidenceCount; $index++) {
  $robotCandidates += New-Candidate `
    -Id "robomaster-link-$($index + 1)" `
    -Name "RoboMaster network link $($index + 1)" `
    -Transport "Wi-Fi or USB/RNDIS" `
    -Status "found" `
    -Detail "A DJI-specific local network link is active; the connect-only preflight must still verify the robot."
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
    -Detail $(if ($tgcListening) { "A paired device and the ThinkGear Connector endpoint are present." } else { "A paired device is present, but ThinkGear Connector is not listening." })
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

# Smart plugs require one exact encrypted local profile. A short passive UDP
# listen may count Tuya-family announcements, but never returns their address or
# treats a broadcast as authenticated. Blind LAN control and browser credential
# collection remain prohibited.
$tuyaBroadcastCount = Get-TuyaBroadcastCount
$citStateBase = Split-Path $StateRoot -Parent
$plugRoots = [Collections.Generic.List[string]]::new()
$legacyPlugRoot = Join-Path $citStateBase "smart-plug"
if (Test-Path -LiteralPath $legacyPlugRoot) { $plugRoots.Add($legacyPlugRoot) }
$multiPlugRoot = Join-Path $citStateBase "smart-plugs"
if (Test-Path -LiteralPath $multiPlugRoot) {
  Get-ChildItem -LiteralPath $multiPlugRoot -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { $plugRoots.Add($_.FullName) }
}
$plugCandidates = @()
$configuredPlugCount = 0
if ($tuyaBroadcastCount -gt 0) {
  $plugCandidates += New-Candidate `
    -Id "tuya-lan-announcements" `
    -Name "$tuyaBroadcastCount possible Tuya LAN device(s)" `
    -Transport "Passive local UDP announcement" `
    -Status "setup_required" `
    -Detail "A compatible-port announcement was heard, but it is not authenticated. Configure the exact approved plug before CIT connects it."
}
foreach ($plugRoot in $plugRoots) {
  $settingsPath = Join-Path $plugRoot "state.json"
  $secretPath = Join-Path $plugRoot "secrets\tuya-device.dpapi"
  if (-not (Test-Path -LiteralPath $settingsPath) -or -not (Test-Path -LiteralPath $secretPath)) { continue }
  try {
    $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json -AsHashtable
    if (-not $settings.vendor -or -not $settings.model -or -not $settings.deviceAddress) { continue }
    $configuredPlugCount++
    $plugCandidates += New-Candidate `
      -Id "configured-plug-$configuredPlugCount" `
      -Name "$($settings.vendor) · $($settings.model)" `
      -Transport "Tuya LAN" `
      -Status "ready" `
      -Detail "An encrypted current-user profile is configured. The address and local key are not returned by discovery."
  } catch {
    $warnings.Add("One smart-plug profile is invalid and must be configured again.")
  }
}
$integrations.Add((New-Integration `
  -Id "tuya-gosund-plugs" `
  -Name "Tuya and Gosund smart plugs" `
  -Category "smart_device" `
  -Status $(if ($configuredPlugCount -gt 0) { "ready" } elseif ($tuyaBroadcastCount -gt 0) { "found" } else { "setup_required" }) `
  -Summary $(if ($configuredPlugCount -gt 0) { "$configuredPlugCount approved encrypted smart-plug profile(s) are ready for a read-only probe." } elseif ($tuyaBroadcastCount -gt 0) { "$tuyaBroadcastCount possible Tuya-family LAN device announcement(s) heard; exact approved profiles are still required." } else { "No approved Tuya/Gosund local profile is configured. Network presence alone cannot authenticate a plug." }) `
  -ConnectionMethod "Local Tuya LAN profile" `
  -Candidates $plugCandidates `
  -SetupSteps @(
    "Choose only an approved low-risk classroom load.",
    "Configure the plug's IPv4 address, device ID, local key, protocol version, and switch DPS once.",
    "Run the read-only preflight before starting its adapter."
  ) `
  -SetupCommand $(if ($configuredPlugCount -gt 0) { 'pnpm hardware:plug:windows -- -Mode Start -Live -ConnectOnly -NoOpenConsole' } else { 'pnpm hardware:plug:windows -- -Mode Configure' }) `
  -ActionId $(if ($configuredPlugCount -gt 0) { "cit.smart-plug.connect" } else { "" }) `
  -ActionLabel $(if ($configuredPlugCount -gt 0) { "Connect approved plug" } else { "" }) `
  -SafetyNote "CIT does not guess keys, accept them in the browser, or switch power during discovery."))

# LEGO remains configuration-bound by advertised hub name; a broad BLE nearest-
# device selection would be unsafe in a classroom with several identical hubs.
$legoDevices = @(Get-PresentDevices '(?i)LEGO|SPIKE|MINDSTORMS|Technic Hub|Pybricks')
$legoCandidates = @()
for ($index = 0; $index -lt $legoDevices.Count; $index++) {
  $legoCandidates += New-Candidate `
    -Id "lego-paired-$($index + 1)" `
    -Name $(if ($legoDevices[$index].FriendlyName) { [string]$legoDevices[$index].FriendlyName } else { "Paired LEGO hub $($index + 1)" }) `
    -Transport "Bluetooth" `
    -Status "found" `
    -Detail "A matching paired device is present; bind it by its classroom hub name before connecting."
}
$integrations.Add((New-Integration `
  -Id "lego-hubs" `
  -Name "LEGO SPIKE and MINDSTORMS" `
  -Category "robot" `
  -Status $(if ($legoDevices.Count -gt 0) { "found" } else { "setup_required" }) `
  -Summary $(if ($legoDevices.Count -gt 0) { "$($legoDevices.Count) paired LEGO/Pybricks device(s) found." } else { "No paired LEGO/Pybricks hub was found; BLE scanning does not auto-select a nearest hub." }) `
  -ConnectionMethod "Bluetooth / Pybricks" `
  -Candidates $legoCandidates `
  -SetupSteps @(
    "Install Pybricks firmware on the supported hub.",
    "Give each classroom hub a unique advertised name and bind that exact name in configuration.",
    "Keep motors raised or disconnected for the first framed-protocol test."
  ) `
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

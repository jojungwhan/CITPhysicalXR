#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Show", "Describe")]
  [string]$Mode = "Show",
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8766,
  [string]$StateRoot = "",
  [ValidateRange(30, 1800)]
  [int]$OperationTimeoutSeconds = 240
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$deviceLauncher = Join-Path $PSScriptRoot "classroom-devices.ps1"
$metaCameraInstaller = Join-Path $PSScriptRoot "meta-camera-companion.ps1"
if (-not $StateRoot) {
  $StateRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
}
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$fabricOrigin = "http://127.0.0.1:$FabricPort"

function Get-ClassroomHostState {
  try {
    $health = Invoke-RestMethod -Uri "$fabricOrigin/api/v1/fabric/healthz" -TimeoutSec 2
    if ($health.status -ne "ok") {
      throw "The local port belongs to another service."
    }
    $mediaIngressEnabled = $health.PSObject.Properties.Name -contains "mediaIngress" -and
      $health.mediaIngress -eq "enabled"
    if (
      $health.physicalActuation -eq "enabled" -and
      $mediaIngressEnabled
    ) {
      return [ordered]@{
        state = "ready"
        heading = "Classroom devices are ready"
        detail = "The local device host is running, including scoped phone-camera access. Devices and lessons remain disarmed until you enable them in Classroom Control."
        primaryAction = "Open"
        primaryLabel = "Open Classroom Control"
      }
    }
    if ($health.physicalActuation -eq "enabled") {
      return [ordered]@{
        state = "camera_limited"
        heading = "Phone cameras need a safe restart"
        detail = "Choose Enable classroom devices to add scoped local-network camera access. Existing sessions will stop and every physical output will remain disarmed."
        primaryAction = "Enable"
        primaryLabel = "Enable phone cameras and devices"
      }
    }
    return [ordered]@{
      state = "simulation_only"
      heading = "Real devices are currently disabled"
      detail = "Choose Enable classroom devices to restart the local host safely. Existing sessions will be stopped and physical outputs will remain disarmed."
      primaryAction = "Enable"
      primaryLabel = "Enable classroom devices"
    }
  } catch {
    return [ordered]@{
      state = "offline"
      heading = "Classroom Control is not running"
      detail = "Choose Start classroom devices. CIT will prepare the local services and open the tutor screen automatically."
      primaryAction = "Start"
      primaryLabel = "Start classroom devices"
    }
  }
}

if ($Mode -eq "Describe") {
  [Console]::Out.Write(((Get-ClassroomHostState) | ConvertTo-Json -Compress))
  exit 0
}

if (-not $IsWindows) {
  throw "The CIT Classroom Control button currently requires Windows 11."
}
if (-not (Test-Path -LiteralPath $deviceLauncher -PathType Leaf)) {
  throw "The fixed classroom device launcher is missing."
}
$pwshCommand = Get-Command pwsh -ErrorAction Stop

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()

$form = [Windows.Forms.Form]::new()
$form.Text = "CIT Classroom Control"
$form.StartPosition = "CenterScreen"
$form.ClientSize = [Drawing.Size]::new(660, 510)
$form.MinimumSize = [Drawing.Size]::new(676, 549)
$form.BackColor = [Drawing.Color]::FromArgb(15, 24, 18)
$form.ForeColor = [Drawing.Color]::FromArgb(235, 244, 237)
$form.Font = [Drawing.Font]::new("Segoe UI", 10)
$form.MaximizeBox = $false

$brand = [Windows.Forms.Label]::new()
$brand.Text = "CIT CLASSROOM"
$brand.Location = [Drawing.Point]::new(42, 32)
$brand.Size = [Drawing.Size]::new(560, 24)
$brand.Font = [Drawing.Font]::new("Segoe UI Semibold", 10)
$brand.ForeColor = [Drawing.Color]::FromArgb(158, 234, 100)
$form.Controls.Add($brand)

$title = [Windows.Forms.Label]::new()
$title.Text = "Start your classroom devices"
$title.Location = [Drawing.Point]::new(39, 58)
$title.Size = [Drawing.Size]::new(570, 48)
$title.Font = [Drawing.Font]::new("Segoe UI Semibold", 22)
$form.Controls.Add($title)

$intro = [Windows.Forms.Label]::new()
$intro.Text = "No PowerShell is required. This button starts the local CIT services and opens the same control screen for glasses, sensors, robots, drones, plugs, LEGO, and coding agents."
$intro.Location = [Drawing.Point]::new(42, 112)
$intro.Size = [Drawing.Size]::new(570, 55)
$intro.ForeColor = [Drawing.Color]::FromArgb(170, 186, 174)
$form.Controls.Add($intro)

$statusPanel = [Windows.Forms.Panel]::new()
$statusPanel.Location = [Drawing.Point]::new(42, 179)
$statusPanel.Size = [Drawing.Size]::new(570, 91)
$statusPanel.BackColor = [Drawing.Color]::FromArgb(23, 36, 27)
$form.Controls.Add($statusPanel)

$statusHeading = [Windows.Forms.Label]::new()
$statusHeading.Location = [Drawing.Point]::new(18, 13)
$statusHeading.Size = [Drawing.Size]::new(530, 24)
$statusHeading.Font = [Drawing.Font]::new("Segoe UI Semibold", 11)
$statusPanel.Controls.Add($statusHeading)

$statusDetail = [Windows.Forms.Label]::new()
$statusDetail.Location = [Drawing.Point]::new(18, 40)
$statusDetail.Size = [Drawing.Size]::new(530, 43)
$statusDetail.ForeColor = [Drawing.Color]::FromArgb(155, 174, 160)
$statusPanel.Controls.Add($statusDetail)

$primaryButton = [Windows.Forms.Button]::new()
$primaryButton.Location = [Drawing.Point]::new(42, 287)
$primaryButton.Size = [Drawing.Size]::new(570, 62)
$primaryButton.FlatStyle = "Flat"
$primaryButton.FlatAppearance.BorderSize = 0
$primaryButton.BackColor = [Drawing.Color]::FromArgb(158, 234, 100)
$primaryButton.ForeColor = [Drawing.Color]::FromArgb(16, 32, 19)
$primaryButton.Font = [Drawing.Font]::new("Segoe UI Semibold", 12)
$primaryButton.Cursor = [Windows.Forms.Cursors]::Hand
$form.Controls.Add($primaryButton)

$metaSetupButton = [Windows.Forms.Button]::new()
$metaSetupButton.Text = "One-time setup: Meta glasses camera"
$metaSetupButton.Location = [Drawing.Point]::new(42, 361)
$metaSetupButton.Size = [Drawing.Size]::new(570, 44)
$metaSetupButton.FlatStyle = "Flat"
$metaSetupButton.ForeColor = [Drawing.Color]::FromArgb(185, 223, 255)
$metaSetupButton.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(63, 91, 72)
$metaSetupButton.Font = [Drawing.Font]::new("Segoe UI Semibold", 10)
$metaSetupButton.Cursor = [Windows.Forms.Cursors]::Hand
$metaSetupButton.Enabled = Test-Path -LiteralPath $metaCameraInstaller -PathType Leaf
$form.Controls.Add($metaSetupButton)

$safety = [Windows.Forms.Label]::new()
$safety.Text = "Connection only: no robot movement, drone flight, plug switching, or agent session starts automatically."
$safety.Location = [Drawing.Point]::new(42, 423)
$safety.Size = [Drawing.Size]::new(455, 55)
$safety.ForeColor = [Drawing.Color]::FromArgb(142, 159, 146)
$form.Controls.Add($safety)

$refreshButton = [Windows.Forms.Button]::new()
$refreshButton.Text = "Check again"
$refreshButton.Location = [Drawing.Point]::new(505, 435)
$refreshButton.Size = [Drawing.Size]::new(107, 31)
$refreshButton.FlatStyle = "Flat"
$refreshButton.ForeColor = [Drawing.Color]::FromArgb(185, 223, 255)
$refreshButton.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(63, 91, 72)
$form.Controls.Add($refreshButton)

$script:currentState = $null
$script:operation = $null
$script:operationDeadline = [DateTime]::MaxValue
$script:diagnosticsRoot = Join-Path ([IO.Path]::GetTempPath()) "cit-classroom-control"
$script:stdoutPath = Join-Path $script:diagnosticsRoot "launcher.stdout.log"
$script:stderrPath = Join-Path $script:diagnosticsRoot "launcher.stderr.log"

function Read-LauncherDiagnostics([string]$Path) {
  # The launcher has only just exited, so its log file can still be held open
  # for a moment. Share the handle and retry briefly rather than losing the
  # message that tells the technician what actually went wrong.
  foreach ($attempt in 1..5) {
    try {
      if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return "" }
      $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::ReadWrite
      )
      try {
        $reader = [IO.StreamReader]::new($stream)
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
      } finally {
        $stream.Dispose()
      }
    } catch {
      if ($attempt -eq 5) { return "" }
      Start-Sleep -Milliseconds 150
    }
  }
  return ""
}

function Update-ClassroomStatus {
  $script:currentState = Get-ClassroomHostState
  $statusHeading.Text = [string]$script:currentState.heading
  $statusDetail.Text = [string]$script:currentState.detail
  $primaryButton.Text = [string]$script:currentState.primaryLabel
  $primaryButton.Enabled = $true
  $refreshButton.Enabled = $true
}

function Start-FixedClassroomAction(
  [ValidateSet("Start", "Enable", "Open")]
  [string]$Action
) {
  $primaryButton.Enabled = $false
  $refreshButton.Enabled = $false
  $primaryButton.Text = if ($Action -eq "Open") { "Opening…" } else { "Starting safely…" }
  $statusHeading.Text = if ($Action -eq "Open") { "Opening Classroom Control" } else { "Preparing local device services" }
  $statusDetail.Text = "This usually takes a few seconds. Keep this window open until the browser appears."
  [Windows.Forms.Application]::DoEvents()

  $arguments = @(
    "-NoProfile",
    "-NonInteractive",
    "-File",
    $deviceLauncher,
    "-Mode",
    $Action,
    "-FabricPort",
    [string]$FabricPort,
    "-StateRoot",
    $StateRoot
  )
  if ($Action -eq "Start") { $arguments += "-AllowPhysical" }

  # The launcher starts long-running classroom services, and those
  # grandchildren inherit the handles it holds. A redirected pipe would
  # therefore never reach EOF, so reading one to the end on this thread would
  # block forever and leave the window stuck on a disabled button. Files carry
  # the diagnostics instead, and are read only after the launcher exits.
  New-Item -ItemType Directory -Path $script:diagnosticsRoot -Force | Out-Null
  foreach ($path in @($script:stdoutPath, $script:stderrPath)) {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
  }

  $script:operationDeadline = (Get-Date).AddSeconds($OperationTimeoutSeconds)
  $script:operation = Start-Process `
    -FilePath $pwshCommand.Source `
    -ArgumentList $arguments `
    -WorkingDirectory $repositoryRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $script:stdoutPath `
    -RedirectStandardError $script:stderrPath `
    -PassThru
  if ($null -eq $script:operation) { throw "The fixed classroom launcher could not start." }
}

$operationTimer = [Windows.Forms.Timer]::new()
$operationTimer.Interval = 300
$operationTimer.Add_Tick({
    if ($null -eq $script:operation) { return }
    $timedOut = (Get-Date) -gt $script:operationDeadline
    if (-not $script:operation.HasExited -and -not $timedOut) { return }
    $operationTimer.Stop()

    $exitCode = -1
    $standardError = ""
    try {
      if ($script:operation.HasExited) {
        $exitCode = $script:operation.ExitCode
        $standardError = Read-LauncherDiagnostics $script:stderrPath
      } else {
        $standardError = "The classroom launcher is still running after $OperationTimeoutSeconds seconds. Ask the classroom technician to check the CIT installation."
      }
    } catch {
      $standardError = $_.Exception.Message
    } finally {
      # Whatever happened above, the operator gets the window back. Leaving
      # the buttons disabled here is what makes the app look frozen.
      try { $script:operation.Dispose() } catch { }
      $script:operation = $null
      $script:operationDeadline = [DateTime]::MaxValue
      Update-ClassroomStatus
    }

    if ($exitCode -eq 0) { return }
    $diagnostics = @($standardError -split "\r?\n" | Where-Object { $_ })
    $message = if ($diagnostics.Count -gt 0) {
      ($diagnostics | Select-Object -Last 4) -join [Environment]::NewLine
    } else {
      "The local device host did not start. Ask the classroom technician to check the CIT installation."
    }
    [Windows.Forms.MessageBox]::Show(
      $form,
      $message,
      "CIT could not start classroom devices",
      [Windows.Forms.MessageBoxButtons]::OK,
      [Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
  })

$primaryButton.Add_Click({
    $action = [string]$script:currentState.primaryAction
    if ($action -eq "Enable") {
      $choice = [Windows.Forms.MessageBox]::Show(
        $form,
        "CIT will stop current local sessions, restart in physical-adapter mode, and keep every output disarmed. Continue?",
        "Enable classroom devices",
        [Windows.Forms.MessageBoxButtons]::YesNo,
        [Windows.Forms.MessageBoxIcon]::Warning
      )
      if ($choice -ne [Windows.Forms.DialogResult]::Yes) { return }
    }
    try {
      Start-FixedClassroomAction -Action $action
      $operationTimer.Start()
    } catch {
      Update-ClassroomStatus
      [Windows.Forms.MessageBox]::Show(
        $form,
        $_.Exception.Message,
        "CIT could not open Classroom Control",
        [Windows.Forms.MessageBoxButtons]::OK,
        [Windows.Forms.MessageBoxIcon]::Error
      ) | Out-Null
    }
  })
$metaSetupButton.Add_Click({
    $choice = [Windows.Forms.MessageBox]::Show(
      $form,
      "This one-time technician setup installs the Meta-enabled CIT companion on an Android phone connected by USB. You will be asked for a GitHub package token; it is held only in that setup process. Continue?",
      "Set up Meta glasses camera",
      [Windows.Forms.MessageBoxButtons]::YesNo,
      [Windows.Forms.MessageBoxIcon]::Information
    )
    if ($choice -ne [Windows.Forms.DialogResult]::Yes) { return }
    try {
      $startInfo = [Diagnostics.ProcessStartInfo]::new()
      $startInfo.FileName = $pwshCommand.Source
      $startInfo.WorkingDirectory = $repositoryRoot
      $startInfo.UseShellExecute = $true
      foreach ($argument in @(
          "-NoProfile",
          "-NoExit",
          "-File",
          $metaCameraInstaller,
          "-Mode",
          "Install",
          "-DeveloperMode"
        )) {
        $startInfo.ArgumentList.Add($argument)
      }
      if ($null -eq [Diagnostics.Process]::Start($startInfo)) {
        throw "The Meta camera setup window could not start."
      }
    } catch {
      [Windows.Forms.MessageBox]::Show(
        $form,
        $_.Exception.Message,
        "CIT could not start Meta camera setup",
        [Windows.Forms.MessageBoxButtons]::OK,
        [Windows.Forms.MessageBoxIcon]::Error
      ) | Out-Null
    }
  })
$refreshButton.Add_Click({ Update-ClassroomStatus })
$form.Add_FormClosing({
    param($sender, $event)
    if ($null -eq $script:operation -or $script:operation.HasExited) { return }
    # Warn, but never refuse. A window that cannot be closed is worse than a
    # startup that carries on in the background.
    $choice = [Windows.Forms.MessageBox]::Show(
      $form,
      "CIT is still preparing the local services. Close anyway? Services that already started keep running.",
      "Startup in progress",
      [Windows.Forms.MessageBoxButtons]::YesNo,
      [Windows.Forms.MessageBoxIcon]::Warning
    )
    if ($choice -ne [Windows.Forms.DialogResult]::Yes) { $event.Cancel = $true }
  })

Update-ClassroomStatus
[void]$form.ShowDialog()

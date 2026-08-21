#Requires -Version 7.4

[CmdletBinding()]
param(
  [ValidateSet("Show", "Describe")]
  [string]$Mode = "Show",
  [ValidateRange(1024, 65535)]
  [int]$FabricPort = 8766,
  [string]$StateRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$deviceLauncher = Join-Path $PSScriptRoot "classroom-devices.ps1"
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
    if ($health.physicalActuation -eq "enabled") {
      return [ordered]@{
        state = "ready"
        heading = "Classroom devices are ready"
        detail = "The local device host is running. Devices and lessons remain disarmed until you enable them in Classroom Control."
        primaryAction = "Open"
        primaryLabel = "Open Classroom Control"
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
$form.ClientSize = [Drawing.Size]::new(660, 430)
$form.MinimumSize = [Drawing.Size]::new(676, 469)
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

$safety = [Windows.Forms.Label]::new()
$safety.Text = "Connection only: no robot movement, drone flight, plug switching, or agent session starts automatically."
$safety.Location = [Drawing.Point]::new(42, 360)
$safety.Size = [Drawing.Size]::new(455, 42)
$safety.ForeColor = [Drawing.Color]::FromArgb(142, 159, 146)
$form.Controls.Add($safety)

$refreshButton = [Windows.Forms.Button]::new()
$refreshButton.Text = "Check again"
$refreshButton.Location = [Drawing.Point]::new(505, 365)
$refreshButton.Size = [Drawing.Size]::new(107, 31)
$refreshButton.FlatStyle = "Flat"
$refreshButton.ForeColor = [Drawing.Color]::FromArgb(185, 223, 255)
$refreshButton.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(63, 91, 72)
$form.Controls.Add($refreshButton)

$script:currentState = $null
$script:operation = $null
$script:stdoutTask = $null
$script:stderrTask = $null

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

  $startInfo = [Diagnostics.ProcessStartInfo]::new()
  $startInfo.FileName = $pwshCommand.Source
  $startInfo.WorkingDirectory = $repositoryRoot
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true
  $startInfo.RedirectStandardOutput = $true
  $startInfo.RedirectStandardError = $true
  foreach ($argument in @(
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
    )) {
    $startInfo.ArgumentList.Add($argument)
  }
  if ($Action -eq "Start") { $startInfo.ArgumentList.Add("-AllowPhysical") }

  $process = [Diagnostics.Process]::new()
  $process.StartInfo = $startInfo
  if (-not $process.Start()) { throw "The fixed classroom launcher could not start." }
  $script:stdoutTask = $process.StandardOutput.ReadToEndAsync()
  $script:stderrTask = $process.StandardError.ReadToEndAsync()
  $script:operation = $process
}

$operationTimer = [Windows.Forms.Timer]::new()
$operationTimer.Interval = 300
$operationTimer.Add_Tick({
    if ($null -eq $script:operation -or -not $script:operation.HasExited) { return }
    $operationTimer.Stop()
    $script:operation.WaitForExit()
    $exitCode = $script:operation.ExitCode
    $standardError = $script:stderrTask.GetAwaiter().GetResult()
    $null = $script:stdoutTask.GetAwaiter().GetResult()
    $script:operation.Dispose()
    $script:operation = $null
    $script:stdoutTask = $null
    $script:stderrTask = $null
    if ($exitCode -eq 0) {
      Update-ClassroomStatus
      return
    }
    $diagnostics = @($standardError -split "\r?\n" | Where-Object { $_ })
    $message = if ($diagnostics.Count -gt 0) {
      ($diagnostics | Select-Object -Last 4) -join [Environment]::NewLine
    } else {
      "The local device host did not start. Ask the classroom technician to check the CIT installation."
    }
    Update-ClassroomStatus
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
$refreshButton.Add_Click({ Update-ClassroomStatus })
$form.Add_FormClosing({
    param($sender, $event)
    if ($null -ne $script:operation -and -not $script:operation.HasExited) {
      $event.Cancel = $true
      [Windows.Forms.MessageBox]::Show(
        $form,
        "CIT is still preparing the local services. Wait for startup to finish before closing this window.",
        "Startup in progress",
        [Windows.Forms.MessageBoxButtons]::OK,
        [Windows.Forms.MessageBoxIcon]::Information
      ) | Out-Null
    }
  })

Update-ClassroomStatus
[void]$form.ShowDialog()

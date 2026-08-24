#Requires -Version 7.4

[CmdletBinding()]
param(
  [string]$OutputDirectory = "",
  [switch]$AllowDirty
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $OutputDirectory) {
  $OutputDirectory = Join-Path $sourceRoot "artifacts\windows-transfer"
}
$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd(
  [IO.Path]::DirectorySeparatorChar,
  [IO.Path]::AltDirectorySeparatorChar
)
$temporaryRoot = [IO.Path]::GetFullPath((Join-Path $tempBase "citxr-transfer-$([Guid]::NewGuid().ToString('N'))"))

function Remove-TemporaryRoot {
  if (-not (Test-Path -LiteralPath $temporaryRoot)) { return }
  $parent = [IO.Path]::GetFullPath((Split-Path $temporaryRoot -Parent))
  $leaf = Split-Path $temporaryRoot -Leaf
  if ($parent -ne $tempBase -or -not $leaf.StartsWith("citxr-transfer-")) {
    throw "Refusing to remove unexpected temporary path: $temporaryRoot"
  }
  Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
}

function Write-JsonUtf8([string]$Path, [object]$Value) {
  [IO.File]::WriteAllText(
    $Path,
    ($Value | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false)
  )
}

function Assert-RelativeSourcePath([string]$RelativePath) {
  $segments = $RelativePath -split '[\\/]'
  $excludedSegments = @(
    ".git", ".mypy_cache", ".playwright-cli", ".pytest_cache", ".ruff_cache",
    ".venv", "__pycache__", "artifacts", "build", "dist", "htmlcov",
    "node_modules", "output", ".godot", ".import"
  )
  foreach ($segment in $segments) {
    if ($segment -in $excludedSegments -or $segment.EndsWith(".egg-info")) { return $false }
  }
  $name = $segments[-1]
  if ($name -eq ".env" -or $name.StartsWith(".env.") -or $name.EndsWith(".local.yaml")) {
    return $false
  }
  if ($name -match '\.(pem|key|pfx|p12|sqlite|sqlite3|db)$') { return $false }
  return $true
}

function Get-SafeSourceFiles([string]$Root) {
  $pending = [Collections.Generic.Stack[IO.DirectoryInfo]]::new()
  $pending.Push((Get-Item -LiteralPath $Root))
  while ($pending.Count -gt 0) {
    $directory = $pending.Pop()
    foreach ($child in Get-ChildItem -LiteralPath $directory.FullName -Force) {
      $relative = [IO.Path]::GetRelativePath($sourceRoot, $child.FullName)
      if (-not (Assert-RelativeSourcePath $relative)) { continue }
      if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to package a reparse point: $relative"
      }
      if ($child.PSIsContainer) { $pending.Push($child) } else { $child }
    }
  }
}

try {
  $package = Get-Content -LiteralPath (Join-Path $sourceRoot "package.json") -Raw | ConvertFrom-Json
  $version = [string]$package.version
  $releaseMetadataPath = Join-Path $sourceRoot "cit-release-source.json"
  $sourceDirty = $false
  if (Test-Path -LiteralPath (Join-Path $sourceRoot ".git") -PathType Container) {
    $revision = (& git -C $sourceRoot rev-parse HEAD | Out-String).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0) { throw "Unable to resolve the Git revision." }
    $dirtyOutput = (& git -C $sourceRoot status --porcelain=v1 --untracked-files=normal | Out-String).Trim()
    $sourceDirty = [bool]$dirtyOutput
    if ($sourceDirty -and -not $AllowDirty) {
      throw "The source tree has uncommitted files. Commit the reviewed source or pass -AllowDirty for a development-only bundle."
    }
  } elseif (Test-Path -LiteralPath $releaseMetadataPath -PathType Leaf) {
    $inherited = Get-Content -LiteralPath $releaseMetadataPath -Raw | ConvertFrom-Json
    $revision = ([string]$inherited.revision).ToLowerInvariant()
    if ([string]$inherited.version -ne $version) {
      throw "Release metadata and package version do not match."
    }
  } else {
    throw "The source has neither Git metadata nor cit-release-source.json."
  }
  if ($revision -notmatch '^[a-f0-9]{7,40}$') { throw "The release revision is invalid." }
  if (-not $version -or $version.Length -gt 80) { throw "The package version is invalid." }

  New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
  $payloadContainer = Join-Path $temporaryRoot "payload"
  $payloadRoot = Join-Path $payloadContainer "CITPhysicalXR"
  $outerRoot = Join-Path $temporaryRoot "outer"
  New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null
  New-Item -ItemType Directory -Path $outerRoot -Force | Out-Null

  $sourceDirectories = @(
    "adapters", "apps", "config", "course-packs", "docs", "examples",
    "firmware", "packages", "schemas", "tests", "tools"
  )
  $sourceFiles = @(
    ".gitattributes", ".gitignore", ".npmrc", ".prettierignore",
    "eslint.config.js", "install-cit-business-site.cmd", "LICENSE", "package.json",
    "pnpm-lock.yaml", "pnpm-workspace.yaml", "pyproject.toml", "README.md",
    "THIRD_PARTY_NOTICES.md", "tsconfig.base.json", "tsconfig.json", "uv.lock",
    "vitest.config.ts"
  )
  $filesToCopy = [Collections.Generic.List[IO.FileInfo]]::new()
  foreach ($directoryName in $sourceDirectories) {
    $directoryPath = Join-Path $sourceRoot $directoryName
    if (Test-Path -LiteralPath $directoryPath -PathType Container) {
      foreach ($file in Get-SafeSourceFiles $directoryPath) { $filesToCopy.Add($file) }
    }
  }
  foreach ($fileName in $sourceFiles) {
    $filePath = Join-Path $sourceRoot $fileName
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
      throw "Required source file is missing: $fileName"
    }
    $filesToCopy.Add((Get-Item -LiteralPath $filePath))
  }
  foreach ($file in $filesToCopy) {
    $relative = [IO.Path]::GetRelativePath($sourceRoot, $file.FullName)
    $destination = Join-Path $payloadRoot $relative
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination
  }

  $generatedAt = [DateTimeOffset]::UtcNow.ToString("o")
  Write-JsonUtf8 (Join-Path $payloadRoot "cit-release-source.json") ([ordered]@{
    schemaVersion = "1.0"
    product = "CITPhysicalXR"
    version = $version
    revision = $revision
    generatedAt = $generatedAt
  })

  $releaseFiles = @(
    Get-ChildItem -LiteralPath $payloadRoot -Recurse -File |
      Sort-Object FullName |
      ForEach-Object {
        [ordered]@{
          path = [IO.Path]::GetRelativePath($payloadRoot, $_.FullName).Replace("\", "/")
          sizeBytes = $_.Length
          sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
      }
  )
  $sourceManifestPath = Join-Path $payloadRoot "cit-release-files.json"
  Write-JsonUtf8 $sourceManifestPath ([ordered]@{
    schemaVersion = "1.0"
    revision = $revision
    files = $releaseFiles
  })
  $sourceManifestHash = (
    Get-FileHash -LiteralPath $sourceManifestPath -Algorithm SHA256
  ).Hash.ToLowerInvariant()

  $payloadArchive = Join-Path $outerRoot "payload.zip"
  Compress-Archive -LiteralPath $payloadRoot -DestinationPath $payloadArchive -CompressionLevel Optimal
  $payloadHash = (Get-FileHash -LiteralPath $payloadArchive -Algorithm SHA256).Hash.ToLowerInvariant()
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot "windows\Install-CIT.cmd") -Destination $outerRoot
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot "windows\Install-CIT.ps1") -Destination $outerRoot
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot "windows\INSTALL-EN.txt") -Destination $outerRoot
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot "windows\INSTALL-KO.txt") -Destination $outerRoot
  Write-JsonUtf8 (Join-Path $outerRoot "bundle-manifest.json") ([ordered]@{
    schemaVersion = "1.0"
    product = "CITPhysicalXR"
    version = $version
    revision = $revision
    generatedAt = $generatedAt
    platform = "windows-x64"
    sourceDirty = $sourceDirty
    requiresInternet = $true
    payloadFile = "payload.zip"
    payloadSha256 = $payloadHash
    sourceManifestFile = "cit-release-files.json"
    sourceManifestSha256 = $sourceManifestHash
    sourceFileCount = $releaseFiles.Count + 1
  })
  [IO.File]::WriteAllText(
    (Join-Path $outerRoot "PAYLOAD-SHA256.txt"),
    "$payloadHash  payload.zip`r`n",
    [Text.UTF8Encoding]::new($false)
  )

  $shortRevision = $revision.Substring(0, [Math]::Min(12, $revision.Length))
  $artifactFileName = "CITPhysicalXR-Windows-Setup-$version-$shortRevision.zip"
  $temporaryArtifact = Join-Path $temporaryRoot $artifactFileName
  Compress-Archive -Path (Join-Path $outerRoot "*") -DestinationPath $temporaryArtifact -CompressionLevel Optimal
  $artifact = Get-Item -LiteralPath $temporaryArtifact
  $artifactHash = (Get-FileHash -LiteralPath $artifact.FullName -Algorithm SHA256).Hash.ToLowerInvariant()

  New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
  $artifactDestination = [IO.Path]::GetFullPath((Join-Path $outputRoot $artifactFileName))
  if ((Split-Path $artifactDestination -Parent) -ne $outputRoot) {
    throw "The generated artifact target escaped the output directory."
  }
  Copy-Item -LiteralPath $artifact.FullName -Destination $artifactDestination -Force
  Write-JsonUtf8 (Join-Path $outputRoot "installation-manifest.json") ([ordered]@{
    schemaVersion = "1.0"
    available = $true
    product = "CITPhysicalXR"
    version = $version
    revision = $revision
    generatedAt = $generatedAt
    platform = "windows-x64"
    requiresInternet = $true
    artifacts = @([ordered]@{
      artifactId = "windows-transfer-online"
      fileName = $artifactFileName
      mediaType = "application/zip"
      sizeBytes = $artifact.Length
      sha256 = $artifactHash
    })
  })

  Write-Host "Created $artifactDestination"
  Write-Host "SHA-256 $artifactHash"
  Write-Host "Secrets, machine state, recordings, build output, and dependency caches were excluded."
} finally {
  Remove-TemporaryRoot
}

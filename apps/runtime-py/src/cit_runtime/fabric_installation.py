"""Validated, immutable installation artifacts exposed by the local Fabric.

The HTTP process never builds a bundle or invokes a shell. A release/build step
places an artifact and manifest in one directory; startup verifies the declared
size and SHA-256 digest before the authenticated download route is installed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SHA256_PATTERN = r"^[a-f0-9]{64}$"
_REVISION_PATTERN = r"^[a-f0-9]{7,40}$"
_ARTIFACT_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,95}$"
_FILE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}\.zip$"
_MAX_ARTIFACT_BYTES = 1_073_741_824


class FabricInstallationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifactId: str = Field(pattern=_ARTIFACT_ID_PATTERN)
    fileName: str = Field(pattern=_FILE_NAME_PATTERN)
    mediaType: Literal["application/zip"] = "application/zip"
    sizeBytes: int = Field(gt=0, le=_MAX_ARTIFACT_BYTES)
    sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def require_plain_file_name(self) -> FabricInstallationArtifact:
        if Path(self.fileName).name != self.fileName:
            raise ValueError("Installation artifact fileName must not contain a path")
        return self


class FabricInstallationInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    available: bool
    product: Literal["CITPhysicalXR"] = "CITPhysicalXR"
    version: str | None = Field(default=None, min_length=1, max_length=80)
    revision: str | None = Field(default=None, pattern=_REVISION_PATTERN)
    generatedAt: datetime | None = None
    platform: Literal["windows-x64"] = "windows-x64"
    requiresInternet: bool = True
    artifacts: list[FabricInstallationArtifact] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def require_complete_available_manifest(self) -> FabricInstallationInfo:
        if self.available:
            if self.version is None or self.revision is None or self.generatedAt is None:
                raise ValueError("Available installation metadata must identify its release")
            if not self.artifacts:
                raise ValueError("Available installation metadata must include an artifact")
        elif self.artifacts:
            raise ValueError("Unavailable installation metadata cannot include artifacts")
        return self


@dataclass(frozen=True, slots=True)
class FabricInstallationCatalog:
    directory: Path | None
    info: FabricInstallationInfo

    @classmethod
    def load(cls, directory: str | Path | None) -> FabricInstallationCatalog:
        if directory is None:
            return cls.unavailable()
        resolved = Path(directory).resolve()
        manifest_path = resolved / "installation-manifest.json"
        if not manifest_path.is_file():
            return cls.unavailable()
        info = FabricInstallationInfo.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if not info.available:
            return cls(directory=resolved, info=info)
        for artifact in info.artifacts:
            artifact_path = (resolved / artifact.fileName).resolve()
            if artifact_path.parent != resolved or not artifact_path.is_file():
                raise ValueError(
                    f"Installation artifact {artifact.artifactId!r} is missing "
                    "or outside its directory"
                )
            if artifact_path.stat().st_size != artifact.sizeBytes:
                raise ValueError(
                    f"Installation artifact {artifact.artifactId!r} does not match "
                    "its declared size"
                )
            if _sha256(artifact_path) != artifact.sha256:
                raise ValueError(
                    f"Installation artifact {artifact.artifactId!r} failed SHA-256 verification"
                )
        return cls(directory=resolved, info=info)

    @classmethod
    def unavailable(cls) -> FabricInstallationCatalog:
        return cls(
            directory=None,
            info=FabricInstallationInfo(available=False),
        )

    def artifact(self, artifact_id: str) -> tuple[FabricInstallationArtifact, Path] | None:
        if self.directory is None:
            return None
        artifact = next(
            (candidate for candidate in self.info.artifacts if candidate.artifactId == artifact_id),
            None,
        )
        if artifact is None:
            return None
        path = (self.directory / artifact.fileName).resolve()
        if (
            path.parent != self.directory
            or not path.is_file()
            or path.stat().st_size != artifact.sizeBytes
            or _sha256(path) != artifact.sha256
        ):
            return None
        return artifact, path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

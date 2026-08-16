"""Projects on disk (FR-001, FR-002, NFR 12.4).

Until Milestone 6 a project lived in the browser tab that made it, so closing
the tab was indistinguishable from deleting the work. This store is the other
half: the same versioned document the Studio already produces (FR-002), written
where a crash cannot take it with it.

Two properties are worth the code they cost. A write is atomic -- a temporary
file in the same directory, fsynced, then renamed over the target -- so a power
cut during autosave leaves either the old project or the new one and never half
of either. And the previous version is kept beside it as ``.bak``, so a project
that is saved corrupt by a bug above this layer is still recoverable by hand.

Every document is validated against the project schema on the way in and on the
way out. A file that has been edited into something invalid is reported as
exactly that, rather than being loaded as a half-project that fails later
somewhere less obvious.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

# A project id is a UUID, and the file name is derived from it. Anything else is
# refused before it can be turned into a path.
_HEX = "[0-9a-fA-F]"
_PROJECT_ID = re.compile(rf"^{_HEX}{{8}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{12}}$")


class ProjectStoreError(RuntimeError):
    """A project could not be read, written, or validated."""

    def __init__(self, message: str, *, recovery: str) -> None:
        self.recovery = recovery
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    """What the Projects list shows without loading every document."""

    project_id: str
    name: str
    authoring_mode: str
    updated_at: str
    owner_id: str | None


def _schema() -> dict[str, Any]:
    resource = files("cit_runtime").joinpath("cit-project.schema.json")
    value: object = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Packaged project schema root must be an object")
    return value


class ProjectStore:
    """One directory of projects. Process-safe enough for one local runtime."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._validator = Draft202012Validator(_schema(), format_checker=FormatChecker())

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------- paths

    def _path(self, project_id: str) -> Path:
        if not _PROJECT_ID.match(project_id):
            raise ProjectStoreError(
                f"{project_id!r} is not a project id",
                recovery="Project ids are UUIDs. Open the project from the list instead.",
            )
        return self._root / f"{project_id}.json"

    def _owner_path(self, project_id: str) -> Path:
        return self._path(project_id).with_suffix(".owner.json")

    def _backup_path(self, project_id: str) -> Path:
        return self._path(project_id).with_suffix(".bak.json")

    # -------------------------------------------------------------------- read

    def list(self, *, owner_id: str | None = None) -> tuple[ProjectSummary, ...]:
        """Summaries, newest first. A corrupt file is skipped, not fatal."""

        summaries: list[ProjectSummary] = []
        for path in self._files():
            try:
                document = self._read_document(path)
            except ProjectStoreError:
                continue
            owner = _read_owner(self._owner_path(str(document["projectId"])))
            if owner_id is not None and owner not in (None, owner_id):
                continue
            summaries.append(
                ProjectSummary(
                    project_id=str(document["projectId"]),
                    name=str(document["name"]),
                    authoring_mode=str(document["authoringMode"]),
                    updated_at=str(document["updatedAt"]),
                    owner_id=owner,
                )
            )
        summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
        return tuple(summaries)

    def get(self, project_id: str) -> dict[str, Any]:
        return self._read_document(self._path(project_id))

    def owner_of(self, project_id: str) -> str | None:
        return _read_owner(self._owner_path(project_id))

    def _files(self) -> Iterator[Path]:
        if not self._root.is_dir():
            return
        for path in sorted(self._root.glob("*.json")):
            if path.name.endswith((".bak.json", ".owner.json")):
                continue
            yield path

    def _read_document(self, path: Path) -> dict[str, Any]:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise ProjectStoreError(
                f"No project stored at {path.name}",
                recovery="Open a project from the list, or create a new one.",
            ) from error
        try:
            value: object = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ProjectStoreError(
                f"{path.name} is not valid JSON: {error}",
                recovery=f"A previous version may be recoverable from {path.stem}.bak.json.",
            ) from error
        if not isinstance(value, dict):
            raise ProjectStoreError(
                f"{path.name} does not contain a project object",
                recovery=f"A previous version may be recoverable from {path.stem}.bak.json.",
            )
        self._validate(value, source=path.name)
        return value

    def _validate(self, document: Mapping[str, Any], *, source: str) -> None:
        errors = sorted(
            self._validator.iter_errors(dict(document)),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if not errors:
            return
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
            for error in errors[:5]
        )
        raise ProjectStoreError(
            f"{source} is not a valid project: {details}",
            recovery="The Studio writes this file; an edit made by hand is the usual cause.",
        )

    # ------------------------------------------------------------------- write

    def save(
        self,
        document: Mapping[str, Any],
        *,
        owner_id: str,
        at: datetime,
    ) -> dict[str, Any]:
        """Validate, stamp, and write atomically. Returns what was stored."""

        stored = dict(document)
        stored["updatedAt"] = at.isoformat()
        self._validate(stored, source="this project")

        project_id = str(stored["projectId"])
        path = self._path(project_id)
        owner_path = self._owner_path(project_id)

        self._root.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self._backup_path(project_id).write_bytes(path.read_bytes())
        _atomic_write(path, json.dumps(stored, indent=2, sort_keys=True) + "\n")

        # Ownership is claimed once, by whoever first saved it. A student who
        # opens someone else's project and saves it does not become its owner.
        if _read_owner(owner_path) is None:
            _atomic_write(owner_path, json.dumps({"ownerId": owner_id}, sort_keys=True) + "\n")
        return stored

    def delete(self, project_id: str) -> bool:
        path = self._path(project_id)
        existed = path.exists()
        for doomed in (path, self._backup_path(project_id), self._owner_path(project_id)):
            doomed.unlink(missing_ok=True)
        return existed


def _atomic_write(path: Path, text: str) -> None:
    """Write through a temporary file in the same directory, then rename.

    Same directory matters: a rename across filesystems is a copy, and a copy is
    exactly the non-atomic write this avoids.
    """

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def _read_owner(path: Path) -> str | None:
    """Ownership is a sidecar, never a field in the project document.

    The project schema is the Studio's and closed to additional properties, so a
    runtime-only field would make every browser-written project invalid. Rather
    than smuggling the owner into a permissive corner of the student's document,
    it lives beside it in ``<id>.owner.json``. Losing that file loses the
    ownership claim, not the work.
    """

    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    owner = value.get("ownerId")
    return owner if isinstance(owner, str) and owner else None

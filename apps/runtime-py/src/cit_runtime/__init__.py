"""CIT Physical XR runtime foundation.

Milestone 0 exposes configuration helpers only. It does not expose a network
service or a device-dispatch path.
"""

from .config import (
    ConfigurationError,
    RepositoryPathUnavailable,
    load_config,
    select_repository_path,
)

__all__ = [
    "ConfigurationError",
    "RepositoryPathUnavailable",
    "load_config",
    "select_repository_path",
]

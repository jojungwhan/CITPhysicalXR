"""CIT Physical XR local runtime.

Milestone 1 adds the runtime core: sessions, a device registry over the adapter
contract, an independent safety supervisor, a single command pipeline, event
routing, record/replay, and a loopback-only local API.

It drives fake adapters. No hardware adapter ships here; those arrive in M2
(RoboMaster S1, Leap), M4 (LEGO), and M5 (Quest).
"""

from .api import create_app, serve
from .audit import AuditAction, AuditEntry, AuditLog, StructuredLogger, redact
from .clock import Clock, ManualClock, SystemClock
from .config import (
    ConfigurationError,
    RepositoryPathUnavailable,
    load_config,
    select_repository_path,
)
from .events import EventRouter, Subscription
from .pipeline import CommandPipeline, CommandQueue, Dispatch
from .recorder import Recorder, Recording, Replayer, merge_recordings
from .registry import (
    ConfiguredDiscoveryProvider,
    DeviceAssignmentError,
    DeviceConnectionState,
    DeviceRegistry,
    DiscoveryProvider,
    RegisteredDevice,
)
from .runtime import Runtime, RuntimeInfo, default_simulation_adapters
from .sessions import (
    AuthoringMode,
    ExecutionMode,
    ProgramSession,
    SessionRepository,
    SessionState,
    SessionTransitionError,
    allowed_transitions,
)
from .supervisor import (
    ArmingError,
    ArmState,
    CommandPriority,
    MotionBounds,
    SafetyPolicy,
    SafetySupervisor,
    SupervisorVerdict,
    WatchdogAction,
    WatchdogKind,
    classify_priority,
)

__all__ = [
    "ArmState",
    "ArmingError",
    "AuditAction",
    "AuditEntry",
    "AuditLog",
    "AuthoringMode",
    "Clock",
    "CommandPipeline",
    "CommandPriority",
    "CommandQueue",
    "ConfigurationError",
    "ConfiguredDiscoveryProvider",
    "DeviceAssignmentError",
    "DeviceConnectionState",
    "DeviceRegistry",
    "DiscoveryProvider",
    "Dispatch",
    "EventRouter",
    "ExecutionMode",
    "ManualClock",
    "MotionBounds",
    "ProgramSession",
    "Recorder",
    "Recording",
    "RegisteredDevice",
    "Replayer",
    "RepositoryPathUnavailable",
    "Runtime",
    "RuntimeInfo",
    "SafetyPolicy",
    "SafetySupervisor",
    "SessionRepository",
    "SessionState",
    "SessionTransitionError",
    "StructuredLogger",
    "Subscription",
    "SupervisorVerdict",
    "SystemClock",
    "WatchdogAction",
    "WatchdogKind",
    "allowed_transitions",
    "classify_priority",
    "create_app",
    "default_simulation_adapters",
    "load_config",
    "merge_recordings",
    "redact",
    "select_repository_path",
    "serve",
]

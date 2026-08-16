"""Event routing, deduplication, and per-device sequencing.

FR-059 has two halves that pull against each other: one input event may fan out
to several subscribers, and one device event must not be delivered twice. The
router therefore fans out by subscriber and dedupes by event identity, so a
retrying adapter cannot make a robot act twice.

FR-060: source timestamps are preserved, receipt time is recorded, and sequence
numbers are per device. No hard real-time claim is made.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from cit_protocol import DeviceEvent

EventHandler = Callable[[DeviceEvent], None]


@dataclass(frozen=True, slots=True)
class Subscription:
    subscriber_id: str
    handler: EventHandler
    device_ids: frozenset[str] = frozenset()
    categories: frozenset[str] = frozenset()

    def wants(self, event: DeviceEvent) -> bool:
        if self.device_ids and event.deviceId not in self.device_ids:
            return False
        if self.categories and event.category not in self.categories:
            return False
        return True


class EventRouter:
    """Fan-out with an identity-keyed dedupe window and a bounded history."""

    def __init__(self, *, dedupe_window: int = 4096, history: int = 512) -> None:
        if dedupe_window <= 0:
            raise ValueError("dedupe_window must be positive")
        self._subscriptions: dict[str, Subscription] = {}
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._dedupe_window = dedupe_window
        self._history: deque[DeviceEvent] = deque(maxlen=history)
        self._sequences: dict[str, int] = {}
        self._dropped_duplicates = 0

    def subscribe(
        self,
        subscriber_id: str,
        handler: EventHandler,
        *,
        device_ids: Iterable[str] = (),
        categories: Iterable[str] = (),
    ) -> Subscription:
        subscription = Subscription(
            subscriber_id=subscriber_id,
            handler=handler,
            device_ids=frozenset(device_ids),
            categories=frozenset(categories),
        )
        self._subscriptions[subscriber_id] = subscription
        return subscription

    def unsubscribe(self, subscriber_id: str) -> None:
        self._subscriptions.pop(subscriber_id, None)

    @property
    def dropped_duplicates(self) -> int:
        return self._dropped_duplicates

    def next_sequence(self, device_id: str) -> int:
        """FR-060. Sequence numbers are per device, never global."""

        value = self._sequences.get(device_id, 0) + 1
        self._sequences[device_id] = value
        return value

    def publish(self, event: DeviceEvent) -> int:
        """Deliver to every matching subscriber. Returns the delivery count."""

        key = str(event.eventId)
        if key in self._seen:
            self._dropped_duplicates += 1
            return 0
        self._seen[key] = None
        while len(self._seen) > self._dedupe_window:
            self._seen.popitem(last=False)

        self._history.append(event)
        delivered = 0
        for subscription in list(self._subscriptions.values()):
            if not subscription.wants(event):
                continue
            subscription.handler(event)
            delivered += 1
        return delivered

    def publish_all(self, events: Iterable[DeviceEvent]) -> int:
        return sum(self.publish(event) for event in events)

    def history(
        self, *, device_id: str | None = None, since: datetime | None = None
    ) -> tuple[DeviceEvent, ...]:
        return tuple(
            event
            for event in self._history
            if (device_id is None or event.deviceId == device_id)
            and (since is None or event.receivedAt >= since)
        )

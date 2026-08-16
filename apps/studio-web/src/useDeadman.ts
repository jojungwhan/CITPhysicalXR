import { useCallback, useEffect, useRef, useState } from "react";

import type { RuntimeClient } from "./runtime-client.js";

/** Beat well inside the 300 ms watchdog, so a slow reply is not a stop. */
const BEAT_MS = 100;

/**
 * ADR-028. Holding the dead-man control, as the runtime understands it.
 *
 * There is no "deadman is active" flag anywhere in this hook, because the
 * runtime does not accept one. Holding the control means this page keeps
 * sending heartbeats; releasing it means it stops. Closing the tab, freezing,
 * and letting go all produce the same silence, which is exactly the property
 * the control is supposed to have.
 */
export function useDeadman(client: RuntimeClient, deviceId: string | null) {
  const timerRef = useRef<number | null>(null);
  const [held, setHeld] = useState(false);

  const release = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setHeld(false);
  }, []);

  const hold = useCallback(() => {
    if (deviceId === null || timerRef.current !== null) return;
    setHeld(true);
    const beat = () => {
      void client.heartbeat(deviceId).catch(() => {
        // A failed beat is a stopped robot within one watchdog period. That is
        // the correct outcome, so there is nothing to recover here.
      });
    };
    beat();
    timerRef.current = window.setInterval(beat, BEAT_MS);
  }, [client, deviceId]);

  // Releasing when the device changes matters: otherwise a hold started on one
  // robot would keep feeding heartbeats after the student selected another.
  useEffect(() => release, [release, deviceId]);

  return { held, hold, release };
}

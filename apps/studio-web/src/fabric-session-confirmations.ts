type ConfirmationStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

type FabricSessionConfirmation = "aircraft-grounded" | "flight-safety";

const CONFIRMATION_KEYS: Record<FabricSessionConfirmation, string> = {
  "aircraft-grounded": "cit.fabric.aircraft-grounded-confirmed.v1",
  "flight-safety": "cit.fabric.flight-safety-confirmed.v1",
};

const confirmationKey = (confirmation: FabricSessionConfirmation) =>
  CONFIRMATION_KEYS[confirmation];

function browserSessionStorage(): ConfirmationStorage | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    return window.sessionStorage;
  } catch {
    return undefined;
  }
}

function readConfirmation(
  confirmation: FabricSessionConfirmation,
  storage: ConfirmationStorage | undefined,
): boolean {
  if (storage === undefined) return false;
  try {
    return storage.getItem(confirmationKey(confirmation)) === "true";
  } catch {
    return false;
  }
}

function saveConfirmation(
  confirmation: FabricSessionConfirmation,
  confirmed: boolean,
  storage: ConfirmationStorage | undefined,
): void {
  if (storage === undefined) return;
  try {
    if (confirmed) {
      storage.setItem(confirmationKey(confirmation), "true");
    } else {
      storage.removeItem(confirmationKey(confirmation));
    }
  } catch {
    // Storage can be blocked by browser privacy settings. The in-memory state
    // still works for the current page when that happens.
  }
}

function clearConfirmation(
  confirmation: FabricSessionConfirmation,
  storage: ConfirmationStorage | undefined,
): void {
  if (storage === undefined) return;
  try {
    storage.removeItem(confirmationKey(confirmation));
  } catch {
    // Safety resets and sign-out must complete if storage is unavailable.
  }
}

export function readAircraftGroundedConfirmation(
  storage: ConfirmationStorage | undefined = browserSessionStorage(),
): boolean {
  return readConfirmation("aircraft-grounded", storage);
}

export function saveAircraftGroundedConfirmation(
  confirmed: boolean,
  storage: ConfirmationStorage | undefined = browserSessionStorage(),
): void {
  saveConfirmation("aircraft-grounded", confirmed, storage);
}

export function clearAircraftGroundedConfirmation(
  storage: ConfirmationStorage | undefined = browserSessionStorage(),
): void {
  clearConfirmation("aircraft-grounded", storage);
}

export function readFlightSafetyConfirmation(
  storage: ConfirmationStorage | undefined = browserSessionStorage(),
): boolean {
  return readConfirmation("flight-safety", storage);
}

export function saveFlightSafetyConfirmation(
  confirmed: boolean,
  storage: ConfirmationStorage | undefined = browserSessionStorage(),
): void {
  saveConfirmation("flight-safety", confirmed, storage);
}

export function clearFlightSafetyConfirmation(
  storage: ConfirmationStorage | undefined = browserSessionStorage(),
): void {
  clearConfirmation("flight-safety", storage);
}

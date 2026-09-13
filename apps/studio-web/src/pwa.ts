interface FabricPwaLocation {
  pathname: string;
}

interface ServiceWorkerRegistrar {
  register(
    scriptURL: string | URL,
    options?: RegistrationOptions,
  ): Promise<unknown>;
}

export async function registerFabricPwa(
  location: FabricPwaLocation = window.location,
  serviceWorker: ServiceWorkerRegistrar | undefined = navigator.serviceWorker,
  origin = window.location.origin,
): Promise<void> {
  if (
    serviceWorker === undefined ||
    !location.pathname.replace(/\/$/, "").endsWith("/fabric")
  ) {
    return;
  }
  await serviceWorker.register(new URL("/fabric-sw.js", origin).toString(), {
    scope: "/",
  });
}

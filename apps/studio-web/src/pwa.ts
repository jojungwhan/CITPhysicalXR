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
  const pathname = location.pathname.replace(/\/+$/, "");
  if (serviceWorker === undefined || !pathname.endsWith("/fabric")) {
    return;
  }
  const basePath = pathname.slice(0, -"/fabric".length);
  await serviceWorker.register(
    new URL(`${basePath}/fabric-sw.js`, origin).toString(),
    {
      scope: `${basePath}/`,
    },
  );
}

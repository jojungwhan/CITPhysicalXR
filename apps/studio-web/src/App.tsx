import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { translatorFor, type Locale } from "./i18n.js";
import { FabricConsole } from "./FabricConsole.js";
import {
  RuntimeClient,
  RuntimeRefusedError,
  RuntimeUnreachableError,
  type DeviceEventView,
  type DeviceView,
  type HealthView,
  type Identity,
  type SessionView,
} from "./runtime-client.js";
import { NAV_LABEL, ROUTES, routeFromHash, type Route } from "./routes.js";
import { SafetyBanner, safetyStateOf } from "./SafetyBanner.js";
import { SignIn } from "./SignIn.js";
import { DevicesView } from "./views/DevicesView.js";
import { InstructorView } from "./views/InstructorView.js";
import { LogsView } from "./views/LogsView.js";
import { SettingsView } from "./views/SettingsView.js";
import { SimulationView } from "./views/SimulationView.js";
import { XrView } from "./views/XrView.js";

// These views pull in AJV's runtime schema compiler. Keep them in route-specific
// chunks so the Fabric console remains compatible with its no-unsafe-eval CSP.
const ProgramView = lazy(async () => {
  const module = await import("./ProgramView.js");
  return { default: module.ProgramView };
});

const ProjectsView = lazy(async () => {
  const module = await import("./views/ProjectsView.js");
  return { default: module.ProjectsView };
});

export function App() {
  if (
    typeof window !== "undefined" &&
    window.location.pathname.replace(/\/$/, "").endsWith("/fabric")
  ) {
    return <FabricConsole />;
  }
  return <ClassroomApp />;
}

function ClassroomApp() {
  const clientRef = useRef(new RuntimeClient());
  const client = clientRef.current;

  const [locale, setLocale] = useState<Locale>("en");
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [route, setRoute] = useState<Route>(() =>
    routeFromHash(typeof window === "undefined" ? "" : window.location.hash),
  );

  const [health, setHealth] = useState<HealthView | null>(null);
  const [devices, setDevices] = useState<DeviceView[]>([]);
  const [sessions, setSessions] = useState<SessionView[]>([]);
  const [session, setSession] = useState<SessionView | null>(null);
  const [events, setEvents] = useState<DeviceEventView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const t = useMemo(() => translatorFor(locale), [locale]);

  const run = useCallback(async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (caught) {
      if (caught instanceof RuntimeRefusedError && caught.needsSignIn) {
        // The token expired or was revoked. Signing in again is the only way
        // forward, and pretending otherwise leaves every button broken.
        setIdentity(null);
      }
      setError(
        caught instanceof RuntimeUnreachableError ||
          caught instanceof RuntimeRefusedError ||
          caught instanceof Error
          ? caught.message
          : String(caught),
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setHealth(await client.health());
    if (!client.hasToken()) return;
    setDevices(await client.devices());
    setSessions(await client.sessions());
  }, [client]);

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // Also on every view change. A classroom moves while a student is reading:
  // another student takes the last free hub, an instructor disarms one. Opening
  // Devices and being shown the room as it was when the page loaded is how
  // somebody ends up binding a robot that is no longer free.
  useEffect(() => {
    void run(refresh);
  }, [run, refresh, identity, route]);

  // Events recorded before this page attached: startup connections happen long
  // before a browser opens, so without this the panel is empty for no reason.
  useEffect(() => {
    if (identity === null) return;
    void client
      .recentEvents()
      .then((recorded) => {
        setEvents((current) =>
          current.length > 0 ? current : [...recorded].reverse().slice(0, 60),
        );
      })
      .catch(() => {
        // The connection error is already reported by refresh().
      });
  }, [client, identity]);

  useEffect(() => {
    if (identity === null) return undefined;
    return client.streamEvents((event) => {
      setEvents((current) => [event, ...current].slice(0, 60));
    });
  }, [client, identity]);

  const signOut = () =>
    run(async () => {
      await client.leave();
      setIdentity(null);
      setSession(null);
      setDevices([]);
      setSessions([]);
      setEvents([]);
    });

  const stopAll = () =>
    run(async () => {
      await client.stop({ reason: "studio stop-all" });
      await refresh();
    });

  if (identity === null) {
    return (
      <main>
        <header className="bar">
          <div>
            <p className="eyebrow">{t("app.title")}</p>
            <h1>{t("app.subtitle")}</h1>
          </div>
        </header>
        <SignIn
          client={client}
          t={t}
          locale={locale}
          onLocale={setLocale}
          onSignedIn={setIdentity}
          runtimeError={error}
          joinRequiresPasscode={health?.joinRequiresPasscode === true}
        />
      </main>
    );
  }

  const safety = safetyStateOf({ health, devices, sessions });

  return (
    <main>
      <header className="bar">
        <div>
          <p className="eyebrow">{t("app.title")}</p>
          <h1>{t("app.subtitle")}</h1>
        </div>
        <div className="row">
          <span className="muted">
            {t("signin.signedInAs")} <strong>{identity.displayName}</strong>{" "}
            <span className="pill">{t(`signin.role.${identity.role}`)}</span>
          </span>
          <button type="button" onClick={signOut} disabled={busy}>
            {t("signin.leave")}
          </button>
          {identity.role === "instructor" && (
            <button
              type="button"
              className="danger"
              onClick={stopAll}
              disabled={busy}
            >
              {t("action.stopAll")}
            </button>
          )}
        </div>
      </header>

      <SafetyBanner state={safety} t={t} />

      <nav className="tabs" aria-label={t("app.subtitle")}>
        {ROUTES.map((name) => (
          <a
            key={name}
            href={`#/${name}`}
            className={name === route ? "tab current" : "tab"}
            aria-current={name === route ? "page" : undefined}
          >
            {t(NAV_LABEL[name])}
          </a>
        ))}
      </nav>

      {error !== null && (
        <div className="notice bad" role="alert">
          {error}
        </div>
      )}

      {route === "projects" && (
        <Suspense fallback={<p className="muted">Loading projects…</p>}>
          <ProjectsView client={client} t={t} run={run} busy={busy} />
        </Suspense>
      )}

      {route === "program" && (
        <Suspense fallback={<p className="muted">Loading program…</p>}>
          <ProgramView
            client={client}
            identity={identity}
            session={session}
            setSession={setSession}
            devices={devices}
            locale={locale}
            t={t}
            run={run}
            busy={busy}
            refresh={refresh}
          />
        </Suspense>
      )}

      {route === "devices" && (
        <DevicesView
          client={client}
          identity={identity}
          devices={devices}
          session={session}
          t={t}
          run={run}
          busy={busy}
          refresh={refresh}
        />
      )}

      {route === "xr" && <XrView t={t} />}

      {route === "simulation" && (
        <SimulationView
          client={client}
          session={session}
          t={t}
          run={run}
          busy={busy}
        />
      )}

      {route === "instructor" && (
        <InstructorView
          client={client}
          identity={identity}
          t={t}
          run={run}
          busy={busy}
        />
      )}

      {route === "logs" && (
        <LogsView
          client={client}
          identity={identity}
          events={events}
          t={t}
          run={run}
        />
      )}

      {route === "settings" && (
        <SettingsView
          client={client}
          identity={identity}
          health={health}
          locale={locale}
          onLocale={setLocale}
          t={t}
          run={run}
          busy={busy}
        />
      )}
    </main>
  );
}

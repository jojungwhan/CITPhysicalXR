import type {
  CoursePack,
  FabricCommandPriority,
  IntegrationNode,
  InteractionSession,
} from "@citxr/protocol";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";

import {
  FabricApiError,
  FabricClient,
  type FabricAuditRecord,
  type FabricDiscoveryReport,
  type FabricIntegrationDiscovery,
  type FabricMediaPairing,
  type FabricMediaSource,
  type FabricPrincipal,
  type StoredFabricEvent,
  type StoredFabricLifecycle,
} from "./fabric-client.js";
import { consumeConsoleTicket } from "./fabric-console-access.js";
import {
  classifyFabricNodeIo,
  isAvailableFabricNode,
  type FabricNodeIoKind,
} from "./fabric-node-io.js";
import { countActiveFabricCommands } from "./fabric-lifecycle.js";
import {
  isSmartPlugNode,
  isSwitchableLoadVisionLabel,
  latestSmartPlugState,
  POWER_SET_CAPABILITY,
} from "./fabric-smart-plug.js";
import { latestSensorReadings } from "./fabric-sensors.js";
import { tutorGuide } from "./fabric-tutor-guide.js";

type BusyAction = string | null;

export function FabricConsole() {
  const client = useMemo(() => new FabricClient(), []);
  const [credential, setCredential] = useState("");
  const [principal, setPrincipal] = useState<FabricPrincipal | null>(null);
  const [nodes, setNodes] = useState<IntegrationNode[]>([]);
  const [discovery, setDiscovery] = useState<FabricDiscoveryReport | null>(
    null,
  );
  const [coursePacks, setCoursePacks] = useState<CoursePack[]>([]);
  const [sessions, setSessions] = useState<InteractionSession[]>([]);
  const [events, setEvents] = useState<StoredFabricEvent[]>([]);
  const [mediaSources, setMediaSources] = useState<FabricMediaSource[]>([]);
  const [mediaPairing, setMediaPairing] = useState<FabricMediaPairing | null>(
    null,
  );
  const [lifecycle, setLifecycle] = useState<StoredFabricLifecycle[]>([]);
  const [audit, setAudit] = useState<FabricAuditRecord[]>([]);
  const [selectedCourseKey, setSelectedCourseKey] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [roleSelections, setRoleSelections] = useState<Record<string, string>>(
    {},
  );
  const [siteId, setSiteId] = useState("local-site");
  const [roomId, setRoomId] = useState("local-room");
  const [sessionMode, setSessionMode] = useState<"simulation" | "physical">(
    "simulation",
  );
  const [showAccessCode, setShowAccessCode] = useState(false);
  const [autoConnecting, setAutoConnecting] = useState(false);
  const [safetyConfirmed, setSafetyConfirmed] = useState(false);
  const [groundedConfirmations, setGroundedConfirmations] = useState<
    Record<string, boolean>
  >({});
  const [busy, setBusy] = useState<BusyAction>(null);
  const [notice, setNotice] = useState("Ready to set up your classroom.");
  const [error, setError] = useState<string | null>(null);
  const pollActive = useRef(false);
  const ticketAttempted = useRef(false);

  const selectedSession = useMemo(
    () => sessions.find((session) => session.sessionId === selectedSessionId),
    [selectedSessionId, sessions],
  );
  const selectedCourse = useMemo(() => {
    const key = selectedSession
      ? courseKey(
          selectedSession.coursePackId,
          selectedSession.coursePackVersion,
        )
      : selectedCourseKey;
    return coursePacks.find(
      (coursePack) =>
        courseKey(coursePack.coursePackId, coursePack.version) === key,
    );
  }, [coursePacks, selectedCourseKey, selectedSession]);
  const canManageSessions = hasPermission(principal, "fabric.sessions.manage");
  const canAssignRoles = hasPermission(principal, "fabric.roles.assign");
  const canSubmitCommands = hasPermission(principal, "fabric.commands.submit");
  const canReadMedia = hasPermission(principal, "fabric.media.read");
  const canPairMedia = hasPermission(principal, "fabric.media.manage");
  const canAnalyzeVision = hasPermission(principal, "fabric.vision.analyze");
  const canConnectDevices = hasPermission(
    principal,
    "fabric.discovery.connect",
  );
  const connectableIntegrations = useMemo(
    () =>
      discovery?.integrations.filter(
        (integration) =>
          integration.actionId !== undefined &&
          integration.status !== "connected",
      ) ?? [],
    [discovery],
  );
  const groundedConnections = useMemo(
    () =>
      connectableIntegrations.filter(
        (integration) => integration.requiresGroundedConfirmation,
      ),
    [connectableIntegrations],
  );
  const allAircraftGrounded = groundedConnections.every(
    (integration) => groundedConfirmations[integration.integrationId] === true,
  );
  const discoveryConnectionsEnabled =
    canConnectDevices && discovery?.physicalActuationEnabled === true;
  const canStopAll = hasPermission(principal, "fabric.stop_all");
  const availableNodes = useMemo(
    () => nodes.filter(isAvailableFabricNode),
    [nodes],
  );
  const offlineNodeCount = nodes.length - availableNodes.length;
  const smartPlugNodes = useMemo(
    () => availableNodes.filter(isSmartPlugNode),
    [availableNodes],
  );
  const smartPlugBinding = selectedSession?.roleBindings.find(
    (binding) => binding.role === "classroom_plug",
  );
  const selectedSmartPlug = smartPlugNodes.find(
    (node) => node.nodeId === smartPlugBinding?.nodeId,
  );
  const smartPlugState = useMemo(
    () => latestSmartPlugState(events, selectedSmartPlug?.nodeId),
    [events, selectedSmartPlug?.nodeId],
  );
  const sensorReadings = useMemo(() => latestSensorReadings(events), [events]);
  const canTurnSmartPlugOff =
    canSubmitCommands && busy === null && smartPlugBinding !== undefined;
  const canTurnSmartPlugOn =
    canTurnSmartPlugOff &&
    selectedSession?.state === "active" &&
    (selectedSession.mode !== "physical" || selectedSession.armed === true);
  const requiredRoles = useMemo(
    () =>
      selectedCourse?.roles
        .filter((requirement) => !requirement.optional)
        .map((requirement) => requirement.role) ?? [],
    [selectedCourse],
  );
  const discoveryScanned =
    discovery !== null &&
    discovery.integrations.every(
      (integration) => integration.status !== "not_scanned",
    );
  const guide = useMemo(
    () => tutorGuide(selectedSession, requiredRoles, discoveryScanned),
    [discoveryScanned, requiredRoles, selectedSession],
  );
  const requiredRolesReady = useMemo(() => {
    if (selectedSession === undefined) return false;
    const assigned = new Set(
      selectedSession.roleBindings.map((binding) => binding.role),
    );
    return requiredRoles.every((role) => assigned.has(role));
  }, [requiredRoles, selectedSession]);

  const refresh = useCallback(
    async (showError = false) => {
      if (principal === null || pollActive.current) return;
      pollActive.current = true;
      try {
        const [
          nextNodes,
          nextDiscovery,
          nextCourses,
          nextSessions,
          nextMediaSources,
        ] = await Promise.all([
          client.listNodes(),
          client.getDiscovery(),
          client.listCoursePacks(),
          client.listSessions(),
          canReadMedia ? client.listMediaSources() : Promise.resolve([]),
        ]);
        setNodes(nextNodes);
        setDiscovery(nextDiscovery);
        setCoursePacks(nextCourses);
        setSessions(nextSessions);
        setMediaSources(nextMediaSources);
        setSelectedCourseKey(
          (current) =>
            current ||
            (nextCourses[0] === undefined
              ? ""
              : courseKey(nextCourses[0].coursePackId, nextCourses[0].version)),
        );
        setSelectedSessionId((current) => {
          if (
            current &&
            nextSessions.some((session) => session.sessionId === current)
          ) {
            return current;
          }
          return nextSessions[0]?.sessionId ?? "";
        });

        if (selectedSessionId) {
          try {
            setEvents(await client.listEvents(selectedSessionId));
          } catch (caught) {
            if (!(caught instanceof FabricApiError && caught.status === 403))
              throw caught;
          }
        } else {
          setEvents([]);
        }
        try {
          setLifecycle(await client.listLifecycle());
        } catch (caught) {
          if (!(caught instanceof FabricApiError && caught.status === 403))
            throw caught;
        }
        if (hasPermission(principal, "fabric.audit.read")) {
          try {
            setAudit(await client.listAudit());
          } catch (caught) {
            if (!(caught instanceof FabricApiError && caught.status === 403))
              throw caught;
          }
        }
        if (showError) setError(null);
      } catch (caught) {
        if (showError) setError(describeFabricError(caught));
      } finally {
        pollActive.current = false;
      }
    },
    [canReadMedia, client, principal, selectedSessionId],
  );

  useLayoutEffect(() => {
    if (ticketAttempted.current) return;
    ticketAttempted.current = true;
    const ticket = consumeConsoleTicket(window.location, window.history);
    if (ticket === undefined) return;
    setAutoConnecting(true);
    setError(null);
    void client
      .connectWithConsoleTicket(ticket)
      .then((identity) => {
        setPrincipal(identity);
        setNotice("Classroom controls opened securely on this computer.");
      })
      .catch((caught: unknown) => {
        setError(describeFabricError(caught));
        setShowAccessCode(true);
      })
      .finally(() => setAutoConnecting(false));
  }, [client]);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "CIT Classroom Control";
    return () => {
      document.title = previousTitle;
    };
  }, []);

  useEffect(() => {
    if (principal === null) return;
    void refresh(true);
    const poll = window.setInterval(() => void refresh(false), 2_000);
    return () => window.clearInterval(poll);
  }, [principal, refresh]);

  useEffect(() => {
    if (selectedSession === undefined) {
      setRoleSelections({});
      return;
    }
    const selections = Object.fromEntries(
      selectedSession.roleBindings.map((binding) => [
        binding.role,
        binding.nodeId,
      ]),
    );
    if (selectedCourse !== undefined) {
      selectedCourse.roles.forEach((requirement) => {
        if (selections[requirement.role] !== undefined) return;
        const candidates = compatibleNodes(nodes, selectedSession, requirement);
        if (candidates.length === 1) {
          selections[requirement.role] = candidates[0]?.nodeId ?? "";
        }
      });
    }
    setRoleSelections(selections);
  }, [nodes, selectedCourse, selectedSession]);

  useEffect(
    () => setSafetyConfirmed(false),
    [selectedSessionId, selectedSession?.armed],
  );

  const runAction = async (label: string, action: () => Promise<void>) => {
    if (busy !== null) return;
    setBusy(label);
    setError(null);
    try {
      await action();
      await refresh(false);
    } catch (caught) {
      setError(describeFabricError(caught));
    } finally {
      setBusy(null);
    }
  };

  const signIn = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runAction("Authenticating", async () => {
      client.setCredential(credential);
      try {
        const identity = await client.whoAmI();
        setPrincipal(identity);
        setCredential("");
        setNotice("Classroom controls connected on this computer.");
      } catch (caught) {
        client.clearCredential();
        throw caught;
      }
    });
  };

  const signOut = () => {
    client.clearCredential();
    setPrincipal(null);
    setNodes([]);
    setDiscovery(null);
    setCoursePacks([]);
    setSessions([]);
    setEvents([]);
    setMediaSources([]);
    setMediaPairing(null);
    setLifecycle([]);
    setAudit([]);
    setGroundedConfirmations({});
    setNotice(
      "Signed out. Reopen the console from the CIT launcher to return.",
    );
  };

  const createSession = () =>
    runAction("Creating session", async () => {
      const coursePack = coursePacks.find(
        (candidate) =>
          courseKey(candidate.coursePackId, candidate.version) ===
          selectedCourseKey,
      );
      if (coursePack === undefined)
        throw new Error("Select an installed course pack.");
      const created = await client.createSession({
        coursePackId: coursePack.coursePackId,
        coursePackVersion: coursePack.version,
        siteId,
        roomId,
        mode: sessionMode,
      });
      let prepared = created;
      let automaticAssignments = 0;
      const usedNodes = new Set<string>();
      for (const requirement of coursePack.roles) {
        const candidates = compatibleNodes(nodes, prepared, requirement).filter(
          (node) => !usedNodes.has(node.nodeId),
        );
        if (candidates.length !== 1) continue;
        const candidate = candidates[0];
        if (candidate === undefined) continue;
        prepared = await client.assignRole(
          prepared.sessionId,
          requirement.role,
          candidate.nodeId,
        );
        usedNodes.add(candidate.nodeId);
        automaticAssignments += 1;
      }
      setSessions((current) => [...current, prepared]);
      setSelectedSessionId(prepared.sessionId);
      setNotice(
        automaticAssignments > 0
          ? `Lesson created and ${automaticAssignments} available ${automaticAssignments === 1 ? "device was" : "devices were"} connected automatically.`
          : "Lesson created. Choose the devices you want to use next.",
      );
    });

  const assignRole = (role: string) =>
    runAction(`Assigning ${role}`, async () => {
      if (selectedSession === undefined)
        throw new Error("Select a session first.");
      const nodeId = roleSelections[role];
      if (!nodeId) throw new Error(`Select a compatible node for ${role}.`);
      const updated = await client.assignRole(
        selectedSession.sessionId,
        role,
        nodeId,
      );
      setSessions((current) => replaceSession(current, updated));
      const nodeName = nodes.find(
        (node) => node.nodeId === nodeId,
      )?.displayName;
      setNotice(
        `${nodeName ?? "The selected device"} is ready as the ${plainRoleName(role).toLowerCase()}.`,
      );
    });

  const changeSessionState = (
    action: "arm" | "disarm" | "start" | "pause" | "stop",
  ) =>
    runAction(`${capitalize(action)}ing session`, async () => {
      if (selectedSession === undefined)
        throw new Error("Select a session first.");
      const updated = await client.sessionAction(
        selectedSession.sessionId,
        action,
      );
      setSessions((current) => replaceSession(current, updated));
      setNotice(`Lesson status: ${plainSessionState(updated)}.`);
    });

  const stopAll = () =>
    runAction("Emergency stopping", async () => {
      const result = await client.stopAll();
      setNotice(
        `Emergency stop ${result.status}: ${result.stoppedSessionIds.length} session(s), ` +
          `${result.stoppedNodeIds.length} adapter node(s).`,
      );
    });

  const findDevices = () =>
    runAction("Finding devices", async () => {
      const report = await client.scanDevices();
      setDiscovery(report);
      const connected = report.integrations.filter(
        (integration) => integration.status === "connected",
      ).length;
      const found = report.integrations.filter((integration) =>
        ["found", "ready"].includes(integration.status),
      ).length;
      setNotice(
        `Device check finished: ${connected} connected, ${found} found or ready. Review the cards below for anything that still needs setup.`,
      );
    });

  const connectDiscovered = (integration: FabricIntegrationDiscovery) =>
    runAction(`Connecting ${integration.displayName}`, async () => {
      if (integration.actionId === undefined) {
        throw new Error("This integration needs its setup command first.");
      }
      const confirmed =
        groundedConfirmations[integration.integrationId] === true;
      if (integration.requiresGroundedConfirmation && !confirmed) {
        throw new Error(
          "Confirm that every aircraft is grounded before connecting.",
        );
      }
      const result = await client.runDiscoveryAction(
        integration.actionId,
        confirmed,
      );
      setDiscovery(result.report);
      setNotice(result.message);
    });

  const connectAllDiscovered = () =>
    runAction("Connecting available devices", async () => {
      if (connectableIntegrations.length === 0) {
        throw new Error(
          "No verified connection is ready. Follow the Setup needed cards, then find devices again.",
        );
      }
      if (!allAircraftGrounded) {
        throw new Error(
          "Confirm that every aircraft is grounded before connecting all available devices.",
        );
      }

      let latestReport = discovery;
      const connectedNames: string[] = [];
      const failures: string[] = [];
      for (const integration of connectableIntegrations) {
        if (integration.actionId === undefined) continue;
        try {
          const result = await client.runDiscoveryAction(
            integration.actionId,
            integration.requiresGroundedConfirmation,
          );
          latestReport = result.report;
          connectedNames.push(integration.displayName);
        } catch (caught) {
          failures.push(
            `${integration.displayName}: ${describeFabricError(caught)}`,
          );
        }
      }
      if (latestReport !== null) setDiscovery(latestReport);

      const connectionSummary =
        connectedNames.length === 0
          ? "No connection completed."
          : `Connection completed for ${connectedNames.length} device group${connectedNames.length === 1 ? "" : "s"}: ${connectedNames.join(", ")}.`;
      setNotice(
        `${connectionSummary} Physical outputs remain disarmed until a tutor starts an approved lesson.`,
      );
      if (failures.length > 0) {
        setError(`Some devices still need attention. ${failures.join(" ")}`);
      }
    });

  const copySetupCommand = (integration: FabricIntegrationDiscovery) =>
    runAction(`Copying ${integration.displayName} setup`, async () => {
      if (integration.setupCommand === undefined) {
        throw new Error("No setup command is available for this integration.");
      }
      if (navigator.clipboard === undefined) {
        throw new Error("Clipboard access is unavailable in this browser.");
      }
      await navigator.clipboard.writeText(integration.setupCommand);
      setNotice(
        `${integration.displayName} setup command copied. Paste it into PowerShell on this tutor computer.`,
      );
    });

  const startMetaCameraPairing = () =>
    runAction("Preparing Meta camera pairing", async () => {
      const pairing = await client.createMediaPairing(
        siteId.trim(),
        roomId.trim(),
      );
      setMediaPairing(pairing);
      setNotice(
        "Meta camera pairing is ready for five minutes. Enter the address and one-time code in the phone companion.",
      );
    });

  const copyMediaPairingValue = (value: string, label: string) =>
    runAction(`Copying ${label}`, async () => {
      if (navigator.clipboard === undefined) {
        throw new Error("Clipboard access is unavailable in this browser.");
      }
      await navigator.clipboard.writeText(value);
      setNotice(
        `${label} copied. Paste it into the CIT Meta Camera phone companion.`,
      );
    });

  const checkInput = () =>
    runAction("Testing input", async () => {
      if (selectedSession === undefined)
        throw new Error("Select a session first.");
      const bindings = new Set(
        selectedSession.roleBindings.map((binding) => binding.nodeId),
      );
      const latest = (await client.listEvents(selectedSession.sessionId))
        .filter((item) => bindings.has(item.event.sourceNodeId))
        .at(-1);
      if (latest === undefined) {
        throw new Error(
          "No semantic input has arrived from an assigned node yet.",
        );
      }
      setEvents(await client.listEvents(selectedSession.sessionId));
      const sourceName =
        nodes.find((node) => node.nodeId === latest.event.sourceNodeId)
          ?.displayName ?? "an assigned device";
      setNotice(
        `Student input was received from ${sourceName} at ${formatTime(latest.event.timestamp)}.`,
      );
    });

  const sendTestCommand = (kind: "agent" | "display" | "robot-stop") =>
    runAction(`Testing ${kind}`, async () => {
      if (selectedSession === undefined)
        throw new Error("Select a session first.");
      if (kind !== "robot-stop" && selectedSession.state !== "active") {
        throw new Error("Start the session before testing an output.");
      }
      const role =
        kind === "agent"
          ? "coding_agent"
          : kind === "display"
            ? "primary_glasses"
            : "student_robot";
      const action =
        kind === "agent"
          ? "agent.prompt.submit"
          : kind === "display"
            ? "display.text.render"
            : "mobility.ground.stop";
      const parameters =
        kind === "agent"
          ? {
              prompt:
                "Reply with a short CIT Fabric connectivity acknowledgement.",
            }
          : kind === "display"
            ? { text: "CIT Fabric display test" }
            : {};
      if (
        !selectedSession.roleBindings.some((binding) => binding.role === role)
      ) {
        throw new Error(`Assign ${role} before running this test.`);
      }
      const correlationId = crypto.randomUUID();
      const priority: FabricCommandPriority =
        principal?.roles.some((roleName) =>
          ["administrator", "instructor"].includes(roleName),
        ) === true
          ? "instructor_override"
          : "lesson_automation";
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action,
        target: { role },
        sessionId: selectedSession.sessionId,
        parameters,
        priority,
        idempotencyKey: `console-test:${kind}:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 2_000,
        safetyProfile: selectedSession.safetyProfile,
        correlationId,
      });
      const terminal = result.lifecycle.at(-1);
      const label =
        kind === "agent"
          ? "Agent"
          : kind === "display"
            ? "Display"
            : "Robot stop";
      setNotice(commandResultNotice(`${label} test`, terminal?.stage));
    });

  const setSmartPlugPower = (on: boolean) =>
    runAction(`Turning smart plug ${on ? "on" : "off"}`, async () => {
      if (selectedSession === undefined)
        throw new Error("Select a smart-plug session first.");
      if (smartPlugBinding === undefined)
        throw new Error("Assign classroom_plug before controlling power.");
      if (on && selectedSession.state !== "active")
        throw new Error("Start the session before turning on a load.");
      if (on && selectedSession.mode === "physical" && !selectedSession.armed)
        throw new Error("Arm the physical session before turning on a load.");
      const correlationId = crypto.randomUUID();
      const priority: FabricCommandPriority =
        principal?.roles.some((roleName) =>
          ["administrator", "instructor"].includes(roleName),
        ) === true
          ? "instructor_override"
          : "lesson_automation";
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: POWER_SET_CAPABILITY,
        target: { role: "classroom_plug" },
        sessionId: selectedSession.sessionId,
        parameters: { on },
        priority,
        idempotencyKey: `console-smart-plug:${on ? "on" : "off"}:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 2_000,
        safetyProfile: selectedSession.safetyProfile,
        correlationId,
      });
      const terminal = result.lifecycle.at(-1);
      setNotice(
        commandResultNotice(
          `Turning the classroom plug ${on ? "on" : "off"}`,
          terminal?.stage,
        ),
      );
    });

  const analyzeMediaSource = (source: FabricMediaSource) =>
    runAction(`Recognizing objects in ${source.displayName}`, async () => {
      const analysis = await client.analyzeMediaSource(source.sourceId);
      setMediaSources((current) =>
        current.map((item) =>
          item.sourceId === source.sourceId
            ? { ...item, latestAnalysis: analysis }
            : item,
        ),
      );
      const labels = analysis.detections.map((item) => item.label);
      setNotice(
        labels.length === 0
          ? `No configured objects were recognized in ${source.displayName}.`
          : `Recognized ${labels.join(", ")} in ${source.displayName}. Review the boxes before choosing any device action.`,
      );
    });

  if (principal === null) {
    return (
      <div className="fabric-console fabric-login-shell">
        <section
          className="fabric-welcome"
          aria-labelledby="fabric-login-heading"
        >
          <div className="fabric-welcome-mark" aria-hidden="true">
            CIT
          </div>
          <p className="eyebrow">Classroom device control</p>
          <h1 id="fabric-login-heading">
            {autoConnecting
              ? "Opening your classroom…"
              : "Welcome to CIT Classroom Control"}
          </h1>
          <p className="fabric-welcome-lead">
            {autoConnecting
              ? "Securely connecting to the devices on this computer."
              : "Set up a lesson, connect devices, check safety, and teach from one screen."}
          </p>

          {autoConnecting ? (
            <div className="fabric-connecting" role="status">
              <span className="fabric-spinner" aria-hidden="true" />
              <div>
                <strong>Just a moment</strong>
                <small>The launcher is completing local sign-in.</small>
              </div>
            </div>
          ) : (
            <div className="fabric-welcome-actions">
              <div className="fabric-launch-instruction">
                <span>1</span>
                <div>
                  <strong>Use the CIT button</strong>
                  <p>
                    Open CIT Classroom Control from the Windows Desktop or Start
                    menu, then choose Start classroom devices. CIT will reopen
                    this page and sign you in automatically.
                  </p>
                </div>
              </div>
              <div className="fabric-launch-instruction">
                <span>2</span>
                <div>
                  <strong>Continue in the browser</strong>
                  <p>
                    Choose a lesson, connect devices, check safety, and teach.
                    No account or device password is needed.
                  </p>
                </div>
              </div>
              <button
                className="fabric-secondary-link"
                type="button"
                aria-expanded={showAccessCode}
                onClick={() => setShowAccessCode((current) => !current)}
              >
                {showAccessCode
                  ? "Hide access-code sign in"
                  : "Launcher unavailable? Use an access code"}
              </button>
            </div>
          )}

          {showAccessCode && !autoConnecting && (
            <form className="fabric-access-form" onSubmit={signIn}>
              <div>
                <strong>Paste your classroom access code</strong>
                <small>
                  Use this recovery option only if automatic opening failed. Ask
                  the classroom technician for a temporary access code.
                </small>
              </div>
              <label htmlFor="fabric-credential">
                Access code
                <input
                  id="fabric-credential"
                  type="password"
                  autoComplete="off"
                  minLength={32}
                  maxLength={512}
                  required
                  placeholder="Paste access code"
                  value={credential}
                  onChange={(event) => setCredential(event.target.value)}
                />
              </label>
              <button type="submit" disabled={busy !== null}>
                {busy ?? "Continue to classroom controls"}
              </button>
              <small>
                The code stays in this tab only and is cleared when you sign out
                or reload.
              </small>
            </form>
          )}
          {error !== null && <div className="fabric-error">{error}</div>}
          {!autoConnecting && (
            <p className="fabric-welcome-help">
              Need help? Ask the classroom technician to start the local CIT
              service. Device credentials never belong in this box.
            </p>
          )}
        </section>
      </div>
    );
  }

  const nodeGroups = groupNodesByIo(availableNodes);

  return (
    <div className="fabric-console">
      <header className="fabric-header">
        <div>
          <p className="eyebrow">CIT classroom</p>
          <h1>Classroom Control</h1>
        </div>
        <div className="fabric-identity">
          <span className="status-dot status-ok" />
          <div>
            <strong>Connected locally</strong>
            <small title={principal.identityId}>Tutor controls</small>
          </div>
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </div>
        <button
          className="fabric-emergency"
          type="button"
          disabled={!canStopAll || busy !== null}
          onClick={() => void stopAll()}
        >
          <span>■</span> Stop all devices
        </button>
      </header>

      <main className="fabric-main">
        <div className="fabric-feedback" aria-live="polite">
          <span>{notice}</span>
          {busy !== null && <strong>{busy}…</strong>}
          <button type="button" onClick={() => void refresh(true)}>
            Refresh
          </button>
        </div>
        {error !== null && (
          <div className="fabric-error" role="alert">
            {error}
          </div>
        )}

        <section className="fabric-next-step" aria-labelledby="next-step-title">
          <div className="fabric-guide-copy">
            <p className="eyebrow">Your next step</p>
            <h2 id="next-step-title">{guide.title}</h2>
            <p>{guide.description}</p>
            <button
              className="fabric-primary-action"
              type="button"
              disabled={guide.stage === "find_devices" && busy !== null}
              onClick={() => {
                if (guide.stage === "find_devices") {
                  void findDevices();
                  return;
                }
                document
                  .getElementById(guide.targetId)
                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              {guide.stage === "find_devices"
                ? "Find devices"
                : guide.stage === "choose_lesson"
                  ? "Choose a lesson"
                  : guide.stage === "connect_devices"
                    ? "Choose devices"
                    : guide.stage === "teach"
                      ? "Go to live controls"
                      : guide.stage === "lesson_ended"
                        ? "Set up another lesson"
                        : "Review and start"}
            </button>
          </div>
          <ol className="fabric-steps" aria-label="Lesson setup progress">
            {[
              "Find devices",
              "Choose lesson",
              "Assign devices",
              "Safety check",
              "Teach",
            ].map((label, index) => {
              const step = index + 1;
              return (
                <li
                  className={
                    step < guide.step
                      ? "is-complete"
                      : step === guide.step
                        ? "is-current"
                        : undefined
                  }
                  key={label}
                >
                  <span>{step < guide.step ? "✓" : step}</span>
                  <strong>{label}</strong>
                </li>
              );
            })}
          </ol>
        </section>

        <section
          className="fabric-panel fabric-discovery-panel"
          id="device-discovery"
          aria-labelledby="device-discovery-title"
        >
          <div className="fabric-discovery-heading">
            <div>
              <p className="eyebrow">Step 1</p>
              <h2 id="device-discovery-title">Find classroom devices</h2>
              <p className="fabric-panel-intro">
                Power devices on, plug in USB equipment, and choose Find
                devices. CIT checks this computer, USB, Bluetooth readiness,
                local services, Wi-Fi radios, and visible Tello networks.
              </p>
            </div>
            <button
              className="fabric-primary-action fabric-find-devices"
              type="button"
              disabled={busy !== null}
              onClick={() => void findDevices()}
            >
              {busy === "Finding devices" ? "Checking…" : "Find devices"}
              <small>No device will move, fly, or switch on</small>
            </button>
          </div>

          <div className="fabric-discovery-safety">
            <span aria-hidden="true">✓</span>
            <div>
              <strong>Safe discovery only</strong>
              <p>
                Finding devices never arms robots, starts propellers, moves a
                motor, turns on a plug, starts an agent, or stores raw audio,
                video, or biosignals.
              </p>
            </div>
          </div>

          {connectableIntegrations.length > 0 && (
            <div className="fabric-connect-all">
              <div>
                <strong>
                  {connectableIntegrations.length} safe connection
                  {connectableIntegrations.length === 1 ? "" : "s"} ready
                </strong>
                <p>
                  Connect every verified adapter in one step. Robots, drones,
                  plugs, and lesson sessions remain disarmed.
                </p>
                {groundedConnections.length > 0 && (
                  <label className="fabric-grounded-confirmation">
                    <input
                      type="checkbox"
                      checked={allAircraftGrounded}
                      onChange={(event) => {
                        const confirmed = event.target.checked;
                        setGroundedConfirmations((current) => ({
                          ...current,
                          ...Object.fromEntries(
                            groundedConnections.map((integration) => [
                              integration.integrationId,
                              confirmed,
                            ]),
                          ),
                        }));
                      }}
                    />
                    <span>
                      Every aircraft is grounded; propellers are removed or
                      guarded.
                    </span>
                  </label>
                )}
              </div>
              <button
                className="fabric-primary-action fabric-connect-all-button"
                type="button"
                disabled={
                  !discoveryConnectionsEnabled ||
                  busy !== null ||
                  !allAircraftGrounded
                }
                onClick={() => void connectAllDiscovered()}
              >
                {busy === "Connecting available devices"
                  ? "Connecting…"
                  : "Connect all available"}
                <small>
                  {discovery?.physicalActuationEnabled
                    ? "Connect only — no movement or switching"
                    : "Start the physical device host first"}
                </small>
              </button>
            </div>
          )}

          {discovery !== null && (
            <div className="fabric-discovery-meta">
              <span>
                {discoveryScanned
                  ? `Checked ${formatTime(discovery.scannedAt)}`
                  : "Not checked yet"}
              </span>
              <span>{discovery.hostId}</span>
              <span>
                Physical control is{" "}
                {discovery.physicalActuationEnabled
                  ? "available but locked"
                  : "disabled in this runtime"}
              </span>
            </div>
          )}

          {(discovery?.warnings.length ?? 0) > 0 && (
            <div className="fabric-discovery-warnings" role="status">
              <strong>Some checks need attention</strong>
              <ul>
                {discovery?.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="fabric-discovery-grid">
            {discovery?.integrations.map((integration) => (
              <FabricDiscoveryCard
                key={integration.integrationId}
                integration={integration}
                busy={busy}
                canConnect={discoveryConnectionsEnabled}
                groundedConfirmed={
                  groundedConfirmations[integration.integrationId] === true
                }
                onGroundedChange={(confirmed) =>
                  setGroundedConfirmations((current) => ({
                    ...current,
                    [integration.integrationId]: confirmed,
                  }))
                }
                onConnect={() => void connectDiscovered(integration)}
                onCopySetup={() => void copySetupCommand(integration)}
              />
            ))}
            {discovery === null && (
              <div className="fabric-empty-state fabric-discovery-loading">
                <span aria-hidden="true">…</span>
                <strong>Loading the device checklist</strong>
                <p>CIT is preparing the supported hardware list.</p>
              </div>
            )}
          </div>
        </section>

        <section className="fabric-overview" aria-label="Classroom status">
          <FabricMetric
            label="Connected devices"
            value={
              availableNodes.length === 0
                ? "None yet"
                : String(availableNodes.length)
            }
          />
          <FabricMetric
            label="Current lesson"
            value={
              selectedSession === undefined
                ? sessions.length > 0
                  ? "Select a lesson"
                  : "Not set up"
                : courseName(coursePacks, selectedSession)
            }
          />
          <FabricMetric
            label="Lesson status"
            value={plainSessionState(selectedSession)}
          />
          <FabricMetric
            label="Physical devices"
            value={
              selectedSession?.mode === "physical"
                ? selectedSession.armed
                  ? "Enabled"
                  : "Locked"
                : "Locked"
            }
            warning={selectedSession?.armed === true}
          />
        </section>

        <section className="fabric-grid fabric-setup-grid">
          <article
            className="fabric-panel fabric-session-builder"
            id="lesson-setup"
          >
            <PanelHeading eyebrow="Step 2" title="Choose a lesson" />
            <p className="fabric-panel-intro">
              What do you want students to do today?
            </p>
            <div className="fabric-course-choices">
              {coursePacks.map((coursePack) => {
                const key = courseKey(
                  coursePack.coursePackId,
                  coursePack.version,
                );
                const chosenKey = selectedSession
                  ? courseKey(
                      selectedSession.coursePackId,
                      selectedSession.coursePackVersion,
                    )
                  : selectedCourseKey;
                return (
                  <button
                    className={key === chosenKey ? "is-selected" : undefined}
                    type="button"
                    key={key}
                    disabled={selectedSession?.state === "active"}
                    onClick={() => {
                      setSelectedSessionId("");
                      setSelectedCourseKey(key);
                    }}
                  >
                    <strong>{plainCourseName(coursePack)}</strong>
                    <small>{plainCourseSummary(coursePack)}</small>
                    <span>{key === chosenKey ? "Selected" : "Choose"}</span>
                  </button>
                );
              })}
            </div>
            {selectedCourse !== undefined && (
              <p className="fabric-course-description">
                {plainCourseDescription(selectedCourse)}
              </p>
            )}
            <details className="fabric-settings">
              <summary>Room and device settings</summary>
              <div className="fabric-fields">
                <label>
                  Site
                  <input
                    value={siteId}
                    onChange={(event) => setSiteId(event.target.value)}
                  />
                </label>
                <label>
                  Room
                  <input
                    value={roomId}
                    onChange={(event) => setRoomId(event.target.value)}
                  />
                </label>
              </div>
              <label>
                Devices used in this lesson
                <select
                  value={sessionMode}
                  onChange={(event) =>
                    setSessionMode(
                      event.target.value as "simulation" | "physical",
                    )
                  }
                >
                  <option value="simulation">
                    Simulators only — safest for practice
                  </option>
                  <option value="physical">
                    Real classroom devices — safety check required
                  </option>
                </select>
              </label>
            </details>
            <button
              className="fabric-primary-action fabric-wide-action"
              type="button"
              disabled={
                !canManageSessions ||
                busy !== null ||
                !selectedCourseKey ||
                selectedSession?.state === "active"
              }
              onClick={() => void createSession()}
            >
              Set up this lesson
            </button>
            {sessions.length > 0 && (
              <label className="fabric-existing-session">
                Or continue a session already set up
                <select
                  value={selectedSessionId}
                  onChange={(event) => setSelectedSessionId(event.target.value)}
                >
                  <option value="">Choose an existing session</option>
                  {sessions.map((session) => (
                    <option key={session.sessionId} value={session.sessionId}>
                      {courseName(coursePacks, session)} ·{" "}
                      {plainSessionState(session)} ·{" "}
                      {formatTime(session.updatedAt)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </article>

          <article
            className="fabric-panel fabric-session-control"
            id="device-setup"
          >
            <PanelHeading eyebrow="Step 3" title="Assign lesson devices" />
            <p className="fabric-panel-intro">
              CIT only shows devices that can perform each job in this lesson.
            </p>
            {selectedSession !== undefined && selectedCourse !== undefined ? (
              <div className="fabric-role-list">
                {selectedCourse.roles.map((requirement) => {
                  const candidates = compatibleNodes(
                    nodes,
                    selectedSession,
                    requirement,
                  );
                  const binding = selectedSession.roleBindings.find(
                    (candidate) => candidate.role === requirement.role,
                  );
                  return (
                    <div className="fabric-role" key={requirement.role}>
                      <span
                        className={`fabric-role-status ${binding === undefined ? "is-missing" : "is-ready"}`}
                        aria-hidden="true"
                      >
                        {binding === undefined ? "!" : "✓"}
                      </span>
                      <div>
                        <strong>{plainRoleName(requirement.role)}</strong>
                        <small>
                          {roleDescription(requirement.role)}
                          {requirement.optional ? " (optional)" : ""}
                        </small>
                      </div>
                      <select
                        aria-label={`Device for ${plainRoleName(requirement.role)}`}
                        value={roleSelections[requirement.role] ?? ""}
                        disabled={
                          !canAssignRoles || selectedSession.state === "active"
                        }
                        onChange={(event) =>
                          setRoleSelections((current) => ({
                            ...current,
                            [requirement.role]: event.target.value,
                          }))
                        }
                      >
                        <option value="">
                          {candidates.length === 0
                            ? "No matching device connected"
                            : "Choose a device"}
                        </option>
                        {candidates.map((node) => (
                          <option key={node.nodeId} value={node.nodeId}>
                            {node.displayName} · {plainConnectionState(node)}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={
                          !canAssignRoles ||
                          busy !== null ||
                          selectedSession.state === "active" ||
                          !roleSelections[requirement.role] ||
                          binding?.nodeId === roleSelections[requirement.role]
                        }
                        onClick={() => void assignRole(requirement.role)}
                      >
                        {binding === undefined ? "Use this device" : "Change"}
                      </button>
                      {candidates.length === 0 && (
                        <p className="fabric-role-help">
                          Start the device’s CIT adapter, then choose Refresh at
                          the top of this page.
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="fabric-empty-state">
                <span aria-hidden="true">2</span>
                <strong>Choose and set up a lesson first</strong>
                <p>Your matching devices will appear here automatically.</p>
              </div>
            )}
          </article>
        </section>

        <section
          className={`fabric-panel fabric-safety-panel ${selectedSession?.armed ? "is-armed" : "is-safe"}`}
          id="lesson-safety"
        >
          <div className="fabric-safety-summary">
            <span className="fabric-safety-icon" aria-hidden="true">
              {selectedSession?.armed ? "!" : "✓"}
            </span>
            <div>
              <PanelHeading eyebrow="Step 4" title="Review and start" />
              <strong>
                {selectedSession === undefined
                  ? "Set up a lesson to continue"
                  : selectedSession.mode === "simulation"
                    ? "Simulation mode — physical devices stay locked"
                    : selectedSession.armed
                      ? "Physical device control is enabled"
                      : "Physical devices are locked"}
              </strong>
              <p>
                {selectedSession?.mode === "physical"
                  ? "Keep the Stop all devices button visible and make sure the activity area is clear."
                  : "Practice safely before switching this lesson to real classroom hardware."}
              </p>
            </div>
          </div>

          {selectedSession?.mode === "physical" && !selectedSession.armed && (
            <label className="fabric-safety-confirmation">
              <input
                type="checkbox"
                checked={safetyConfirmed}
                onChange={(event) => setSafetyConfirmed(event.target.checked)}
              />
              <span>
                I can see the devices, the activity area is clear, and I know
                where “Stop all devices” is.
              </span>
            </label>
          )}

          <div className="fabric-session-actions">
            {selectedSession?.mode === "physical" && !selectedSession.armed && (
              <button
                className="fabric-enable-physical"
                type="button"
                disabled={
                  !canManageSessions ||
                  busy !== null ||
                  !requiredRolesReady ||
                  !safetyConfirmed ||
                  !["ready", "paused"].includes(selectedSession.state)
                }
                onClick={() => void changeSessionState("arm")}
              >
                Enable physical controls
              </button>
            )}
            {selectedSession?.armed && (
              <button
                type="button"
                disabled={!canManageSessions || busy !== null}
                onClick={() => void changeSessionState("disarm")}
              >
                Lock physical devices
              </button>
            )}
            <button
              className="fabric-primary-action"
              type="button"
              disabled={
                !canManageSessions ||
                busy !== null ||
                !requiredRolesReady ||
                !["ready", "paused"].includes(selectedSession?.state ?? "") ||
                (selectedSession?.mode === "physical" &&
                  selectedSession.armed !== true)
              }
              onClick={() => void changeSessionState("start")}
            >
              {selectedSession?.state === "paused"
                ? "Resume lesson"
                : "Start lesson"}
            </button>
            {selectedSession?.state === "active" && (
              <button
                type="button"
                disabled={!canManageSessions || busy !== null}
                onClick={() => void changeSessionState("pause")}
              >
                Pause lesson
              </button>
            )}
            <button
              type="button"
              disabled={
                !canManageSessions ||
                busy !== null ||
                selectedSession === undefined ||
                ["stopped", "emergency_stopped", "failed"].includes(
                  selectedSession.state,
                )
              }
              onClick={() => void changeSessionState("stop")}
            >
              End lesson and lock devices
            </button>
          </div>
        </section>

        <section className="fabric-panel fabric-test-panel" id="live-controls">
          <PanelHeading eyebrow="Step 5" title="Teach and test" />
          <p className="fabric-panel-intro">
            {selectedSession?.state === "active"
              ? "The lesson is running. Use only the checks that match today’s activity."
              : "Start the lesson in Step 4 to unlock its teaching controls."}
          </p>
          <div className="fabric-test-actions">
            {(selectedCourse?.flows.length ?? 0) > 0 && (
              <button
                type="button"
                disabled={selectedSession?.state !== "active" || busy !== null}
                onClick={() => void checkInput()}
              >
                Check student input
                <small>Ask for a gesture, button press, or voice input</small>
              </button>
            )}
            {selectedCourse?.roles.some(
              (requirement) => requirement.role === "coding_agent",
            ) && (
              <button
                type="button"
                disabled={
                  !canSubmitCommands ||
                  selectedSession?.state !== "active" ||
                  busy !== null
                }
                onClick={() => void sendTestCommand("agent")}
              >
                Check coding assistant
                <small>Send one safe connectivity message</small>
              </button>
            )}
            {selectedCourse?.roles.some(
              (requirement) => requirement.role === "primary_glasses",
            ) && (
              <button
                type="button"
                disabled={
                  !canSubmitCommands ||
                  selectedSession?.state !== "active" ||
                  busy !== null
                }
                onClick={() => void sendTestCommand("display")}
              >
                Check glasses display
                <small>Show one fixed classroom message</small>
              </button>
            )}
            {selectedCourse?.roles.some(
              (requirement) => requirement.role === "student_robot",
            ) && (
              <button
                type="button"
                disabled={
                  !canSubmitCommands ||
                  selectedSession === undefined ||
                  busy !== null ||
                  !selectedSession.roleBindings.some(
                    (binding) => binding.role === "student_robot",
                  )
                }
                onClick={() => void sendTestCommand("robot-stop")}
              >
                Check robot stop
                <small>Confirm the robot accepts its safe stop command</small>
              </button>
            )}
            <div className="fabric-live-state">
              <span
                className={`status-dot ${selectedSession?.state === "active" ? "status-ok" : "status-muted"}`}
              />
              <div>
                <strong>
                  {selectedSession?.state === "active"
                    ? "Lesson is running"
                    : "Teaching controls are waiting"}
                </strong>
                <small>
                  {countActiveFabricCommands(lifecycle)} device action(s) in
                  progress
                </small>
              </div>
            </div>
          </div>
        </section>

        {canReadMedia && (
          <section className="fabric-panel fabric-media-panel">
            <PanelHeading
              eyebrow="Classroom vision"
              title="Live cameras and object recognition"
            />
            <p className="fabric-help">
              Meta glasses, RoboMaster, Tello, and other approved local camera
              publishers appear together here. Frames stay in memory, are not
              added to lesson recordings, and are replaced by the next frame.
            </p>
            {canPairMedia && (
              <div className="fabric-camera-pairing">
                <div>
                  <strong>Connect a Meta glasses camera</strong>
                  <span>
                    Keep the phone on the classroom Wi-Fi, then pair the CIT
                    Meta Camera companion. Start live sharing on the phone;
                    older glasses firmware can use the snapshot fallback.
                  </span>
                </div>
                {mediaPairing === null ? (
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => void startMetaCameraPairing()}
                  >
                    Create phone pairing
                  </button>
                ) : (
                  <div className="fabric-camera-pairing-details">
                    <ol>
                      <li>Open CIT Meta Camera on the Android phone.</li>
                      <li>
                        Enter the classroom address and one-time code below.
                      </li>
                      <li>
                        Tap Pair, approve Meta camera access, then tap Share
                        live camera. Use snapshot fallback only if live frames
                        fail.
                      </li>
                    </ol>
                    <label>
                      Classroom address
                      <span>
                        <input readOnly value={mediaPairing.fabricOrigin} />
                        <button
                          type="button"
                          onClick={() =>
                            void copyMediaPairingValue(
                              mediaPairing.fabricOrigin,
                              "Classroom address",
                            )
                          }
                        >
                          Copy
                        </button>
                      </span>
                    </label>
                    <label>
                      One-time pairing code
                      <span>
                        <input readOnly value={mediaPairing.pairingCode} />
                        <button
                          type="button"
                          onClick={() =>
                            void copyMediaPairingValue(
                              mediaPairing.pairingCode,
                              "Pairing code",
                            )
                          }
                        >
                          Copy
                        </button>
                      </span>
                    </label>
                    <small>
                      Expires {formatTime(mediaPairing.expiresAt)} and works
                      once. The phone receives publish-only access for{" "}
                      {mediaPairing.siteId}/{mediaPairing.roomId}; it cannot
                      read cameras or control devices.
                    </small>
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => void startMetaCameraPairing()}
                    >
                      Replace with a new code
                    </button>
                  </div>
                )}
              </div>
            )}
            {mediaSources.length === 0 ? (
              <div className="fabric-empty fabric-media-empty">
                <strong>No camera source is publishing yet.</strong>
                <span>
                  Start an approved camera bridge. Meta glasses require the CIT
                  phone companion, camera permission, and visible camera-use
                  indicator.
                </span>
              </div>
            ) : (
              <div className="fabric-media-grid">
                {mediaSources.map((source) => (
                  <MediaFeedCard
                    key={source.sourceId}
                    source={source}
                    client={client}
                    busy={busy !== null}
                    canAnalyze={canAnalyzeVision}
                    canTurnPlugOn={canTurnSmartPlugOn}
                    canTurnPlugOff={canTurnSmartPlugOff}
                    smartPlugName={selectedSmartPlug?.displayName}
                    onAnalyze={() => void analyzeMediaSource(source)}
                    onPower={(on) => void setSmartPlugPower(on)}
                  />
                ))}
              </div>
            )}
            <p className="fabric-privacy-note">
              Object recognition never operates a robot, drone, or plug by
              itself. A tutor must review the detection and press an explicit
              bounded control.
            </p>
          </section>
        )}

        <section className="fabric-panel fabric-sensor-panel">
          <PanelHeading eyebrow="Live sensors" title="Classroom readings" />
          <p className="fabric-help">
            The latest normalized LEGO, robot, biosignal, and battery readings
            appear automatically when an adapter publishes them.
          </p>
          {sensorReadings.length === 0 ? (
            <div className="fabric-empty">
              No sensor readings have arrived in the selected lesson yet.
            </div>
          ) : (
            <div className="fabric-sensor-grid">
              {sensorReadings.map((reading) => (
                <article className="fabric-sensor-card" key={reading.key}>
                  <header>
                    <strong>{plainCapabilityName(reading.topic)}</strong>
                    <span>{formatTime(reading.observedAt)}</span>
                  </header>
                  <div className="fabric-sensor-values">
                    {reading.values.map((value) => (
                      <div key={value.label}>
                        <span>{value.label}</span>
                        <strong>{value.value}</strong>
                      </div>
                    ))}
                  </div>
                  <small>{nodeDisplayName(nodes, reading.sourceNodeId)}</small>
                </article>
              ))}
            </div>
          )}
        </section>

        {(smartPlugNodes.length > 0 ||
          selectedCourse?.roles.some(
            (requirement) => requirement.role === "classroom_plug",
          )) && (
          <section className="fabric-panel fabric-smart-plug-panel">
            <PanelHeading eyebrow="Lesson control" title="Classroom plug" />
            <div className="fabric-smart-plug-layout">
              <div className="fabric-smart-plug-state">
                <span
                  className={`fabric-plug-indicator ${smartPlugState?.on ? "is-on" : "is-off"}`}
                  aria-hidden="true"
                >
                  {smartPlugState?.on ? "ON" : "OFF"}
                </span>
                <div>
                  <strong>
                    {selectedSmartPlug?.displayName ??
                      "No classroom plug assigned"}
                  </strong>
                  <small>
                    {selectedSmartPlug === undefined
                      ? `${smartPlugNodes.length} compatible ${smartPlugNodes.length === 1 ? "device" : "devices"} connected`
                      : `${metadataText(selectedSmartPlug, "vendorBrand") ?? "compatible"} · ${metadataText(selectedSmartPlug, "model") ?? selectedSmartPlug.nodeId}`}
                  </small>
                  <small>
                    {smartPlugState === undefined
                      ? "State has not been observed in this session"
                      : `Observed ${formatTime(smartPlugState.observedAt)}${smartPlugState.source === undefined ? "" : ` · ${smartPlugState.source}`}`}
                  </small>
                </div>
              </div>
              <div className="fabric-smart-plug-actions">
                <button
                  className="fabric-power-on"
                  type="button"
                  disabled={!canTurnSmartPlugOn}
                  onClick={() => void setSmartPlugPower(true)}
                >
                  Turn on
                  <small>
                    {selectedSession?.state === "active" &&
                    (selectedSession.mode !== "physical" ||
                      selectedSession.armed)
                      ? "Turn on the approved classroom load"
                      : "Available after the lesson safety check"}
                  </small>
                </button>
                <button
                  className="fabric-power-off"
                  type="button"
                  disabled={!canTurnSmartPlugOff}
                  onClick={() => void setSmartPlugPower(false)}
                >
                  Turn off
                  <small>Always available as the safe state</small>
                </button>
              </div>
            </div>
            <p className="fabric-help">
              Use only the approved classroom load. The tutor can always turn it
              off, even when physical controls are locked.
            </p>
          </section>
        )}

        <section className="fabric-panel fabric-node-panel">
          <PanelHeading
            eyebrow="Device status"
            title="Everything connected to this classroom"
          />
          <p className="fabric-help">
            Glasses, sensors, robots, smart plugs, coding assistants, and
            simulators all appear here when their CIT adapter is running.
          </p>
          <div className="fabric-io-groups">
            <FabricNodeGroup
              kind="input"
              title="Sends information"
              description="Gestures, voice, buttons, and sensors"
              nodes={nodeGroups.input}
            />
            <FabricNodeGroup
              kind="bidirectional"
              title="Sends and receives"
              description="Glasses, robots, agents, and smart devices"
              nodes={nodeGroups.bidirectional}
            />
            <FabricNodeGroup
              kind="output"
              title="Receives instructions"
              description="Displays, lights, and other controlled devices"
              nodes={nodeGroups.output}
            />
          </div>
        </section>

        <details className="fabric-advanced">
          <summary>
            <strong>Technical diagnostics</strong>
            <span>
              Signals, command history, identifiers, and audit records
            </span>
          </summary>
          <section className="fabric-grid fabric-stream-grid">
            <article className="fabric-panel">
              <PanelHeading eyebrow="Device signals" title="Recent activity" />
              <ol className="fabric-stream-list">
                {[...events]
                  .reverse()
                  .slice(0, 12)
                  .map((item) => (
                    <li key={item.streamSequence}>
                      <span>{item.streamSequence}</span>
                      <div>
                        <strong>{item.event.topic}</strong>
                        <small>
                          {item.event.sourceNodeId} ·{" "}
                          {formatTime(item.event.timestamp)}
                        </small>
                      </div>
                      <em>{Math.round((item.event.confidence ?? 1) * 100)}%</em>
                    </li>
                  ))}
                {events.length === 0 && (
                  <li className="fabric-empty">
                    No selected-session signals yet.
                  </li>
                )}
              </ol>
            </article>
            <article className="fabric-panel">
              <PanelHeading
                eyebrow="Device instructions"
                title="Command progress"
              />
              <ol className="fabric-stream-list">
                {[...lifecycle]
                  .reverse()
                  .slice(0, 12)
                  .map((item) => (
                    <li key={item.streamSequence}>
                      <span>{item.streamSequence}</span>
                      <div>
                        <strong>{item.lifecycle.stage}</strong>
                        <small>
                          {shortId(item.lifecycle.commandId)} ·{" "}
                          {item.lifecycle.targetNodeId}
                        </small>
                      </div>
                      <em>{formatTime(item.lifecycle.occurredAt)}</em>
                    </li>
                  ))}
                {lifecycle.length === 0 && (
                  <li className="fabric-empty">No command decisions yet.</li>
                )}
              </ol>
            </article>
          </section>

          {offlineNodeCount > 0 && (
            <section className="fabric-panel fabric-offline-history">
              <PanelHeading
                eyebrow="Adapter history"
                title={`${offlineNodeCount} offline ${offlineNodeCount === 1 ? "record" : "records"} hidden`}
              />
              <p className="fabric-help">
                Disconnected adapter records are retained for diagnostics and
                audit, but they are excluded from connected-device totals and
                lesson assignment choices.
              </p>
            </section>
          )}

          {audit.length > 0 && (
            <section className="fabric-panel fabric-audit-panel">
              <PanelHeading
                eyebrow="Audit history"
                title="Recent control changes"
              />
              <div className="fabric-audit-list">
                {audit.slice(0, 10).map((record) => (
                  <div key={record.auditId}>
                    <strong>{record.action}</strong>
                    <span>{record.actorId}</span>
                    <small>
                      {record.resourceId ?? record.resourceType} ·{" "}
                      {formatTime(record.occurredAt)}
                    </small>
                  </div>
                ))}
              </div>
            </section>
          )}
        </details>
      </main>
    </div>
  );
}

function PanelHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="fabric-panel-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
    </div>
  );
}

function FabricMetric({
  label,
  value,
  warning = false,
}: {
  label: string;
  value: string;
  warning?: boolean;
}) {
  return (
    <div className={warning ? "is-warning" : undefined}>
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function FabricDiscoveryCard({
  integration,
  busy,
  canConnect,
  groundedConfirmed,
  onGroundedChange,
  onConnect,
  onCopySetup,
}: {
  integration: FabricIntegrationDiscovery;
  busy: BusyAction;
  canConnect: boolean;
  groundedConfirmed: boolean;
  onGroundedChange: (confirmed: boolean) => void;
  onConnect: () => void;
  onCopySetup: () => void;
}) {
  const status = discoveryStatus(integration.status);
  const connected = integration.status === "connected";
  return (
    <article
      className={`fabric-discovery-card is-${integration.status.replaceAll("_", "-")}`}
    >
      <header>
        <span className="fabric-discovery-icon" aria-hidden="true">
          {DISCOVERY_ICONS[integration.integrationId] ?? "IO"}
        </span>
        <div>
          <h3>{integration.displayName}</h3>
          <small>{integration.connectionMethod}</small>
        </div>
        <strong className={`fabric-discovery-status is-${status.tone}`}>
          {status.label}
        </strong>
      </header>

      <p className="fabric-discovery-summary">{integration.summary}</p>

      {integration.candidates.length > 0 && (
        <ul className="fabric-candidate-list">
          {integration.candidates.map((candidate, index) => (
            <li key={`${candidate.candidateId}:${index}`}>
              <span
                className={`status-dot ${candidate.status === "found" ? "status-ok" : "status-muted"}`}
              />
              <div>
                <strong>{candidate.displayName}</strong>
                <small>
                  {candidate.transport}
                  {candidate.signalPercent === undefined
                    ? ""
                    : ` · ${candidate.signalPercent}% signal`}
                </small>
                <p>{candidate.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      )}

      {integration.requiresGroundedConfirmation &&
        integration.actionId !== undefined &&
        !connected && (
          <label className="fabric-grounded-confirmation">
            <input
              type="checkbox"
              checked={groundedConfirmed}
              onChange={(event) => onGroundedChange(event.target.checked)}
            />
            <span>
              Every aircraft is grounded; propellers are removed or guarded.
            </span>
          </label>
        )}

      <div className="fabric-discovery-actions">
        {integration.actionId !== undefined && !connected && (
          <button
            className="fabric-connect-device"
            type="button"
            disabled={
              !canConnect ||
              busy !== null ||
              (integration.requiresGroundedConfirmation && !groundedConfirmed)
            }
            onClick={onConnect}
          >
            {integration.actionLabel ?? "Connect"}
          </button>
        )}
        {integration.setupCommand !== undefined && !connected && (
          <button
            className="fabric-copy-setup"
            type="button"
            disabled={busy !== null}
            onClick={onCopySetup}
          >
            Copy setup command
          </button>
        )}
      </div>

      <details className="fabric-device-help">
        <summary>
          {connected ? "Connection details" : "What do I need to do?"}
        </summary>
        {integration.setupSteps.length > 0 && (
          <ol>
            {integration.setupSteps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        )}
        {integration.setupCommand !== undefined && !connected && (
          <code>{integration.setupCommand}</code>
        )}
        {integration.connectedNodeIds.length > 0 && (
          <small>CIT nodes: {integration.connectedNodeIds.join(", ")}</small>
        )}
        <p>{integration.safetyNote}</p>
      </details>
    </article>
  );
}

function MediaFeedCard({
  source,
  client,
  busy,
  canAnalyze,
  canTurnPlugOn,
  canTurnPlugOff,
  smartPlugName,
  onAnalyze,
  onPower,
}: {
  source: FabricMediaSource;
  client: FabricClient;
  busy: boolean;
  canAnalyze: boolean;
  canTurnPlugOn: boolean;
  canTurnPlugOff: boolean;
  smartPlugName: string | undefined;
  onAnalyze: () => void;
  onPower: (on: boolean) => void;
}) {
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [visibleSequence, setVisibleSequence] = useState(0);
  const [frameMessage, setFrameMessage] = useState("Waiting for first frame");
  const etag = useRef<string | undefined>(undefined);
  const frameUrlRef = useRef<string | null>(null);

  useEffect(
    () => () => {
      if (frameUrlRef.current !== null) {
        URL.revokeObjectURL(frameUrlRef.current);
        frameUrlRef.current = null;
      }
    },
    [],
  );

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const load = async () => {
      try {
        const frame = await client.getMediaFrame(source.sourceId, etag.current);
        if (!active) return;
        if (!frame.unchanged && frame.blob !== undefined) {
          const nextUrl = URL.createObjectURL(frame.blob);
          if (frameUrlRef.current !== null)
            URL.revokeObjectURL(frameUrlRef.current);
          frameUrlRef.current = nextUrl;
          etag.current = frame.etag;
          setFrameUrl(nextUrl);
          setVisibleSequence(frame.sequence ?? 0);
          setFrameMessage("");
        }
      } catch (caught) {
        if (!active) return;
        setFrameMessage(
          caught instanceof FabricApiError && caught.status === 404
            ? "Waiting for first frame"
            : describeFabricError(caught),
        );
      } finally {
        if (active) timer = window.setTimeout(() => void load(), 750);
      }
    };
    void load();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [client, source.sourceId]);

  const analysis = source.latestAnalysis;
  const overlayVisible =
    analysis !== null &&
    analysis.frameSequence === visibleSequence &&
    source.width !== null &&
    source.height !== null;
  const switchableLoadDetected =
    analysis?.detections.some((detection) =>
      isSwitchableLoadVisionLabel(detection.label),
    ) === true;
  const droneDetected =
    analysis?.detections.some(
      (detection) => detection.label.trim().toLowerCase() === "drone",
    ) === true;
  return (
    <article className="fabric-media-card">
      <header>
        <div>
          <strong>{source.displayName}</strong>
          <small>
            {mediaKindName(source.kind)} ·{" "}
            {mediaCaptureModeName(source.captureMode)}
          </small>
        </div>
        <span className={`fabric-media-state is-${source.state}`}>
          {source.state === "online" ? "Live" : "Waiting"}
        </span>
      </header>
      <div className="fabric-media-frame">
        {frameUrl === null ? (
          <div className="fabric-media-placeholder">
            <span aria-hidden="true">CAM</span>
            <strong>{frameMessage}</strong>
          </div>
        ) : (
          <img src={frameUrl} alt={`Latest view from ${source.displayName}`} />
        )}
        {overlayVisible &&
          analysis !== null &&
          analysis.detections.map((detection, index) => (
            <span
              className="fabric-detection-box"
              key={`${detection.label}:${index}`}
              style={{
                left: `${(detection.box.x1 / (source.width ?? 1)) * 100}%`,
                top: `${(detection.box.y1 / (source.height ?? 1)) * 100}%`,
                width: `${((detection.box.x2 - detection.box.x1) / (source.width ?? 1)) * 100}%`,
                height: `${((detection.box.y2 - detection.box.y1) / (source.height ?? 1)) * 100}%`,
              }}
            >
              {detection.label} {Math.round(detection.confidence * 100)}%
            </span>
          ))}
      </div>
      <div className="fabric-media-meta">
        <span>
          {source.width === null
            ? "No image dimensions yet"
            : `${source.width} × ${source.height}`}
        </span>
        <span>
          {source.lastFrameAt === null
            ? "No frame received"
            : `Updated ${formatTime(source.lastFrameAt)}`}
        </span>
      </div>
      <button
        className="fabric-analyze-button"
        type="button"
        disabled={!canAnalyze || busy || source.frameSequence === 0}
        onClick={onAnalyze}
      >
        Recognize lamps, drones, and robots
      </button>
      {analysis !== null && (
        <div className="fabric-detection-results" aria-live="polite">
          <strong>
            {analysis.detections.length === 0
              ? "No configured object found"
              : "Objects found"}
          </strong>
          {analysis.detections.length > 0 && (
            <ul>
              {analysis.detections.map((detection, index) => (
                <li key={`${detection.label}:${index}`}>
                  {detection.label}
                  <span>{Math.round(detection.confidence * 100)}%</span>
                </li>
              ))}
            </ul>
          )}
          {switchableLoadDetected ? (
            <div className="fabric-detection-actions">
              <small>
                {smartPlugName === undefined
                  ? "Assign a classroom plug session to control an approved lamp."
                  : `Explicit tutor control for ${smartPlugName}`}
              </small>
              <div>
                <button
                  type="button"
                  disabled={!canTurnPlugOn}
                  onClick={() => onPower(true)}
                >
                  Turn linked plug on
                </button>
                <button
                  type="button"
                  disabled={!canTurnPlugOff}
                  onClick={() => onPower(false)}
                >
                  Turn linked plug off
                </button>
              </div>
            </div>
          ) : analysis.detections.length > 0 ? (
            <div className="fabric-detection-actions">
              <small>
                {droneDetected
                  ? "Drone recognition is advisory. Use an assigned, armed flight lesson for bounded drone controls; vision cannot arm or fly it."
                  : "No device action is mapped to this visual class. Use an assigned lesson control if one is available."}
              </small>
            </div>
          ) : null}
        </div>
      )}
    </article>
  );
}

function FabricNodeCard({ node }: { node: IntegrationNode }) {
  const battery = metadataNumber(node, "batteryPercent");
  const agentType = metadataText(node, "agentType");
  return (
    <div className="fabric-node-card">
      <span
        className={`fabric-node-icon ${node.simulated ? "is-simulated" : "is-physical"}`}
        aria-hidden="true"
      >
        {node.simulated ? "S" : "P"}
      </span>
      <div>
        <strong>{node.displayName}</strong>
        <small>
          {node.simulated ? "Simulator" : "Real device"}
          {agentType === undefined ? "" : ` · ${agentType}`}
        </small>
        <details className="fabric-node-technical">
          <summary>Technical details</summary>
          <small>
            {node.pluginId} · {node.nodeId} · host {node.hostId}
          </small>
          <CapabilityList
            label="Sends"
            capabilities={node.publishedCapabilities.map(
              (capability) => capability.name,
            )}
          />
          <CapabilityList
            label="Receives"
            capabilities={node.consumedCapabilities.map(
              (capability) => capability.name,
            )}
          />
        </details>
      </div>
      <div className="fabric-node-state">
        <span>{plainConnectionState(node)}</span>
        <small>
          {plainHealthState(node.healthState)}
          {battery === undefined ? "" : ` · ${battery}%`}
        </small>
      </div>
    </div>
  );
}

function FabricNodeGroup({
  kind,
  title,
  description,
  nodes,
}: {
  kind: FabricNodeIoKind;
  title: string;
  description: string;
  nodes: IntegrationNode[];
}) {
  return (
    <article className={`fabric-io-group is-${kind}`}>
      <header>
        <div>
          <h3>{title}</h3>
          <small>{description}</small>
        </div>
        <strong aria-label={`${nodes.length} ${title.toLowerCase()}`}>
          {nodes.length}
        </strong>
      </header>
      <div className="fabric-node-list">
        {nodes.length === 0 ? (
          <p className="fabric-empty">No devices in this group yet.</p>
        ) : (
          nodes.map((node) => <FabricNodeCard key={node.nodeId} node={node} />)
        )}
      </div>
    </article>
  );
}

function CapabilityList({
  label,
  capabilities,
}: {
  label: string;
  capabilities: string[];
}) {
  return (
    <div className="fabric-capability-row">
      <span>{label}</span>
      <div>
        {capabilities.length === 0 ? (
          <em>None</em>
        ) : (
          capabilities.map((capability) => (
            <code key={capability}>{capability}</code>
          ))
        )}
      </div>
    </div>
  );
}

const groupNodesByIo = (nodes: IntegrationNode[]) => {
  const groups: Record<FabricNodeIoKind, IntegrationNode[]> = {
    input: [],
    output: [],
    bidirectional: [],
  };
  nodes.forEach((node) => groups[classifyFabricNodeIo(node)].push(node));
  return groups;
};

const DISCOVERY_ICONS: Record<string, string> = {
  "even-meta-glasses": "XR",
  "coding-agents": "AI",
  "leap-motion": "LM",
  "robomaster-s1": "S1",
  "tello-drones": "TL",
  "mindwave-mobile2": "MW",
  "tuya-gosund-plugs": "PL",
  "lego-hubs": "LE",
};

const discoveryStatus = (status: FabricIntegrationDiscovery["status"]) => {
  switch (status) {
    case "connected":
      return { label: "Connected", tone: "connected" };
    case "found":
      return { label: "Found", tone: "found" };
    case "ready":
      return { label: "Computer ready", tone: "ready" };
    case "setup_required":
      return { label: "Setup needed", tone: "setup" };
    case "not_found":
      return { label: "Not found", tone: "missing" };
    case "unavailable":
      return { label: "Unavailable", tone: "missing" };
    case "not_scanned":
      return { label: "Not checked", tone: "unchecked" };
  }
};

const courseKey = (coursePackId: string, version: string) =>
  `${coursePackId}@${version}`;

const replaceSession = (
  sessions: InteractionSession[],
  replacement: InteractionSession,
) =>
  sessions.map((session) =>
    session.sessionId === replacement.sessionId ? replacement : session,
  );

const compatibleNodes = (
  nodes: IntegrationNode[],
  session: InteractionSession,
  requirement: CoursePack["roles"][number],
) => {
  const capabilities = new Set(requirement.oneOfCapabilities);
  return nodes.filter(
    (node) =>
      node.siteId === session.siteId &&
      node.roomId === session.roomId &&
      ["connected", "degraded"].includes(node.connectionState) &&
      [...node.publishedCapabilities, ...node.consumedCapabilities].some(
        (capability) =>
          capabilities.has(capability.name) &&
          (session.mode !== "simulation" ||
            node.simulated ||
            ["none", "informational"].includes(
              capability.safetyClassification,
            )),
      ),
  );
};

const hasPermission = (principal: FabricPrincipal | null, permission: string) =>
  principal?.permissions.includes(permission) === true;

const metadataNumber = (
  node: IntegrationNode,
  key: string,
): number | undefined => {
  const value = node.metadata[key];
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
};

const metadataText = (
  node: IntegrationNode,
  key: string,
): string | undefined => {
  const value = node.metadata[key];
  return typeof value === "string" ? value : undefined;
};

const mediaKindName = (kind: FabricMediaSource["kind"]) => {
  const names: Record<FabricMediaSource["kind"], string> = {
    meta_glasses: "Meta glasses",
    robomaster: "RoboMaster",
    tello: "Tello drone",
    usb_camera: "USB camera",
    simulator: "Simulated camera",
  };
  return names[kind];
};

const mediaCaptureModeName = (mode: FabricMediaSource["captureMode"]) =>
  mode === "video" ? "Live frames" : "Snapshot fallback";

const plainCapabilityName = (capability: string) =>
  capability
    .split(".")
    .slice(1)
    .join(" ")
    .replaceAll("_", " ")
    .replace(/^./, (first) => first.toUpperCase());

const nodeDisplayName = (nodes: IntegrationNode[], nodeId: string) =>
  nodes.find((node) => node.nodeId === nodeId)?.displayName ?? nodeId;

const COURSE_SUMMARIES: Record<string, string> = {
  "glasses-agent-control": "Glasses + coding assistant",
  "gesture-ground-robot": "Gesture + classroom robot",
  "smart-plug-control": "Tutor-controlled classroom plug",
};

const COURSE_NAMES: Record<string, string> = {
  "glasses-agent-control": "Glasses and coding assistant",
  "gesture-ground-robot": "Gesture-controlled robot",
  "smart-plug-control": "Classroom smart plug",
};

const COURSE_DESCRIPTIONS: Record<string, string> = {
  "glasses-agent-control":
    "Students send a request from their glasses to a coding assistant and receive the response on a classroom display.",
  "gesture-ground-robot":
    "Students steer a classroom robot with hand gestures while CIT keeps movement within the lesson’s safety limits.",
  "smart-plug-control":
    "The tutor turns one approved classroom lamp or other low-risk load on and off from this screen.",
};

const ROLE_NAMES: Record<string, string> = {
  classroom_plug: "Classroom plug",
  coding_agent: "Coding assistant",
  feedback_display: "Feedback display",
  gesture_input: "Gesture controller",
  instructor_console: "Tutor display",
  primary_glasses: "Student glasses",
  student_robot: "Classroom robot",
};

const ROLE_DESCRIPTIONS: Record<string, string> = {
  classroom_plug: "Turns one approved classroom load on or off",
  coding_agent: "Receives student prompts and returns coding progress",
  feedback_display: "Shows coding progress and lesson messages",
  gesture_input: "Sends hand movements to the lesson",
  instructor_console: "Shows lesson activity to the tutor",
  primary_glasses: "Sends student input and displays lesson feedback",
  student_robot: "Receives bounded movement and stop instructions",
};

const plainCourseSummary = (coursePack: CoursePack) =>
  COURSE_SUMMARIES[coursePack.coursePackId] ??
  `${coursePack.roles.length} classroom device ${coursePack.roles.length === 1 ? "role" : "roles"}`;

const plainCourseName = (coursePack: CoursePack) =>
  COURSE_NAMES[coursePack.coursePackId] ?? coursePack.displayName;

const plainCourseDescription = (coursePack: CoursePack) =>
  COURSE_DESCRIPTIONS[coursePack.coursePackId] ?? coursePack.description;

const plainRoleName = (role: string) =>
  ROLE_NAMES[role] ?? capitalize(role.replaceAll("_", " "));

const roleDescription = (role: string) =>
  ROLE_DESCRIPTIONS[role] ?? "Fills this part of the classroom lesson";

const courseName = (coursePacks: CoursePack[], session: InteractionSession) => {
  const coursePack = coursePacks.find(
    (coursePack) =>
      coursePack.coursePackId === session.coursePackId &&
      coursePack.version === session.coursePackVersion,
  );
  return coursePack === undefined
    ? session.coursePackId.replaceAll("-", " ")
    : plainCourseName(coursePack);
};

const plainSessionState = (session: InteractionSession | undefined) => {
  if (session === undefined) return "Not started";
  const states: Record<string, string> = {
    draft: "Needs devices",
    ready: "Ready to start",
    active: "Running",
    paused: "Paused",
    stopped: "Ended",
    emergency_stopped: "Emergency stopped",
    failed: "Needs attention",
  };
  return states[session.state] ?? session.state.replaceAll("_", " ");
};

const plainConnectionState = (node: IntegrationNode) => {
  const states: Record<string, string> = {
    connected: "Connected",
    degraded: "Connected · needs attention",
    unavailable: "Unavailable",
    disconnected: "Disconnected",
    connecting: "Connecting",
  };
  return (
    states[node.connectionState] ?? node.connectionState.replaceAll("_", " ")
  );
};

const plainHealthState = (state: string) => {
  const states: Record<string, string> = {
    healthy: "Healthy",
    degraded: "Needs attention",
    unhealthy: "Not working",
    unknown: "Health unknown",
  };
  return states[state] ?? capitalize(state.replaceAll("_", " "));
};

const commandResultNotice = (label: string, stage: string | undefined) => {
  if (stage === "SUCCEEDED") return `${label} worked.`;
  if (stage === "FAILED" || stage === "REJECTED") {
    return `${label} was not completed. Open Technical diagnostics for details.`;
  }
  if (stage === "CANCELLED" || stage === "TIMED_OUT") {
    return `${label} stopped before it finished. Try again or check the device.`;
  }
  return `${label} was sent to the device.`;
};

const describeFabricError = (caught: unknown) => {
  if (caught instanceof FabricApiError) {
    const messages: Record<string, string> = {
      AUTHENTICATION_REQUIRED:
        "That access code is invalid or expired. Reopen Classroom Control from the CIT launcher.",
      PHYSICAL_EXECUTION_DISABLED:
        "Real-device control is locked by the local runtime. Restart CIT with physical devices enabled, or use a simulator.",
      SESSION_NOT_ACTIVE: "Start the lesson before using that device.",
      NODE_UNAVAILABLE:
        "That device is no longer connected. Check its power and adapter, then refresh.",
      REQUIRED_ROLES_UNASSIGNED:
        "Connect every required device before starting the lesson.",
    };
    return messages[caught.code] ?? caught.message;
  }
  return caught instanceof Error
    ? caught.message
    : "The Fabric request failed.";
};

const shortId = (value: string) =>
  value.length > 20 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
const capitalize = (value: string) =>
  value.charAt(0).toUpperCase() + value.slice(1);
const formatTime = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));

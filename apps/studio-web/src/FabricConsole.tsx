import type {
  CoursePack,
  FabricCommandPriority,
  IntegrationNode,
  InteractionSession,
} from "@citxr/protocol";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";

import {
  FabricApiError,
  FabricClient,
  type FabricAuditRecord,
  type FabricPrincipal,
  type StoredFabricEvent,
  type StoredFabricLifecycle,
} from "./fabric-client.js";

type BusyAction = string | null;

const TERMINAL_COMMAND_STAGES = new Set([
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "TIMED_OUT",
  "REJECTED",
]);

export function FabricConsole() {
  const client = useMemo(() => new FabricClient(), []);
  const [credential, setCredential] = useState("");
  const [principal, setPrincipal] = useState<FabricPrincipal | null>(null);
  const [nodes, setNodes] = useState<IntegrationNode[]>([]);
  const [coursePacks, setCoursePacks] = useState<CoursePack[]>([]);
  const [sessions, setSessions] = useState<InteractionSession[]>([]);
  const [events, setEvents] = useState<StoredFabricEvent[]>([]);
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
  const [busy, setBusy] = useState<BusyAction>(null);
  const [notice, setNotice] = useState(
    "Authenticate with an independently issued CIT Fabric credential.",
  );
  const [error, setError] = useState<string | null>(null);
  const pollActive = useRef(false);

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
  const canStopAll = hasPermission(principal, "fabric.stop_all");

  const refresh = useCallback(
    async (showError = false) => {
      if (principal === null || pollActive.current) return;
      pollActive.current = true;
      try {
        const [nextNodes, nextCourses, nextSessions] = await Promise.all([
          client.listNodes(),
          client.listCoursePacks(),
          client.listSessions(),
        ]);
        setNodes(nextNodes);
        setCoursePacks(nextCourses);
        setSessions(nextSessions);
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
    [client, principal, selectedSessionId],
  );

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
    setRoleSelections(
      Object.fromEntries(
        selectedSession.roleBindings.map((binding) => [
          binding.role,
          binding.nodeId,
        ]),
      ),
    );
  }, [selectedSession]);

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
        setNotice(
          `Connected as ${identity.identityId}. The credential remains in memory only.`,
        );
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
    setCoursePacks([]);
    setSessions([]);
    setEvents([]);
    setLifecycle([]);
    setAudit([]);
    setNotice("The in-memory credential was cleared.");
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
      setSelectedSessionId(created.sessionId);
      setNotice(`Created ${created.sessionId} in ${created.mode} mode.`);
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
      setNotice(`${nodeId} now fills ${role}.`);
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
      setNotice(`Session is now ${updated.state.replaceAll("_", " ")}.`);
    });

  const stopAll = () =>
    runAction("Emergency stopping", async () => {
      const result = await client.stopAll();
      setNotice(
        `Emergency stop ${result.status}: ${result.stoppedSessionIds.length} session(s), ` +
          `${result.stoppedNodeIds.length} adapter node(s).`,
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
      setNotice(
        `Input path is live: ${latest.event.topic} from ${latest.event.sourceNodeId}.`,
      );
    });

  const sendTestCommand = (kind: "agent" | "display") =>
    runAction(`Testing ${kind}`, async () => {
      if (selectedSession === undefined)
        throw new Error("Select a session first.");
      if (selectedSession.state !== "active") {
        throw new Error("Start the session before testing an output.");
      }
      const role = kind === "agent" ? "coding_agent" : "primary_glasses";
      const action =
        kind === "agent" ? "agent.prompt.submit" : "display.text.render";
      const parameters =
        kind === "agent"
          ? {
              prompt:
                "Reply with a short CIT Fabric connectivity acknowledgement.",
            }
          : { text: "CIT Fabric display test" };
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
      setNotice(
        `${kind === "agent" ? "Agent" : "Display"} test reached ` +
          `${terminal?.stage ?? "an unknown state"}.`,
      );
    });

  if (principal === null) {
    return (
      <div className="fabric-console fabric-login-shell">
        <section
          className="fabric-login-card"
          aria-labelledby="fabric-login-heading"
        >
          <p className="eyebrow">Independent local authority</p>
          <h1 id="fabric-login-heading">Interaction Fabric</h1>
          <p>
            Use a scoped CIT credential issued by the local runtime. Agent,
            vendor, and course credentials are never accepted here.
          </p>
          <form onSubmit={signIn}>
            <label htmlFor="fabric-credential">Fabric bearer credential</label>
            <input
              id="fabric-credential"
              type="password"
              autoComplete="off"
              minLength={32}
              maxLength={512}
              required
              value={credential}
              onChange={(event) => setCredential(event.target.value)}
            />
            <button type="submit" disabled={busy !== null}>
              {busy ?? "Connect locally"}
            </button>
          </form>
          <small>
            Credentials are held in page memory and cleared on sign-out or
            reload.
          </small>
          {error !== null && <div className="fabric-error">{error}</div>}
          <div className="fabric-notice">{notice}</div>
        </section>
      </div>
    );
  }

  const activeCommands = lifecycle.filter(
    (item) => !TERMINAL_COMMAND_STAGES.has(item.lifecycle.stage),
  );
  const agentNodes = nodes.filter((node) =>
    [...node.publishedCapabilities, ...node.consumedCapabilities].some(
      (capability) => capability.name.startsWith("agent."),
    ),
  );

  return (
    <div className="fabric-console">
      <header className="fabric-header">
        <div>
          <p className="eyebrow">Local-first orchestration</p>
          <h1>Interaction Fabric</h1>
        </div>
        <div className="fabric-identity">
          <span className="status-dot status-ok" />
          <div>
            <strong>{principal.identityId}</strong>
            <small>{principal.roles.join(" · ")}</small>
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
          <span>■</span> Emergency stop
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

        <section className="fabric-overview" aria-label="Fabric status">
          <FabricMetric label="Nodes" value={String(nodes.length)} />
          <FabricMetric
            label="Connected"
            value={String(
              nodes.filter((node) => node.connectionState === "connected")
                .length,
            )}
          />
          <FabricMetric
            label="Active sessions"
            value={String(
              sessions.filter((session) => session.state === "active").length,
            )}
          />
          <FabricMetric
            label="Active commands"
            value={String(activeCommands.length)}
          />
          <FabricMetric
            label="Safety"
            value={
              selectedSession?.mode === "physical"
                ? selectedSession.armed
                  ? "Armed"
                  : "Disarmed"
                : "Physical actuation off"
            }
            warning={selectedSession?.armed === true}
          />
        </section>

        <section className="fabric-grid">
          <article className="fabric-panel fabric-session-builder">
            <PanelHeading eyebrow="Course and room" title="Create a session" />
            <label>
              Course pack
              <select
                value={selectedCourseKey}
                onChange={(event) => setSelectedCourseKey(event.target.value)}
              >
                {coursePacks.map((coursePack) => (
                  <option
                    key={courseKey(coursePack.coursePackId, coursePack.version)}
                    value={courseKey(
                      coursePack.coursePackId,
                      coursePack.version,
                    )}
                  >
                    {coursePack.displayName} · {coursePack.version}
                  </option>
                ))}
              </select>
            </label>
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
              Device mode
              <select
                value={sessionMode}
                onChange={(event) =>
                  setSessionMode(
                    event.target.value as "simulation" | "physical",
                  )
                }
              >
                <option value="simulation">Safe / simulated outputs</option>
                <option value="physical">
                  Physical devices (policy disabled)
                </option>
              </select>
            </label>
            <button
              className="fabric-primary-action"
              type="button"
              disabled={
                !canManageSessions || busy !== null || !selectedCourseKey
              }
              onClick={() => void createSession()}
            >
              Create isolated session
            </button>
            <p className="fabric-help">{selectedCourse?.fallbackBehavior}</p>
          </article>

          <article className="fabric-panel fabric-session-control">
            <PanelHeading eyebrow="Role assignment" title="Control a session" />
            <label>
              Session
              <select
                value={selectedSessionId}
                onChange={(event) => setSelectedSessionId(event.target.value)}
              >
                <option value="">Select a session</option>
                {sessions.map((session) => (
                  <option key={session.sessionId} value={session.sessionId}>
                    {shortId(session.sessionId)} · {session.state}
                  </option>
                ))}
              </select>
            </label>
            {selectedSession !== undefined && selectedCourse !== undefined ? (
              <div className="fabric-role-list">
                {selectedCourse.roles.map((requirement) => {
                  const candidates = compatibleNodes(
                    nodes,
                    selectedSession,
                    requirement,
                  );
                  return (
                    <div className="fabric-role" key={requirement.role}>
                      <div>
                        <strong>{requirement.role.replaceAll("_", " ")}</strong>
                        <small>
                          {requirement.optional ? "optional" : "required"} ·{" "}
                          {requirement.oneOfCapabilities.join(" or ")}
                        </small>
                      </div>
                      <select
                        aria-label={`Node for ${requirement.role}`}
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
                        <option value="">Unassigned</option>
                        {candidates.map((node) => (
                          <option key={node.nodeId} value={node.nodeId}>
                            {node.displayName} · {node.connectionState}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={
                          !canAssignRoles ||
                          busy !== null ||
                          selectedSession.state === "active" ||
                          !roleSelections[requirement.role]
                        }
                        onClick={() => void assignRole(requirement.role)}
                      >
                        Assign
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="fabric-empty">
                Select a session to assign logical roles.
              </p>
            )}
            <div className="fabric-session-actions">
              <button
                type="button"
                disabled={
                  !canManageSessions ||
                  busy !== null ||
                  selectedSession?.mode !== "physical" ||
                  selectedSession.armed === true ||
                  !["ready", "paused"].includes(selectedSession?.state ?? "")
                }
                onClick={() => void changeSessionState("arm")}
              >
                Arm
              </button>
              <button
                type="button"
                disabled={
                  !canManageSessions ||
                  busy !== null ||
                  selectedSession?.armed !== true
                }
                onClick={() => void changeSessionState("disarm")}
              >
                Disarm
              </button>
              <button
                type="button"
                disabled={
                  !canManageSessions ||
                  busy !== null ||
                  !["ready", "paused"].includes(selectedSession?.state ?? "")
                }
                onClick={() => void changeSessionState("start")}
              >
                Start
              </button>
              <button
                type="button"
                disabled={
                  !canManageSessions ||
                  busy !== null ||
                  selectedSession?.state !== "active"
                }
                onClick={() => void changeSessionState("pause")}
              >
                Pause
              </button>
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
                Stop and disarm
              </button>
            </div>
          </article>
        </section>

        <section className="fabric-panel fabric-test-panel">
          <PanelHeading
            eyebrow="Guided checks"
            title="Test the selected experience"
          />
          <div className="fabric-test-actions">
            <button
              type="button"
              disabled={selectedSession === undefined || busy !== null}
              onClick={() => void checkInput()}
            >
              Test assigned input
              <small>Verify the latest semantic signal</small>
            </button>
            <button
              type="button"
              disabled={
                !canSubmitCommands ||
                selectedSession?.state !== "active" ||
                busy !== null
              }
              onClick={() => void sendTestCommand("agent")}
            >
              Test coding agent
              <small>Submit one bounded prompt</small>
            </button>
            <button
              type="button"
              disabled={
                !canSubmitCommands ||
                selectedSession?.state !== "active" ||
                busy !== null
              }
              onClick={() => void sendTestCommand("display")}
            >
              Test glasses display
              <small>Render one fixed notification</small>
            </button>
            <div className="fabric-arm-state">
              <span
                className={`status-dot ${selectedSession?.armed ? "status-warning" : "status-ok"}`}
              />
              <div>
                <strong>
                  {selectedSession?.armed
                    ? "Physical outputs armed"
                    : "Physical outputs disarmed"}
                </strong>
                <small>
                  {selectedSession?.disarmReason?.replaceAll("_", " ") ??
                    "Reference runtime has no physical execution path"}
                </small>
              </div>
            </div>
          </div>
        </section>

        <section className="fabric-grid fabric-node-observability">
          <article className="fabric-panel fabric-node-panel">
            <PanelHeading
              eyebrow="Capability registry"
              title="Connected nodes"
            />
            <div className="fabric-node-list">
              {nodes.length === 0 ? (
                <p className="fabric-empty">
                  No nodes are registered in this scope.
                </p>
              ) : (
                nodes.map((node) => (
                  <FabricNodeCard key={node.nodeId} node={node} />
                ))
              )}
            </div>
          </article>
          <article className="fabric-panel">
            <PanelHeading eyebrow="Agent gateway" title="Coding-agent status" />
            {agentNodes.length === 0 ? (
              <p className="fabric-empty">
                Connect the Agent Mesh bridge to advertise sessions.
              </p>
            ) : (
              <div className="fabric-agent-list">
                {agentNodes.map((node) => (
                  <div key={node.nodeId}>
                    <span
                      className={`status-dot ${node.connectionState === "connected" ? "status-ok" : "status-warning"}`}
                    />
                    <div>
                      <strong>{node.displayName}</strong>
                      <small>
                        {node.nodeId} · {node.connectionState}
                      </small>
                    </div>
                    <span>{metadataText(node, "agentType") ?? "agent"}</span>
                  </div>
                ))}
              </div>
            )}
          </article>
        </section>

        <section className="fabric-grid fabric-stream-grid">
          <article className="fabric-panel">
            <PanelHeading eyebrow="Semantic stream" title="Recent signals" />
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
              eyebrow="Traceable execution"
              title="Command lifecycle"
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

        {audit.length > 0 && (
          <section className="fabric-panel fabric-audit-panel">
            <PanelHeading
              eyebrow="Independent audit"
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

function FabricNodeCard({ node }: { node: IntegrationNode }) {
  const battery = metadataNumber(node, "batteryPercent");
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
          {node.nodeId} · {node.hostId}
        </small>
        <p>
          {[...node.publishedCapabilities, ...node.consumedCapabilities]
            .slice(0, 3)
            .map((capability) => capability.name)
            .join(" · ")}
        </p>
      </div>
      <div className="fabric-node-state">
        <span>{node.connectionState}</span>
        <small>
          {node.healthState}
          {battery === undefined ? "" : ` · ${battery}%`}
        </small>
      </div>
    </div>
  );
}

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

const describeFabricError = (caught: unknown) => {
  if (caught instanceof FabricApiError) {
    return `${caught.code}: ${caught.message}`;
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

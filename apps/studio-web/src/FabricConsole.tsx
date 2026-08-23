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
  type LegoConnectionConfiguration,
  type FabricPrincipal,
  type FabricSessionStartPolicy,
  type StoredFabricEvent,
  type StoredFabricLifecycle,
} from "./fabric-client.js";
import { discoveryLinkLabel } from "./fabric-discovery.js";
import { consumeConsoleTicket } from "./fabric-console-access.js";
import {
  BRAIN_DEMO_ARM_CAPABILITY,
  BRAIN_DEMO_STOP_CAPABILITY,
  isBrainDemoControllerNode,
  latestBrainDemoStatus,
  type BrainDemoSettings,
} from "./fabric-brain-demo.js";
import {
  FLIGHT_EMERGENCY_STOP_CAPABILITY,
  FLIGHT_LAND_CAPABILITY,
  isSafeStateTelloNode,
  isSafetyDroneRole,
} from "./fabric-drone.js";
import {
  FLEET_SEQUENCE_ARM_CAPABILITY,
  FLEET_SEQUENCE_START_CAPABILITY,
  FLEET_SEQUENCE_STOP_CAPABILITY,
  isFleetSequenceControllerNode,
  isFleetSequenceInputNode,
  latestFleetSequenceStatus,
  type FleetSequenceSettings,
} from "./fabric-fleet-sequence.js";
import {
  classifyFabricNodeIo,
  groupFabricCourseRolesByIo,
  groupFabricIntegrationsByIo,
  isAvailableFabricNode,
  type FabricNodeIoKind,
} from "./fabric-node-io.js";
import { countActiveFabricCommands } from "./fabric-lifecycle.js";
import { parallelFlowGroups } from "./fabric-parallel-flow.js";
import { refreshedSessionSelection } from "./fabric-session-selection.js";
import {
  isSmartPlugNode,
  isSwitchableLoadVisionLabel,
  latestSmartPlugState,
  POWER_SET_CAPABILITY,
} from "./fabric-smart-plug.js";
import { latestSensorReadings } from "./fabric-sensors.js";
import { tutorGuide } from "./fabric-tutor-guide.js";
import {
  fabricCapabilityName,
  fabricConnectionState,
  fabricCourseName,
  fabricCourseText,
  fabricFormatTime,
  fabricHealthState,
  fabricMediaKind,
  fabricPhase,
  fabricRoleText,
  fabricSessionState,
  fabricTranslatorFor,
  localizeFabricIntegration,
  type FabricMessageKey,
  type FabricTranslate,
} from "./fabric-i18n.js";
import { LOCALES, readSavedLocale, saveLocale, type Locale } from "./i18n.js";
import { FabricBrainDemoPanel } from "./FabricBrainDemoPanel.js";
import { FabricDronePanel } from "./FabricDronePanel.js";
import { FabricFleetSequencePanel } from "./FabricFleetSequencePanel.js";
import { FabricLegoSetup } from "./FabricLegoSetup.js";
import { FabricMatterSetup } from "./FabricMatterSetup.js";

type BusyAction = {
  key: FabricMessageKey;
  values?: Record<string, string | number>;
} | null;

export function FabricConsole() {
  const [locale, setLocaleState] = useState<Locale>(readSavedLocale);
  const t = useMemo(() => fabricTranslatorFor(locale), [locale]);
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
  const [sessionStartPolicy, setSessionStartPolicy] =
    useState<FabricSessionStartPolicy | null>(null);
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
  const [notice, setNotice] = useState(() => t("notice.ready"));
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
  const simultaneousFlowGroups = useMemo(
    () => parallelFlowGroups(selectedCourse),
    [selectedCourse],
  );
  const requiresArmingForStart =
    selectedSession?.mode === "physical" &&
    (selectedSession.roleBindings.some(
      (binding) =>
        binding.role === "brain_flight_demo" ||
        binding.role === "fleet_sequence_controller",
    ) ||
      sessionStartPolicy?.sessionId !== selectedSession.sessionId ||
      sessionStartPolicy.requiresArming);
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
  const assignedDrones = useMemo(
    () =>
      (selectedSession?.roleBindings ?? [])
        .filter((binding) => isSafetyDroneRole(binding.role))
        .map((binding) => ({
          role: binding.role,
          node: availableNodes.find(
            (node) =>
              node.nodeId === binding.nodeId && isSafeStateTelloNode(node),
          ),
        }))
        .filter(
          (item): item is { role: string; node: IntegrationNode } =>
            item.node !== undefined,
        ),
    [availableNodes, selectedSession?.roleBindings],
  );
  const brainDemoBinding = selectedSession?.roleBindings.find(
    (binding) => binding.role === "brain_flight_demo",
  );
  const brainDemoController = availableNodes.find(
    (node) =>
      node.nodeId === brainDemoBinding?.nodeId &&
      isBrainDemoControllerNode(node),
  );
  const brainDemoStatus = useMemo(
    () => latestBrainDemoStatus(events, brainDemoController?.nodeId),
    [brainDemoController?.nodeId, events],
  );
  const fleetSequenceBinding = selectedSession?.roleBindings.find(
    (binding) => binding.role === "fleet_sequence_controller",
  );
  const fleetSequenceController = availableNodes.find(
    (node) =>
      node.nodeId === fleetSequenceBinding?.nodeId &&
      isFleetSequenceControllerNode(node),
  );
  const fleetSequenceInputNodes = useMemo(
    () =>
      (selectedSession?.roleBindings ?? [])
        .filter((binding) => isFleetSequenceInputRole(binding.role))
        .flatMap((binding) => {
          const node = availableNodes.find(
            (candidate) =>
              candidate.nodeId === binding.nodeId &&
              isFleetSequenceInputNode(candidate),
          );
          return node === undefined ? [] : [node];
        }),
    [availableNodes, selectedSession?.roleBindings],
  );
  const fleetSequenceStatus = useMemo(
    () => latestFleetSequenceStatus(events, fleetSequenceController?.nodeId),
    [events, fleetSequenceController?.nodeId],
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
    () => tutorGuide(selectedSession, requiredRoles, discoveryScanned, t),
    [discoveryScanned, requiredRoles, selectedSession, t],
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
        const detailSessionId = refreshedSessionSelection(
          selectedSessionId,
          nextSessions,
        );
        setSelectedSessionId((current) =>
          refreshedSessionSelection(current, nextSessions),
        );

        if (detailSessionId) {
          try {
            const [nextEvents, nextStartPolicy] = await Promise.all([
              client.listEvents(detailSessionId),
              client.getSessionStartPolicy(detailSessionId),
            ]);
            setEvents(nextEvents);
            setSessionStartPolicy(nextStartPolicy);
          } catch (caught) {
            if (!(caught instanceof FabricApiError && caught.status === 403))
              throw caught;
          }
        } else {
          setEvents([]);
          setSessionStartPolicy(null);
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
        if (showError) setError(describeFabricError(caught, t));
      } finally {
        pollActive.current = false;
      }
    },
    [canReadMedia, client, principal, selectedSessionId, t],
  );

  const setLocale = useCallback((nextLocale: Locale) => {
    saveLocale(nextLocale);
    setLocaleState(nextLocale);
    setError(null);
    setNotice(fabricTranslatorFor(nextLocale)("notice.ready"));
  }, []);

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
        setNotice(t("notice.secureOpen"));
      })
      .catch((caught: unknown) => {
        setError(describeFabricError(caught, t));
        setShowAccessCode(true);
      })
      .finally(() => setAutoConnecting(false));
  }, [client, t]);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = t("document.title");
    return () => {
      document.title = previousTitle;
    };
  }, [t]);

  useEffect(() => saveLocale(locale), [locale]);

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
        if (requirement.optional) return;
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

  const runAction = async (
    key: FabricMessageKey,
    action: () => Promise<void>,
    values?: Record<string, string | number>,
  ): Promise<boolean> => {
    if (busy !== null) return false;
    setBusy({ key, ...(values === undefined ? {} : { values }) });
    setError(null);
    try {
      await action();
      await refresh(false);
      return true;
    } catch (caught) {
      setError(describeFabricError(caught, t));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const signIn = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runAction("busy.authenticating", async () => {
      client.setCredential(credential);
      try {
        const identity = await client.whoAmI();
        setPrincipal(identity);
        setCredential("");
        setNotice(t("notice.connected"));
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
    setSessionStartPolicy(null);
    setEvents([]);
    setMediaSources([]);
    setMediaPairing(null);
    setLifecycle([]);
    setAudit([]);
    setGroundedConfirmations({});
    setNotice(t("notice.signedOut"));
  };

  const createSession = () =>
    runAction("busy.creatingSession", async () => {
      const coursePack = coursePacks.find(
        (candidate) =>
          courseKey(candidate.coursePackId, candidate.version) ===
          selectedCourseKey,
      );
      if (coursePack === undefined) throw new Error(t("error.selectCourse"));
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
          ? t("notice.lessonCreatedAuto", { count: automaticAssignments })
          : t("notice.lessonCreated"),
      );
    });

  const assignRole = (role: string) =>
    runAction("busy.assigningRole", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.selectSession"));
      const nodeId = roleSelections[role];
      if (!nodeId)
        throw new Error(
          t("error.selectNode", { role: fabricRoleText(role, t).name }),
        );
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
        t("notice.roleReady", {
          device: nodeName ?? t("role.chooseDevice"),
          role: fabricRoleText(role, t).name,
        }),
      );
    });

  const changeSessionState = (
    action: "arm" | "disarm" | "start" | "pause" | "stop",
  ) =>
    runAction("busy.changingSession", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.selectSession"));
      const updated = await client.sessionAction(
        selectedSession.sessionId,
        action,
      );
      setSessions((current) => replaceSession(current, updated));
      setNotice(
        t("notice.lessonStatus", {
          status: fabricSessionState(updated, t),
        }),
      );
    });

  const enablePhysicalControls = () =>
    runAction("busy.enablingPhysical", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.selectPhysicalSession"));
      const resume = selectedSession.state === "active";
      let updated = selectedSession;
      if (resume) {
        updated = await client.sessionAction(updated.sessionId, "pause");
      }
      updated = await client.sessionAction(updated.sessionId, "arm");
      if (resume) {
        updated = await client.sessionAction(updated.sessionId, "start");
      }
      setSessions((current) => replaceSession(current, updated));
      setNotice(
        resume ? t("notice.physicalResumed") : t("notice.physicalReady"),
      );
    });

  const stopAll = () =>
    runAction("busy.emergencyStop", async () => {
      const result = await client.stopAll();
      setNotice(
        t("notice.emergencyStop", {
          status: result.status,
          sessions: result.stoppedSessionIds.length,
          nodes: result.stoppedNodeIds.length,
        }),
      );
    });

  const findDevices = () =>
    runAction("busy.findingDevices", async () => {
      const report = await client.scanDevices();
      setDiscovery(report);
      const connected = report.integrations.filter(
        (integration) => integration.status === "connected",
      ).length;
      const found = report.integrations.filter((integration) =>
        ["found", "ready"].includes(integration.status),
      ).length;
      setNotice(t("notice.deviceCheck", { connected, found }));
    });

  const connectDiscovered = (integration: FabricIntegrationDiscovery) =>
    runAction(
      "busy.connectingDevice",
      async () => {
        if (integration.actionId === undefined) {
          throw new Error(t("error.setupFirst"));
        }
        const confirmed =
          groundedConfirmations[integration.integrationId] === true;
        if (integration.requiresGroundedConfirmation && !confirmed) {
          throw new Error(t("error.grounded"));
        }
        const result = await client.runDiscoveryAction(
          integration.actionId,
          confirmed,
        );
        setDiscovery(result.report);
        setNotice(
          t("notice.integrationConnected", {
            name: localizeFabricIntegration(locale, integration, t).displayName,
          }),
        );
      },
      { name: localizeFabricIntegration(locale, integration, t).displayName },
    );

  const commissionMatterPlug = (setupCode: string) =>
    runAction("busy.addingMatter", async () => {
      const result = await client.commissionMatterPlug(setupCode);
      setDiscovery(result.report);
      setNotice(t("notice.matterAdded"));
    });

  const connectLegoHub = (configuration: LegoConnectionConfiguration) =>
    runAction("busy.connectingLego", async () => {
      const result = await client.connectLegoHub(configuration);
      setDiscovery(result.report);
      setNotice(t("notice.legoConnected"));
    });

  const connectAllDiscovered = () =>
    runAction("busy.connectingAll", async () => {
      if (connectableIntegrations.length === 0) {
        throw new Error(t("error.noConnection"));
      }
      if (!allAircraftGrounded) {
        throw new Error(t("error.groundedAll"));
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
          connectedNames.push(
            localizeFabricIntegration(locale, integration, t).displayName,
          );
        } catch (caught) {
          failures.push(
            `${localizeFabricIntegration(locale, integration, t).displayName}: ${describeFabricError(caught, t)}`,
          );
        }
      }
      if (latestReport !== null) setDiscovery(latestReport);

      const connectionSummary =
        connectedNames.length === 0
          ? t("notice.noneConnected")
          : t("notice.groupsConnected", {
              count: connectedNames.length,
              names: connectedNames.join(", "),
            });
      setNotice(`${connectionSummary} ${t("notice.outputsLocked")}`);
      if (failures.length > 0) {
        setError(t("notice.someAttention", { details: failures.join(" ") }));
      }
    });

  const copySetupCommand = (integration: FabricIntegrationDiscovery) =>
    runAction("busy.copyingSetup", async () => {
      if (integration.setupCommand === undefined) {
        throw new Error(t("error.noSetupCommand"));
      }
      if (navigator.clipboard === undefined) {
        throw new Error(t("error.clipboard"));
      }
      await navigator.clipboard.writeText(integration.setupCommand);
      setNotice(
        t("notice.setupCopied", {
          name: localizeFabricIntegration(locale, integration, t).displayName,
        }),
      );
    });

  const startMetaCameraPairing = () =>
    runAction("busy.cameraPairing", async () => {
      const pairing = await client.createMediaPairing(
        siteId.trim(),
        roomId.trim(),
      );
      setMediaPairing(pairing);
      setNotice(t("notice.cameraPairing"));
    });

  const copyMediaPairingValue = (value: string, label: string) =>
    runAction(
      "busy.copying",
      async () => {
        if (navigator.clipboard === undefined) {
          throw new Error(t("error.clipboard"));
        }
        await navigator.clipboard.writeText(value);
        setNotice(t("notice.copied", { label }));
      },
      { label },
    );

  const checkInput = () =>
    runAction("busy.testingInput", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.selectSession"));
      const bindings = new Set(
        selectedSession.roleBindings.map((binding) => binding.nodeId),
      );
      const latest = (await client.listEvents(selectedSession.sessionId))
        .filter((item) => bindings.has(item.event.sourceNodeId))
        .at(-1);
      if (latest === undefined) {
        throw new Error(t("error.noInput"));
      }
      setEvents(await client.listEvents(selectedSession.sessionId));
      const sourceName =
        nodes.find((node) => node.nodeId === latest.event.sourceNodeId)
          ?.displayName ?? t("role.chooseDevice");
      setNotice(
        t("notice.inputReceived", {
          source: sourceName,
          time: fabricFormatTime(latest.event.timestamp, locale),
        }),
      );
    });

  const sendTestCommand = (kind: "agent" | "display" | "robot-stop") =>
    runAction("busy.testingOutput", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.selectSession"));
      if (kind !== "robot-stop" && selectedSession.state !== "active") {
        throw new Error(t("error.startOutput"));
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
              prompt: t("test.agentPrompt"),
            }
          : kind === "display"
            ? {
                text: t("test.displayMessage"),
              }
            : {};
      if (
        !selectedSession.roleBindings.some((binding) => binding.role === role)
      ) {
        throw new Error(
          t("error.assignRole", { role: fabricRoleText(role, t).name }),
        );
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
          ? t("test.agent")
          : kind === "display"
            ? t("test.glasses")
            : t("test.robotStop");
      setNotice(commandResultNotice(label, terminal?.stage, t));
    });

  const setSmartPlugPower = (on: boolean) =>
    runAction("busy.smartPlug", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.smartPlugSession"));
      if (smartPlugBinding === undefined)
        throw new Error(t("error.assignPlug"));
      if (on && selectedSession.state !== "active")
        throw new Error(t("error.startLoad"));
      if (on && selectedSession.mode === "physical" && !selectedSession.armed)
        throw new Error(t("error.armLoad"));
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
          on ? t("plug.turnOn") : t("plug.turnOff"),
          terminal?.stage,
          t,
        ),
      );
    });

  const setDroneSafeState = (role: string, emergency: boolean) =>
    runAction(
      emergency ? "busy.telloEmergency" : "busy.telloLand",
      async () => {
        if (selectedSession === undefined)
          throw new Error(t("error.monitoringSession"));
        if (
          !selectedSession.roleBindings.some((binding) => binding.role === role)
        )
          throw new Error(t("error.droneUnassigned"));
        const correlationId = crypto.randomUUID();
        const result = await client.submitCommand({
          messageId: crypto.randomUUID(),
          schemaVersion: "1.0",
          messageType: "command.requested",
          action: emergency
            ? FLIGHT_EMERGENCY_STOP_CAPABILITY
            : FLIGHT_LAND_CAPABILITY,
          target: { role },
          sessionId: selectedSession.sessionId,
          parameters: {},
          priority: emergency ? "emergency_stop" : "instructor_override",
          idempotencyKey: `console-tello:${emergency ? "emergency" : "land"}:${correlationId}`,
          requestedAt: new Date().toISOString(),
          ttlMs: 5_000,
          safetyProfile: selectedSession.safetyProfile,
          correlationId,
        });
        const terminal = result.lifecycle.at(-1);
        setNotice(
          commandResultNotice(
            emergency ? t("drone.emergency") : t("drone.land"),
            terminal?.stage,
            t,
          ),
        );
      },
    );

  const armBrainDemo = (settings: BrainDemoSettings) =>
    runAction("busy.brainArm", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.monitoringSession"));
      if (brainDemoBinding === undefined || brainDemoController === undefined)
        throw new Error(t("error.brainController"));
      if (selectedSession.state !== "active")
        throw new Error(t("error.startDemo"));
      if (selectedSession.mode === "physical" && !selectedSession.armed)
        throw new Error(t("error.armFlight"));
      const correlationId = crypto.randomUUID();
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: BRAIN_DEMO_ARM_CAPABILITY,
        target: { role: "brain_flight_demo" },
        sessionId: selectedSession.sessionId,
        parameters: { ...settings },
        priority: "instructor_override",
        idempotencyKey: `console-brain-demo:arm:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 5_000,
        safetyProfile: selectedSession.safetyProfile,
        correlationId,
      });
      const terminal = result.lifecycle.at(-1);
      setNotice(commandResultNotice(t("brain.arm"), terminal?.stage, t));
    });

  const stopBrainDemo = () =>
    runAction("busy.brainStop", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.monitoringSession"));
      if (brainDemoBinding === undefined || brainDemoController === undefined)
        throw new Error(t("error.brainController"));
      const correlationId = crypto.randomUUID();
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: BRAIN_DEMO_STOP_CAPABILITY,
        target: { role: "brain_flight_demo" },
        sessionId: selectedSession.sessionId,
        parameters: {},
        priority: "instructor_override",
        idempotencyKey: `console-brain-demo:stop:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 5_000,
        safetyProfile: selectedSession.safetyProfile,
        correlationId,
      });
      const terminal = result.lifecycle.at(-1);
      setNotice(commandResultNotice(t("brain.stop"), terminal?.stage, t));
    });

  const armFleetSequence = (settings: FleetSequenceSettings) =>
    runAction("busy.fleetArm", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.fleetLesson"));
      if (
        fleetSequenceBinding === undefined ||
        fleetSequenceController === undefined
      )
        throw new Error(t("error.fleetController"));
      if (selectedSession.state !== "active")
        throw new Error(t("error.startSequence"));
      if (selectedSession.mode === "physical" && !selectedSession.armed)
        throw new Error(t("error.armFlight"));
      const correlationId = crypto.randomUUID();
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: FLEET_SEQUENCE_ARM_CAPABILITY,
        target: { role: "fleet_sequence_controller" },
        sessionId: selectedSession.sessionId,
        parameters: { ...settings },
        priority: "instructor_override",
        idempotencyKey: `console-fleet-sequence:arm:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 5_000,
        safetyProfile: selectedSession.safetyProfile,
        correlationId,
      });
      setNotice(
        commandResultNotice(t("fleet.arm"), result.lifecycle.at(-1)?.stage, t),
      );
    });

  const startFleetSequence = () =>
    runAction("busy.fleetStart", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.fleetLesson"));
      if (
        fleetSequenceBinding === undefined ||
        fleetSequenceController === undefined
      )
        throw new Error(t("error.fleetController"));
      const correlationId = crypto.randomUUID();
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: FLEET_SEQUENCE_START_CAPABILITY,
        target: { role: "fleet_sequence_controller" },
        sessionId: selectedSession.sessionId,
        parameters: {},
        priority: "instructor_override",
        idempotencyKey: `console-fleet-sequence:start:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 2_000,
        safetyProfile: selectedSession.safetyProfile,
        correlationId,
      });
      setNotice(
        commandResultNotice(
          t("fleet.startNow"),
          result.lifecycle.at(-1)?.stage,
          t,
        ),
      );
    });

  const stopFleetSequence = () =>
    runAction("busy.fleetStop", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.fleetLesson"));
      if (
        fleetSequenceBinding === undefined ||
        fleetSequenceController === undefined
      )
        throw new Error(t("error.fleetController"));
      const correlationId = crypto.randomUUID();
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: FLEET_SEQUENCE_STOP_CAPABILITY,
        target: { role: "fleet_sequence_controller" },
        sessionId: selectedSession.sessionId,
        parameters: {},
        priority: "instructor_override",
        idempotencyKey: `console-fleet-sequence:stop:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 5_000,
        safetyProfile: selectedSession.safetyProfile,
        correlationId,
      });
      setNotice(
        commandResultNotice(t("fleet.stop"), result.lifecycle.at(-1)?.stage, t),
      );
    });

  const analyzeMediaSource = (source: FabricMediaSource) =>
    runAction(
      "busy.vision",
      async () => {
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
            ? t("notice.noObjects", { source: source.displayName })
            : t("notice.objects", {
                labels: labels.join(", "),
                source: source.displayName,
              }),
        );
      },
      { name: source.displayName },
    );

  if (principal === null) {
    return (
      <div className="fabric-console fabric-login-shell">
        <section
          className="fabric-welcome"
          aria-labelledby="fabric-login-heading"
        >
          <FabricLanguageSwitch locale={locale} onChange={setLocale} t={t} />
          <div className="fabric-welcome-mark" aria-hidden="true">
            CIT
          </div>
          <p className="eyebrow">{t("login.eyebrow")}</p>
          <h1 id="fabric-login-heading">
            {autoConnecting ? t("login.opening") : t("login.welcome")}
          </h1>
          <p className="fabric-welcome-lead">
            {autoConnecting
              ? t("login.connectingLead")
              : t("login.welcomeLead")}
          </p>

          {autoConnecting ? (
            <div className="fabric-connecting" role="status">
              <span className="fabric-spinner" aria-hidden="true" />
              <div>
                <strong>{t("login.wait")}</strong>
                <small>{t("login.launcherCompleting")}</small>
              </div>
            </div>
          ) : (
            <div className="fabric-welcome-actions">
              <div className="fabric-launch-instruction">
                <span>1</span>
                <div>
                  <strong>{t("login.useButton")}</strong>
                  <p>{t("login.useButtonHelp")}</p>
                </div>
              </div>
              <div className="fabric-launch-instruction">
                <span>2</span>
                <div>
                  <strong>{t("login.continueBrowser")}</strong>
                  <p>{t("login.continueBrowserHelp")}</p>
                </div>
              </div>
              <button
                className="fabric-secondary-link"
                type="button"
                aria-expanded={showAccessCode}
                onClick={() => setShowAccessCode((current) => !current)}
              >
                {showAccessCode ? t("login.hideAccess") : t("login.useAccess")}
              </button>
            </div>
          )}

          {showAccessCode && !autoConnecting && (
            <form className="fabric-access-form" onSubmit={signIn}>
              <div>
                <strong>{t("login.pasteAccess")}</strong>
                <small>{t("login.accessHelp")}</small>
              </div>
              <label htmlFor="fabric-credential">
                {t("login.accessLabel")}
                <input
                  id="fabric-credential"
                  type="password"
                  autoComplete="off"
                  minLength={32}
                  maxLength={512}
                  required
                  placeholder={t("login.accessPlaceholder")}
                  value={credential}
                  onChange={(event) => setCredential(event.target.value)}
                />
              </label>
              <button type="submit" disabled={busy !== null}>
                {busy === null ? t("login.continue") : t(busy.key, busy.values)}
              </button>
              <small>{t("login.accessMemory")}</small>
            </form>
          )}
          {error !== null && <div className="fabric-error">{error}</div>}
          {!autoConnecting && (
            <p className="fabric-welcome-help">{t("login.needHelp")}</p>
          )}
        </section>
      </div>
    );
  }

  const nodeGroups = groupNodesByIo(availableNodes);
  const discoveryGroups = groupFabricIntegrationsByIo(
    (discovery?.integrations ?? []).map((integration) =>
      localizeFabricIntegration(locale, integration, t),
    ),
  );
  const courseRoleGroups = groupFabricCourseRolesByIo(
    selectedSession === undefined || selectedCourse === undefined
      ? []
      : visibleRoleRequirements(
          selectedCourse.roles,
          selectedSession.roleBindings,
          selectedSession.state !== "active",
        ),
  );

  return (
    <div className="fabric-console">
      <header className="fabric-header">
        <div>
          <p className="eyebrow">{t("header.eyebrow")}</p>
          <h1>{t("header.title")}</h1>
        </div>
        <FabricLanguageSwitch locale={locale} onChange={setLocale} t={t} />
        <div className="fabric-identity">
          <span className="status-dot status-ok" />
          <div>
            <strong>{t("header.connected")}</strong>
            <small title={principal.identityId}>{t("header.tutor")}</small>
          </div>
          <button type="button" onClick={signOut}>
            {t("header.signOut")}
          </button>
        </div>
        <button
          className="fabric-emergency"
          type="button"
          disabled={!canStopAll || busy !== null}
          onClick={() => void stopAll()}
        >
          <span>■</span> {t("header.stopAll")}
        </button>
      </header>

      <main className="fabric-main">
        <div className="fabric-feedback" aria-live="polite">
          <span>{notice}</span>
          {busy !== null && <strong>{t(busy.key, busy.values)}…</strong>}
          <button type="button" onClick={() => void refresh(true)}>
            {t("header.refresh")}
          </button>
        </div>
        {error !== null && (
          <div className="fabric-error" role="alert">
            {error}
          </div>
        )}

        <section className="fabric-next-step" aria-labelledby="next-step-title">
          <div className="fabric-guide-copy">
            <p className="eyebrow">{t("header.nextStep")}</p>
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
                ? t("guide.action.find")
                : guide.stage === "choose_lesson"
                  ? t("guide.action.choose")
                  : guide.stage === "connect_devices"
                    ? t("guide.action.connect")
                    : guide.stage === "teach"
                      ? t("guide.action.teach")
                      : guide.stage === "lesson_ended"
                        ? t("guide.action.ended")
                        : t("guide.action.review")}
            </button>
          </div>
          <ol className="fabric-steps" aria-label={t("guide.progress")}>
            {[
              t("guide.step.find"),
              t("guide.step.choose"),
              t("guide.step.assign"),
              t("guide.step.safety"),
              t("guide.step.teach"),
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
              <p className="eyebrow">{t("discovery.step")}</p>
              <h2 id="device-discovery-title">{t("discovery.title")}</h2>
              <p className="fabric-panel-intro">{t("discovery.intro")}</p>
            </div>
            <button
              className="fabric-primary-action fabric-find-devices"
              type="button"
              disabled={busy !== null}
              onClick={() => void findDevices()}
            >
              {busy?.key === "busy.findingDevices"
                ? t("discovery.checking")
                : t("discovery.find")}
              <small>{t("discovery.noMovement")}</small>
            </button>
          </div>

          <div className="fabric-discovery-safety">
            <span aria-hidden="true">✓</span>
            <div>
              <strong>{t("discovery.safeTitle")}</strong>
              <p>{t("discovery.safeBody")}</p>
            </div>
          </div>

          {connectableIntegrations.length > 0 && (
            <div className="fabric-connect-all">
              <div>
                <strong>
                  {t("discovery.connectionsReady", {
                    count: connectableIntegrations.length,
                  })}
                </strong>
                <p>{t("discovery.connectAllHelp")}</p>
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
                    <span>{t("discovery.aircraftGrounded")}</span>
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
                {busy?.key === "busy.connectingAll"
                  ? t("discovery.connecting")
                  : t("discovery.connectAll")}
                <small>
                  {discovery?.physicalActuationEnabled
                    ? t("discovery.offState")
                    : t("discovery.startHost")}
                </small>
              </button>
            </div>
          )}

          {discovery !== null && (
            <div className="fabric-discovery-meta">
              <span>
                {discoveryScanned
                  ? t("discovery.checked", {
                      time: fabricFormatTime(discovery.scannedAt, locale),
                    })
                  : t("discovery.notChecked")}
              </span>
              <span>{discovery.hostId}</span>
              <span>
                {discovery.physicalActuationEnabled
                  ? t("discovery.physicalAvailable")
                  : t("discovery.physicalDisabled")}
              </span>
            </div>
          )}

          {(discovery?.warnings.length ?? 0) > 0 && (
            <div className="fabric-discovery-warnings" role="status">
              <strong>{t("discovery.warningTitle")}</strong>
              <p>{t("discovery.warningBody")}</p>
            </div>
          )}

          {discovery === null ? (
            <div className="fabric-empty-state fabric-discovery-loading">
              <span aria-hidden="true">…</span>
              <strong>{t("discovery.loading")}</strong>
              <p>{t("discovery.loadingHelp")}</p>
            </div>
          ) : (
            <div className="fabric-discovery-groups">
              {fabricIoGroups(t).map((group) => (
                <section
                  className={`fabric-discovery-group is-${group.kind}`}
                  key={group.kind}
                >
                  <header>
                    <div>
                      <h3>{group.title}</h3>
                      <p>{group.discoveryDescription}</p>
                    </div>
                    <strong>{discoveryGroups[group.kind].length}</strong>
                  </header>
                  <div className="fabric-discovery-grid">
                    {discoveryGroups[group.kind].map((integration) => (
                      <FabricDiscoveryCard
                        key={integration.integrationId}
                        integration={integration}
                        t={t}
                        busy={busy}
                        canConnect={discoveryConnectionsEnabled}
                        groundedConfirmed={
                          groundedConfirmations[integration.integrationId] ===
                          true
                        }
                        onGroundedChange={(confirmed) =>
                          setGroundedConfirmations((current) => ({
                            ...current,
                            [integration.integrationId]: confirmed,
                          }))
                        }
                        onConnect={() => void connectDiscovered(integration)}
                        onCopySetup={() => void copySetupCommand(integration)}
                        onMatterCommission={commissionMatterPlug}
                        onLegoConnect={(configuration) =>
                          void connectLegoHub(configuration)
                        }
                      />
                    ))}
                    {discoveryGroups[group.kind].length === 0 && (
                      <p className="fabric-empty">{t("discovery.empty")}</p>
                    )}
                  </div>
                </section>
              ))}
            </div>
          )}
        </section>

        <section
          className="fabric-overview"
          aria-label={t("overview.lessonStatus")}
        >
          <FabricMetric
            label={t("overview.devices")}
            value={
              availableNodes.length === 0
                ? t("status.none")
                : String(availableNodes.length)
            }
          />
          <FabricMetric
            label={t("overview.lesson")}
            value={
              selectedSession === undefined
                ? sessions.length > 0
                  ? t("status.selectLesson")
                  : t("status.notSetUp")
                : fabricCourseName(coursePacks, selectedSession, t)
            }
          />
          <FabricMetric
            label={t("overview.lessonStatus")}
            value={fabricSessionState(selectedSession, t)}
          />
          <FabricMetric
            label={t("overview.physical")}
            value={
              selectedSession?.mode === "physical"
                ? selectedSession.armed
                  ? t("status.enabled")
                  : t("status.locked")
                : t("status.locked")
            }
            warning={selectedSession?.armed === true}
          />
        </section>

        <section className="fabric-grid fabric-setup-grid">
          <article
            className="fabric-panel fabric-session-builder"
            id="lesson-setup"
          >
            <PanelHeading
              eyebrow={t("lesson.step2")}
              title={t("lesson.chooseTitle")}
            />
            <p className="fabric-panel-intro">{t("lesson.choosePrompt")}</p>
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
                    <strong>{fabricCourseText(coursePack, t).name}</strong>
                    <small>{fabricCourseText(coursePack, t).summary}</small>
                    <span>
                      {key === chosenKey
                        ? t("lesson.selected")
                        : t("lesson.choose")}
                    </span>
                  </button>
                );
              })}
            </div>
            {selectedCourse !== undefined && (
              <p className="fabric-course-description">
                {fabricCourseText(selectedCourse, t).description}
              </p>
            )}
            <details className="fabric-settings">
              <summary>{t("lesson.settings")}</summary>
              <div className="fabric-fields">
                <label>
                  {t("lesson.site")}
                  <input
                    value={siteId}
                    onChange={(event) => setSiteId(event.target.value)}
                  />
                </label>
                <label>
                  {t("lesson.room")}
                  <input
                    value={roomId}
                    onChange={(event) => setRoomId(event.target.value)}
                  />
                </label>
              </div>
              <label>
                {t("lesson.devicesUsed")}
                <select
                  value={sessionMode}
                  onChange={(event) =>
                    setSessionMode(
                      event.target.value as "simulation" | "physical",
                    )
                  }
                >
                  <option value="simulation">{t("lesson.simulation")}</option>
                  <option value="physical">{t("lesson.physical")}</option>
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
              {t("lesson.setup")}
            </button>
            {sessions.length > 0 && (
              <label className="fabric-existing-session">
                {t("lesson.continue")}
                <select
                  value={selectedSessionId}
                  onChange={(event) => setSelectedSessionId(event.target.value)}
                >
                  <option value="">{t("lesson.existing")}</option>
                  {sessions.map((session) => (
                    <option key={session.sessionId} value={session.sessionId}>
                      {fabricCourseName(coursePacks, session, t)} ·{" "}
                      {fabricSessionState(session, t)} ·{" "}
                      {fabricFormatTime(session.updatedAt, locale)}
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
            <PanelHeading
              eyebrow={t("lesson.step3")}
              title={t("lesson.assignTitle")}
            />
            <p className="fabric-panel-intro">{t("lesson.assignIntro")}</p>
            {selectedSession !== undefined && selectedCourse !== undefined ? (
              <>
                <div className="fabric-role-groups">
                  {fabricIoGroups(t).map((group) => {
                    const requirements = courseRoleGroups[group.kind];
                    if (requirements.length === 0) return null;
                    return (
                      <section
                        className={`fabric-role-group is-${group.kind}`}
                        key={group.kind}
                      >
                        <header>
                          <div>
                            <strong>{group.title}</strong>
                            <small>{group.roleDescription}</small>
                          </div>
                          <span>{requirements.length}</span>
                        </header>
                        <div className="fabric-role-list">
                          {requirements.map((requirement) => (
                            <FabricRoleAssignment
                              key={requirement.role}
                              requirement={requirement}
                              nodes={nodes}
                              session={selectedSession}
                              selectedNodeId={
                                roleSelections[requirement.role] ?? ""
                              }
                              canAssign={canAssignRoles}
                              busy={busy !== null}
                              t={t}
                              onSelect={(nodeId) =>
                                setRoleSelections((current) => ({
                                  ...current,
                                  [requirement.role]: nodeId,
                                }))
                              }
                              onAssign={() => void assignRole(requirement.role)}
                            />
                          ))}
                        </div>
                      </section>
                    );
                  })}
                </div>
                {simultaneousFlowGroups.map((group) => (
                  <section className="fabric-parallel-plan" key={group.groupId}>
                    <header>
                      <div>
                        <span>{t("parallel.runsTogether")}</span>
                        <strong>{t("parallel.title")}</strong>
                      </div>
                      <em>
                        {t("parallel.assigned", {
                          ready: group.outputs.filter((output) =>
                            selectedSession.roleBindings.some(
                              (binding) => binding.role === output.role,
                            ),
                          ).length,
                          total: group.outputs.length,
                        })}
                      </em>
                    </header>
                    <p>
                      {t("parallel.description", {
                        trigger: fabricCapabilityName(group.trigger, locale),
                      })}
                    </p>
                    <ul>
                      {group.outputs.map((output) => {
                        const binding = selectedSession.roleBindings.find(
                          (candidate) => candidate.role === output.role,
                        );
                        return (
                          <li
                            className={
                              binding === undefined
                                ? "is-unassigned"
                                : "is-assigned"
                            }
                            key={output.flowId}
                          >
                            <span aria-hidden="true">
                              {binding === undefined ? "○" : "✓"}
                            </span>
                            <div>
                              <strong>
                                {fabricRoleText(output.role, t).name}
                              </strong>
                              <small>
                                {fabricCapabilityName(output.action, locale)}
                              </small>
                            </div>
                            <em>
                              {binding === undefined
                                ? t("status.notIncluded")
                                : nodeDisplayName(nodes, binding.nodeId)}
                            </em>
                          </li>
                        );
                      })}
                    </ul>
                    <small>{t("parallel.safety")}</small>
                  </section>
                ))}
              </>
            ) : (
              <div className="fabric-empty-state">
                <span aria-hidden="true">2</span>
                <strong>{t("lesson.chooseFirst")}</strong>
                <p>{t("lesson.matchesAppear")}</p>
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
              <PanelHeading
                eyebrow={t("safety.step4")}
                title={t("safety.title")}
              />
              <strong>
                {selectedSession === undefined
                  ? t("safety.setupFirst")
                  : selectedSession.mode === "simulation"
                    ? t("safety.simulation")
                    : selectedSession.armed
                      ? t("safety.enabled")
                      : t("safety.locked")}
              </strong>
              <p>
                {selectedSession?.mode === "physical"
                  ? t("safety.physicalHelp")
                  : t("safety.simulationHelp")}
              </p>
            </div>
          </div>

          {selectedSession?.mode === "physical" &&
            !selectedSession.armed &&
            requiresArmingForStart && (
              <label className="fabric-safety-confirmation">
                <input
                  type="checkbox"
                  checked={safetyConfirmed}
                  onChange={(event) => setSafetyConfirmed(event.target.checked)}
                />
                <span>{t("safety.confirm")}</span>
              </label>
            )}

          <div className="fabric-session-actions">
            {selectedSession?.mode === "physical" &&
              !selectedSession.armed &&
              requiresArmingForStart && (
                <button
                  className="fabric-enable-physical"
                  type="button"
                  disabled={
                    !canManageSessions ||
                    busy !== null ||
                    !requiredRolesReady ||
                    !safetyConfirmed ||
                    !["ready", "paused", "active"].includes(
                      selectedSession.state,
                    )
                  }
                  onClick={() => void enablePhysicalControls()}
                >
                  {selectedSession.state === "active"
                    ? t("safety.pauseEnable")
                    : t("safety.enable")}
                </button>
              )}
            {selectedSession?.armed && (
              <button
                type="button"
                disabled={!canManageSessions || busy !== null}
                onClick={() => void changeSessionState("disarm")}
              >
                {t("safety.lock")}
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
                  selectedSession.armed !== true &&
                  requiresArmingForStart)
              }
              onClick={() => void changeSessionState("start")}
            >
              {selectedSession?.state === "paused"
                ? t("safety.resume")
                : t("safety.start")}
            </button>
            {selectedSession?.state === "active" && (
              <button
                type="button"
                disabled={!canManageSessions || busy !== null}
                onClick={() => void changeSessionState("pause")}
              >
                {t("safety.pause")}
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
              {t("safety.end")}
            </button>
          </div>
        </section>

        <section className="fabric-panel fabric-test-panel" id="live-controls">
          <PanelHeading eyebrow={t("test.step5")} title={t("test.title")} />
          <p className="fabric-panel-intro">
            {selectedSession?.state === "active"
              ? t("test.runningHelp")
              : t("test.waitingHelp")}
          </p>
          <div className="fabric-test-actions">
            {(selectedCourse?.flows.length ?? 0) > 0 && (
              <button
                type="button"
                disabled={selectedSession?.state !== "active" || busy !== null}
                onClick={() => void checkInput()}
              >
                {t("test.input")}
                <small>{t("test.inputHelp")}</small>
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
                {t("test.agent")}
                <small>{t("test.agentHelp")}</small>
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
                {t("test.glasses")}
                <small>{t("test.glassesHelp")}</small>
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
                {t("test.robotStop")}
                <small>{t("test.robotStopHelp")}</small>
              </button>
            )}
            <div className="fabric-live-state">
              <span
                className={`status-dot ${selectedSession?.state === "active" ? "status-ok" : "status-muted"}`}
              />
              <div>
                <strong>
                  {selectedSession?.state === "active"
                    ? t("test.running")
                    : t("test.waiting")}
                </strong>
                <small>
                  {t("test.inProgress", {
                    count: countActiveFabricCommands(lifecycle),
                  })}
                </small>
              </div>
            </div>
          </div>
        </section>

        {canReadMedia && (
          <section className="fabric-panel fabric-media-panel">
            <PanelHeading
              eyebrow={t("media.eyebrow")}
              title={t("media.title")}
            />
            <p className="fabric-help">{t("media.intro")}</p>
            {canPairMedia && (
              <div className="fabric-camera-pairing">
                <div>
                  <strong>{t("media.connectMeta")}</strong>
                  <span>{t("media.connectMetaHelp")}</span>
                </div>
                {mediaPairing === null ? (
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => void startMetaCameraPairing()}
                  >
                    {t("media.createPairing")}
                  </button>
                ) : (
                  <div className="fabric-camera-pairing-details">
                    <ol>
                      <li>{t("media.pairStep1")}</li>
                      <li>{t("media.pairStep2")}</li>
                      <li>{t("media.pairStep3")}</li>
                    </ol>
                    <label>
                      {t("media.address")}
                      <span>
                        <input readOnly value={mediaPairing.fabricOrigin} />
                        <button
                          type="button"
                          onClick={() =>
                            void copyMediaPairingValue(
                              mediaPairing.fabricOrigin,
                              t("media.address"),
                            )
                          }
                        >
                          {t("media.copy")}
                        </button>
                      </span>
                    </label>
                    <label>
                      {t("media.code")}
                      <span>
                        <input readOnly value={mediaPairing.pairingCode} />
                        <button
                          type="button"
                          onClick={() =>
                            void copyMediaPairingValue(
                              mediaPairing.pairingCode,
                              t("media.code"),
                            )
                          }
                        >
                          {t("media.copy")}
                        </button>
                      </span>
                    </label>
                    <small>
                      {t("media.expiry", {
                        time: fabricFormatTime(mediaPairing.expiresAt, locale),
                        site: mediaPairing.siteId,
                        room: mediaPairing.roomId,
                      })}
                    </small>
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => void startMetaCameraPairing()}
                    >
                      {t("media.replaceCode")}
                    </button>
                  </div>
                )}
              </div>
            )}
            {mediaSources.length === 0 ? (
              <div className="fabric-empty fabric-media-empty">
                <strong>{t("media.none")}</strong>
                <span>{t("media.noneHelp")}</span>
              </div>
            ) : (
              <div className="fabric-media-grid">
                {mediaSources.map((source) => (
                  <MediaFeedCard
                    key={source.sourceId}
                    source={source}
                    client={client}
                    locale={locale}
                    t={t}
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
            <p className="fabric-privacy-note">{t("media.privacy")}</p>
          </section>
        )}

        <section className="fabric-panel fabric-sensor-panel">
          <PanelHeading
            eyebrow={t("sensor.eyebrow")}
            title={t("sensor.title")}
          />
          <p className="fabric-help">{t("sensor.intro")}</p>
          {sensorReadings.length === 0 ? (
            <div className="fabric-empty">{t("sensor.none")}</div>
          ) : (
            <div className="fabric-sensor-grid">
              {sensorReadings.map((reading) => (
                <article className="fabric-sensor-card" key={reading.key}>
                  <header>
                    <strong>
                      {fabricCapabilityName(reading.topic, locale)}
                    </strong>
                    <span>{fabricFormatTime(reading.observedAt, locale)}</span>
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

        {fleetSequenceController !== undefined &&
          selectedSession !== undefined && (
            <FabricFleetSequencePanel
              controllerName={fleetSequenceController.displayName}
              simulated={fleetSequenceController.simulated}
              {...(fleetSequenceStatus === undefined
                ? {}
                : { status: fleetSequenceStatus })}
              inputNodes={fleetSequenceInputNodes}
              sessionState={selectedSession.state}
              sessionArmed={selectedSession.armed === true}
              busy={busy !== null}
              canSubmit={canSubmitCommands}
              onArm={(settings) => void armFleetSequence(settings)}
              onStart={() => void startFleetSequence()}
              onStop={() => void stopFleetSequence()}
              locale={locale}
              t={t}
            />
          )}

        {brainDemoController !== undefined && selectedSession !== undefined && (
          <FabricBrainDemoPanel
            controllerName={brainDemoController.displayName}
            simulated={brainDemoController.simulated}
            {...(brainDemoStatus === undefined
              ? {}
              : { status: brainDemoStatus })}
            sessionState={selectedSession.state}
            sessionArmed={selectedSession.armed === true}
            busy={busy !== null}
            canSubmit={canSubmitCommands}
            onArm={(settings) => void armBrainDemo(settings)}
            onStop={() => void stopBrainDemo()}
            locale={locale}
            t={t}
          />
        )}

        <FabricDronePanel
          drones={assignedDrones}
          busy={busy !== null}
          canSubmit={canSubmitCommands}
          onLand={(role) => void setDroneSafeState(role, false)}
          onEmergencyStop={(role) => void setDroneSafeState(role, true)}
          t={t}
        />

        {(smartPlugNodes.length > 0 ||
          selectedCourse?.roles.some(
            (requirement) => requirement.role === "classroom_plug",
          )) && (
          <section className="fabric-panel fabric-smart-plug-panel">
            <PanelHeading eyebrow={t("plug.eyebrow")} title={t("plug.title")} />
            <div className="fabric-smart-plug-layout">
              <div className="fabric-smart-plug-state">
                <span
                  className={`fabric-plug-indicator ${smartPlugState?.on ? "is-on" : "is-off"}`}
                  aria-hidden="true"
                >
                  {smartPlugState?.on ? t("plug.onState") : t("plug.offState")}
                </span>
                <div>
                  <strong>
                    {selectedSmartPlug?.displayName ?? t("plug.noneAssigned")}
                  </strong>
                  <small>
                    {selectedSmartPlug === undefined
                      ? t("plug.compatible", { count: smartPlugNodes.length })
                      : `${metadataText(selectedSmartPlug, "vendorBrand") ?? "compatible"} · ${metadataText(selectedSmartPlug, "model") ?? selectedSmartPlug.nodeId}`}
                  </small>
                  <small>
                    {smartPlugState === undefined
                      ? t("plug.stateUnknown")
                      : t("plug.observed", {
                          time: fabricFormatTime(
                            smartPlugState.observedAt,
                            locale,
                          ),
                          source:
                            smartPlugState.source === undefined
                              ? ""
                              : ` · ${smartPlugState.source}`,
                        })}
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
                  {t("plug.turnOn")}
                  <small>
                    {selectedSession?.state === "active" &&
                    (selectedSession.mode !== "physical" ||
                      selectedSession.armed)
                      ? t("plug.turnOnHelp")
                      : t("plug.afterSafety")}
                  </small>
                </button>
                <button
                  className="fabric-power-off"
                  type="button"
                  disabled={!canTurnSmartPlugOff}
                  onClick={() => void setSmartPlugPower(false)}
                >
                  {t("plug.turnOff")}
                  <small>{t("plug.turnOffHelp")}</small>
                </button>
              </div>
            </div>
            <p className="fabric-help">{t("plug.help")}</p>
          </section>
        )}

        <section className="fabric-panel fabric-node-panel">
          <PanelHeading eyebrow={t("nodes.eyebrow")} title={t("nodes.title")} />
          <p className="fabric-help">{t("nodes.intro")}</p>
          <div className="fabric-io-groups">
            <FabricNodeGroup
              kind="input"
              title={t("io.input.label")}
              description={t("io.input.discovery")}
              nodes={nodeGroups.input}
              t={t}
            />
            <FabricNodeGroup
              kind="bidirectional"
              title={t("io.bidirectional.label")}
              description={t("io.bidirectional.discovery")}
              nodes={nodeGroups.bidirectional}
              t={t}
            />
            <FabricNodeGroup
              kind="output"
              title={t("io.output.label")}
              description={t("io.output.discovery")}
              nodes={nodeGroups.output}
              t={t}
            />
          </div>
        </section>

        <details className="fabric-advanced">
          <summary>
            <strong>{t("diagnostics.title")}</strong>
            <span>{t("diagnostics.subtitle")}</span>
          </summary>
          <section className="fabric-grid fabric-stream-grid">
            <article className="fabric-panel">
              <PanelHeading
                eyebrow={t("diagnostics.signalEyebrow")}
                title={t("diagnostics.signalTitle")}
              />
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
                          {fabricFormatTime(item.event.timestamp, locale)}
                        </small>
                      </div>
                      <em>{Math.round((item.event.confidence ?? 1) * 100)}%</em>
                    </li>
                  ))}
                {events.length === 0 && (
                  <li className="fabric-empty">{t("diagnostics.noSignals")}</li>
                )}
              </ol>
            </article>
            <article className="fabric-panel">
              <PanelHeading
                eyebrow={t("diagnostics.commandEyebrow")}
                title={t("diagnostics.commandTitle")}
              />
              <ol className="fabric-stream-list">
                {[...lifecycle]
                  .reverse()
                  .slice(0, 12)
                  .map((item) => (
                    <li key={item.streamSequence}>
                      <span>{item.streamSequence}</span>
                      <div>
                        <strong>
                          {fabricPhase(item.lifecycle.stage, locale)}
                        </strong>
                        <small>
                          {shortId(item.lifecycle.commandId)} ·{" "}
                          {item.lifecycle.targetNodeId}
                        </small>
                      </div>
                      <em>
                        {fabricFormatTime(item.lifecycle.occurredAt, locale)}
                      </em>
                    </li>
                  ))}
                {lifecycle.length === 0 && (
                  <li className="fabric-empty">
                    {t("diagnostics.noCommands")}
                  </li>
                )}
              </ol>
            </article>
          </section>

          {offlineNodeCount > 0 && (
            <section className="fabric-panel fabric-offline-history">
              <PanelHeading
                eyebrow={t("diagnostics.offlineEyebrow")}
                title={t("diagnostics.offlineTitle", {
                  count: offlineNodeCount,
                })}
              />
              <p className="fabric-help">{t("diagnostics.offlineHelp")}</p>
            </section>
          )}

          {audit.length > 0 && (
            <section className="fabric-panel fabric-audit-panel">
              <PanelHeading
                eyebrow={t("diagnostics.auditEyebrow")}
                title={t("diagnostics.auditTitle")}
              />
              <div className="fabric-audit-list">
                {audit.slice(0, 10).map((record) => (
                  <div key={record.auditId}>
                    <strong>{record.action}</strong>
                    <span>{record.actorId}</span>
                    <small>
                      {record.resourceId ?? record.resourceType} ·{" "}
                      {fabricFormatTime(record.occurredAt, locale)}
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

function FabricRoleAssignment({
  requirement,
  nodes,
  session,
  selectedNodeId,
  canAssign,
  busy,
  t,
  onSelect,
  onAssign,
}: {
  requirement: CoursePack["roles"][number];
  nodes: IntegrationNode[];
  session: InteractionSession;
  selectedNodeId: string;
  canAssign: boolean;
  busy: boolean;
  t: FabricTranslate;
  onSelect: (nodeId: string) => void;
  onAssign: () => void;
}) {
  const candidates = compatibleNodes(nodes, session, requirement);
  const binding = session.roleBindings.find(
    (candidate) => candidate.role === requirement.role,
  );

  return (
    <div className="fabric-role">
      <span
        className={`fabric-role-status ${binding === undefined ? "is-missing" : "is-ready"}`}
        aria-hidden="true"
      >
        {binding === undefined ? "!" : "✓"}
      </span>
      <div>
        <strong>{fabricRoleText(requirement.role, t).name}</strong>
        <small>
          {fabricRoleText(requirement.role, t).description}
          {requirement.optional ? ` (${t("status.optional")})` : ""}
        </small>
      </div>
      <select
        aria-label={t("role.deviceFor", {
          role: fabricRoleText(requirement.role, t).name,
        })}
        value={selectedNodeId}
        disabled={!canAssign || session.state === "active"}
        onChange={(event) => onSelect(event.target.value)}
      >
        <option value="">
          {candidates.length === 0 ? t("role.noMatch") : t("role.chooseDevice")}
        </option>
        {candidates.map((node) => (
          <option key={node.nodeId} value={node.nodeId}>
            {node.displayName} · {fabricConnectionState(node, t)}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={
          !canAssign ||
          busy ||
          session.state === "active" ||
          !selectedNodeId ||
          binding?.nodeId === selectedNodeId
        }
        onClick={onAssign}
      >
        {binding === undefined ? t("role.useDevice") : t("role.change")}
      </button>
      {candidates.length === 0 && (
        <p className="fabric-role-help">{t("role.startAdapter")}</p>
      )}
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

function FabricLanguageSwitch({
  locale,
  onChange,
  t,
}: {
  locale: Locale;
  onChange: (locale: Locale) => void;
  t: FabricTranslate;
}) {
  return (
    <div
      className="fabric-language-switch"
      role="group"
      aria-label={t("language.label")}
    >
      {LOCALES.map((candidate) => (
        <button
          type="button"
          className={candidate === locale ? "is-current" : undefined}
          aria-pressed={candidate === locale}
          key={candidate}
          onClick={() => onChange(candidate)}
        >
          {candidate === "ko" ? t("language.ko") : t("language.en")}
        </button>
      ))}
    </div>
  );
}

function FabricDiscoveryCard({
  integration,
  t,
  busy,
  canConnect,
  groundedConfirmed,
  onGroundedChange,
  onConnect,
  onCopySetup,
  onMatterCommission,
  onLegoConnect,
}: {
  integration: FabricIntegrationDiscovery;
  t: FabricTranslate;
  busy: BusyAction;
  canConnect: boolean;
  groundedConfirmed: boolean;
  onGroundedChange: (confirmed: boolean) => void;
  onConnect: () => void;
  onCopySetup: () => void;
  onMatterCommission: (setupCode: string) => Promise<boolean>;
  onLegoConnect: (configuration: LegoConnectionConfiguration) => void;
}) {
  const status = discoveryStatus(integration.status, t);
  const connected = integration.status === "connected";
  return (
    <article
      id={`integration-${integration.integrationId}`}
      className={`fabric-discovery-card is-${integration.status.replaceAll("_", "-")}`}
    >
      <header>
        <span className="fabric-discovery-icon" aria-hidden="true">
          {DISCOVERY_ICONS[integration.icon ?? ""] ?? "IO"}
        </span>
        <div>
          <h3>{integration.displayName}</h3>
          <small>{integration.connectionMethod}</small>
          <span className={`fabric-io-label is-${integration.ioType}`}>
            {fabricIoLabel(integration.ioType, t)}
          </span>
        </div>
        <strong className={`fabric-discovery-status is-${status.tone}`}>
          {status.label}
        </strong>
      </header>

      <p className="fabric-discovery-summary">{integration.summary}</p>

      {integration.integrationId === "matter-smart-plugs" && (
        <FabricMatterSetup
          busy={busy?.key === "busy.addingMatter"}
          canConnect={canConnect}
          connected={connected}
          onCommission={onMatterCommission}
          t={t}
        />
      )}

      {integration.integrationId === "lego-hubs" && !connected && (
        <FabricLegoSetup
          busy={busy?.key === "busy.connectingLego"}
          canConnect={canConnect}
          connected={connected}
          onConnect={onLegoConnect}
          t={t}
        />
      )}

      {integration.candidates.length > 0 && (
        <ul className="fabric-candidate-list">
          {integration.candidates.map((candidate, index) => (
            <li key={`${candidate.candidateId}:${index}`}>
              <span
                className={`status-dot ${candidate.status === "found" ? "status-ok" : "status-muted"}`}
              />
              <div>
                <div className="fabric-candidate-title">
                  <strong>{candidate.displayName}</strong>
                  {discoveryLinkLabel(candidate, t) !== undefined && (
                    <span
                      className={`fabric-link-state is-${candidate.linkState?.replaceAll("_", "-")}`}
                    >
                      {discoveryLinkLabel(candidate, t)}
                    </span>
                  )}
                </div>
                <small>
                  {candidate.transport}
                  {candidate.signalPercent === undefined
                    ? ""
                    : ` · ${t("discovery.signal", { percent: candidate.signalPercent })}`}
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
            <span>{t("discovery.aircraftGrounded")}</span>
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
            {integration.actionLabel ?? t("discovery.connect")}
          </button>
        )}
        {integration.setupCommand !== undefined && !connected && (
          <button
            className="fabric-copy-setup"
            type="button"
            disabled={busy !== null}
            onClick={onCopySetup}
          >
            {t("discovery.copySetup")}
          </button>
        )}
      </div>

      <details className="fabric-device-help">
        <summary>
          {connected
            ? t("discovery.connectionDetails")
            : t("discovery.whatToDo")}
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
          <small>
            {t("discovery.nodes", {
              nodes: integration.connectedNodeIds.join(", "),
            })}
          </small>
        )}
        <p>{integration.safetyNote}</p>
      </details>
    </article>
  );
}

function MediaFeedCard({
  source,
  client,
  locale,
  t,
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
  locale: Locale;
  t: FabricTranslate;
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
  const [frameMessage, setFrameMessage] = useState(() => t("media.waitFrame"));
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
            ? t("media.waitFrame")
            : describeFabricError(caught, t),
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
  }, [client, source.sourceId, t]);

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
            {fabricMediaKind(source.kind, locale)} ·{" "}
            {source.captureMode === "video"
              ? t("media.captureVideo")
              : t("media.captureSnapshot")}
          </small>
        </div>
        <span className={`fabric-media-state is-${source.state}`}>
          {source.state === "online" ? t("media.live") : t("media.waiting")}
        </span>
      </header>
      <div className="fabric-media-frame">
        {frameUrl === null ? (
          <div className="fabric-media-placeholder">
            <span aria-hidden="true">CAM</span>
            <strong>{frameMessage}</strong>
          </div>
        ) : (
          <img
            src={frameUrl}
            alt={t("media.latestAlt", { name: source.displayName })}
          />
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
            ? t("media.noDimensions")
            : `${source.width} × ${source.height}`}
        </span>
        <span>
          {source.lastFrameAt === null
            ? t("media.noFrame")
            : t("media.updated", {
                time: fabricFormatTime(source.lastFrameAt, locale),
              })}
        </span>
      </div>
      <button
        className="fabric-analyze-button"
        type="button"
        disabled={!canAnalyze || busy || source.frameSequence === 0}
        onClick={onAnalyze}
      >
        {t("media.recognize")}
      </button>
      {analysis !== null && (
        <div className="fabric-detection-results" aria-live="polite">
          <strong>
            {analysis.detections.length === 0
              ? t("media.noneFound")
              : t("media.objectsFound")}
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
                  ? t("media.assignPlug")
                  : t("media.explicitPlug", { name: smartPlugName })}
              </small>
              <div>
                <button
                  type="button"
                  disabled={!canTurnPlugOn}
                  onClick={() => onPower(true)}
                >
                  {t("media.plugOn")}
                </button>
                <button
                  type="button"
                  disabled={!canTurnPlugOff}
                  onClick={() => onPower(false)}
                >
                  {t("media.plugOff")}
                </button>
              </div>
            </div>
          ) : analysis.detections.length > 0 ? (
            <div className="fabric-detection-actions">
              <small>
                {droneDetected
                  ? t("media.droneAdvisory")
                  : t("media.noMappedAction")}
              </small>
            </div>
          ) : null}
        </div>
      )}
    </article>
  );
}

function FabricNodeCard({
  node,
  t,
}: {
  node: IntegrationNode;
  t: FabricTranslate;
}) {
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
          {node.simulated ? t("nodes.simulator") : t("nodes.physical")}
          {agentType === undefined ? "" : ` · ${agentType}`}
        </small>
        <details className="fabric-node-technical">
          <summary>{t("nodes.technical")}</summary>
          <small>
            {node.pluginId} · {node.nodeId} · {t("nodes.host")} {node.hostId}
          </small>
          <CapabilityList
            label={t("nodes.sends")}
            t={t}
            capabilities={node.publishedCapabilities.map(
              (capability) => capability.name,
            )}
          />
          <CapabilityList
            label={t("nodes.receives")}
            t={t}
            capabilities={node.consumedCapabilities.map(
              (capability) => capability.name,
            )}
          />
        </details>
      </div>
      <div className="fabric-node-state">
        <span>{fabricConnectionState(node, t)}</span>
        <small>
          {fabricHealthState(node.healthState, t)}
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
  t,
}: {
  kind: FabricNodeIoKind;
  title: string;
  description: string;
  nodes: IntegrationNode[];
  t: FabricTranslate;
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
          <p className="fabric-empty">{t("nodes.empty")}</p>
        ) : (
          nodes.map((node) => (
            <FabricNodeCard key={node.nodeId} node={node} t={t} />
          ))
        )}
      </div>
    </article>
  );
}

function CapabilityList({
  label,
  capabilities,
  t,
}: {
  label: string;
  capabilities: string[];
  t: FabricTranslate;
}) {
  return (
    <div className="fabric-capability-row">
      <span>{label}</span>
      <div>
        {capabilities.length === 0 ? (
          <em>{t("nodes.none")}</em>
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

const fabricIoGroups = (
  t: FabricTranslate,
): ReadonlyArray<{
  kind: FabricNodeIoKind;
  title: string;
  discoveryDescription: string;
  roleDescription: string;
}> => [
  {
    kind: "input",
    title: t("io.input.title"),
    discoveryDescription: t("io.input.discovery"),
    roleDescription: t("io.input.role"),
  },
  {
    kind: "bidirectional",
    title: t("io.bidirectional.title"),
    discoveryDescription: t("io.bidirectional.discovery"),
    roleDescription: t("io.bidirectional.role"),
  },
  {
    kind: "output",
    title: t("io.output.title"),
    discoveryDescription: t("io.output.discovery"),
    roleDescription: t("io.output.role"),
  },
];

const fabricIoLabel = (kind: FabricNodeIoKind, t: FabricTranslate) =>
  kind === "bidirectional"
    ? t("io.bidirectional.label")
    : kind === "input"
      ? t("io.input.label")
      : t("io.output.label");

const DISCOVERY_ICONS: Record<string, string> = {
  glasses: "XR",
  terminal: "AI",
  hand: "LM",
  robot: "S1",
  drone: "TL",
  brain: "MW",
  plug: "PL",
  lego: "LE",
  sphero: "SB",
};

const discoveryStatus = (
  status: FabricIntegrationDiscovery["status"],
  t: FabricTranslate,
) => {
  switch (status) {
    case "connected":
      return { label: t("status.connected"), tone: "connected" };
    case "found":
      return { label: t("status.found"), tone: "found" };
    case "ready":
      return { label: t("status.ready"), tone: "ready" };
    case "setup_required":
      return { label: t("status.setup"), tone: "setup" };
    case "not_found":
      return { label: t("status.notFound"), tone: "missing" };
    case "unavailable":
      return { label: t("status.unavailable"), tone: "missing" };
    case "not_scanned":
      return { label: t("status.notChecked"), tone: "unchecked" };
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

const nodeDisplayName = (nodes: IntegrationNode[], nodeId: string) =>
  nodes.find((node) => node.nodeId === nodeId)?.displayName ?? nodeId;

const isRobotSensorRole = (role: string) => /^robot_sensor_[1-8]$/.test(role);
const isFleetSequenceInputRole = (role: string) =>
  /^fleet_sequence_input_[1-4]$/.test(role);

const visibleRoleRequirements = (
  requirements: CoursePack["roles"],
  bindings: InteractionSession["roleBindings"],
  showOneEmptySlot: boolean,
) => {
  const boundRoles = new Set(bindings.map((binding) => binding.role));
  const shownEmptyFamilies = new Set<string>();
  return requirements.filter((requirement) => {
    const family = isSafetyDroneRole(requirement.role)
      ? "safety_drone"
      : isFleetSequenceInputRole(requirement.role)
        ? "fleet_sequence_input"
        : isRobotSensorRole(requirement.role)
          ? "robot_sensor"
          : null;
    if (family === null || boundRoles.has(requirement.role)) return true;
    if (!showOneEmptySlot) return false;
    if (shownEmptyFamilies.has(family)) return false;
    shownEmptyFamilies.add(family);
    return true;
  });
};

const commandResultNotice = (
  label: string,
  stage: string | undefined,
  t: FabricTranslate,
) => {
  if (stage === "SUCCEEDED") return t("command.success", { label });
  if (stage === "FAILED" || stage === "REJECTED") {
    return t("command.failed", { label });
  }
  if (stage === "CANCELLED" || stage === "TIMED_OUT") {
    return t("command.stopped", { label });
  }
  return t("command.sent", { label });
};

const describeFabricError = (caught: unknown, t: FabricTranslate) => {
  if (caught instanceof FabricApiError) {
    const messages: Record<string, string> = {
      AUTHENTICATION_REQUIRED: t("error.auth"),
      PHYSICAL_EXECUTION_DISABLED: t("error.physicalDisabled"),
      SESSION_NOT_ACTIVE: t("error.sessionInactive"),
      NODE_UNAVAILABLE: t("error.nodeUnavailable"),
      REQUIRED_ROLES_UNASSIGNED: t("error.rolesMissing"),
    };
    return (
      messages[caught.code] ?? t("error.requestFailed") + ` (${caught.code})`
    );
  }
  return caught instanceof Error ? caught.message : t("error.requestFailed");
};

const shortId = (value: string) =>
  value.length > 20 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;

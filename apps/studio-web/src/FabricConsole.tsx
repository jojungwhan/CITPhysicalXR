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
  type ReactNode,
} from "react";

import {
  FabricApiError,
  FabricClient,
  type FabricAuditRecord,
  type FabricDiscoveryCandidate,
  type FabricDiscoveryReport,
  type FabricInstallationInfo,
  type FabricIntegrationDiscovery,
  type FabricMediaPairing,
  type FabricMediaSource,
  type FabricRememberedConnections,
  type LegoConnectionConfiguration,
  type SpheroBoltSelection,
  type SpheroOllieSelection,
  type WonderRobotSelection,
  type FabricPrincipal,
  type FabricSessionStartPolicy,
  type StoredFabricEvent,
  type StoredFabricLifecycle,
} from "./fabric-client.js";
import {
  canRunFabricDiscoveryConnection,
  discoveryLinkLabel,
} from "./fabric-discovery.js";
import { consumeConsoleTicket } from "./fabric-console-access.js";
import { awaitFabricCommandTerminal } from "./fabric-command-chain.js";
import {
  directControlSessionActions,
  plannedControlAssignments,
  sessionCoversNodes,
} from "./fabric-control-session.js";
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
  isTelloNode,
  isSafetyDroneRole,
  preferredTelloControlSession,
} from "./fabric-drone.js";
import {
  assignedFleetSequenceInputNodes,
  FLEET_SEQUENCE_ARM_CAPABILITY,
  FLEET_SEQUENCE_START_CAPABILITY,
  FLEET_SEQUENCE_STOP_CAPABILITY,
  isFleetSequenceControllerNode,
  latestFleetSequenceStatus,
  preferredFleetSequenceControlSession,
  type FleetSequenceSettings,
} from "./fabric-fleet-sequence.js";
import {
  classifyFabricNodeIo,
  groupFabricCourseRolesByIo,
  isAvailableFabricNode,
  type FabricNodeIoKind,
} from "./fabric-node-io.js";
import {
  connectedFabricDeviceCount,
  fabricDiscoveryTierOpenByDefault,
  groupFabricIntegrationsByReadiness,
} from "./fabric-discovery-readiness.js";
import { countActiveFabricCommands } from "./fabric-lifecycle.js";
import { fabricMediaFrameAvailable } from "./fabric-media.js";
import {
  clearAircraftGroundedConfirmation,
  clearFlightSafetyConfirmation,
  readAircraftGroundedConfirmation,
  readFlightSafetyConfirmation,
  saveAircraftGroundedConfirmation,
  saveFlightSafetyConfirmation,
} from "./fabric-session-confirmations.js";
import { parallelFlowGroups } from "./fabric-parallel-flow.js";
import {
  automaticRoleAssignments,
  reconciledRoleSelections,
  refreshedSessionSelection,
} from "./fabric-session-selection.js";
import {
  isSmartPlugNode,
  isSmartPlugRole,
  isSwitchableLoadVisionLabel,
  latestSmartPlugState,
  preferredSmartPlugControlSession,
  POWER_SET_CAPABILITY,
  smartPlugStateFromHealth,
} from "./fabric-smart-plug.js";
import {
  latestSensorReadings,
  type FabricSensorReading,
} from "./fabric-sensors.js";
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
import { FabricDeviceIoPanel } from "./FabricDeviceIoPanel.js";
import { FabricDronePanel } from "./FabricDronePanel.js";
import {
  FabricDiscoveryActions,
  type FabricDiscoveryActionFeedback,
} from "./FabricDiscoveryActions.js";
import { FabricFleetSequencePanel } from "./FabricFleetSequencePanel.js";
import { FabricG2Guide } from "./FabricG2Guide.js";
import { FabricInfoDisclosure } from "./FabricInfoDisclosure.js";
import { FabricInstallationPanel } from "./FabricInstallationPanel.js";
import { FabricLegoSetup } from "./FabricLegoSetup.js";
import { FabricLeapPanel } from "./FabricLeapPanel.js";
import { FabricMatterSetup } from "./FabricMatterSetup.js";
import { FabricSpheroPanel } from "./FabricSpheroPanel.js";
import { FabricSpheroSetup } from "./FabricSpheroSetup.js";
import { FabricSetupProgress } from "./FabricSetupProgress.js";
import { FabricSmartPlugPanel } from "./FabricSmartPlugPanel.js";
import { FabricSynchronizedMotionPanel } from "./FabricSynchronizedMotionPanel.js";
import { FabricWonderWorkshopPanel } from "./FabricWonderWorkshopPanel.js";
import { FabricWonderWorkshopSetup } from "./FabricWonderWorkshopSetup.js";
import { requiresSpatialSafetyConfirmation } from "./fabric-device-controls.js";
import {
  isWonderNode,
  WONDER_STOP_CAPABILITY,
} from "./fabric-wonder-workshop.js";
import {
  isSpheroNode,
  preferredSpheroControlSession,
  SPHERO_STOP_CAPABILITY,
} from "./fabric-sphero-bolt.js";
import {
  synchronizedInputKinds,
  synchronizedMotionCommands,
  type SynchronizedMotionDirection,
} from "./fabric-synchronized-motion.js";
import {
  createSiteTemplate,
  selectWindowsInstallationArtifact,
  verifyInstallationArtifact,
} from "./fabric-installation.js";
import { saveBlobAsFile, saveTextAsFile } from "./download.js";

type BusyAction = {
  key: FabricMessageKey;
  values?: Record<string, string | number>;
} | null;

type IntegrationActionFeedback = FabricDiscoveryActionFeedback & {
  integrationId: string;
};

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
  const [rememberedConnections, setRememberedConnections] =
    useState<FabricRememberedConnections | null>(null);
  const [installation, setInstallation] =
    useState<FabricInstallationInfo | null>(null);
  const [coursePacks, setCoursePacks] = useState<CoursePack[]>([]);
  const [sessions, setSessions] = useState<InteractionSession[]>([]);
  const [events, setEvents] = useState<StoredFabricEvent[]>([]);
  const [fleetEvents, setFleetEvents] = useState<StoredFabricEvent[]>([]);
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
  const [aircraftGroundedConfirmed, setAircraftGroundedConfirmed] = useState(
    readAircraftGroundedConfirmation,
  );
  const [safetyConfirmed, setSafetyConfirmed] = useState(
    readFlightSafetyConfirmation,
  );
  const [synchronizedMotionEnabled, setSynchronizedMotionEnabled] =
    useState(false);
  const [
    includeTelloInSynchronizedMotion,
    setIncludeTelloInSynchronizedMotion,
  ] = useState(false);
  const [synchronizedMotionSessionId, setSynchronizedMotionSessionId] =
    useState("");
  const [busy, setBusy] = useState<BusyAction>(null);
  const [notice, setNotice] = useState(() => t("notice.ready"));
  const [error, setError] = useState<string | null>(null);
  const [integrationActionFeedback, setIntegrationActionFeedback] =
    useState<IntegrationActionFeedback | null>(null);
  const pollActive = useRef(false);
  const ticketAttempted = useRef(false);
  const roleSelectionSessionId = useRef("");
  const physicalModeDefaulted = useRef(false);
  const safetyConfirmationSessionId = useRef(selectedSessionId);

  const updateSafetyConfirmation = useCallback((confirmed: boolean) => {
    setSafetyConfirmed(confirmed);
    saveFlightSafetyConfirmation(confirmed);
  }, []);

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
  const requiresPositionSafetyConfirmation =
    requiresArmingForStart &&
    requiresSpatialSafetyConfirmation(selectedSession?.roleBindings ?? []);
  const canManageSessions = hasPermission(principal, "fabric.sessions.manage");
  const canAssignRoles = hasPermission(principal, "fabric.roles.assign");
  const canSubmitCommands = hasPermission(principal, "fabric.commands.submit");
  const canReadMedia = hasPermission(principal, "fabric.media.read");
  const canPairMedia = hasPermission(principal, "fabric.media.manage");
  const canAnalyzeVision = hasPermission(principal, "fabric.vision.analyze");
  const canReadInstallation = hasPermission(
    principal,
    "fabric.installation.read",
  );
  const canConnectDevices = hasPermission(
    principal,
    "fabric.discovery.connect",
  );
  const connectableIntegrations = useMemo(
    () =>
      discovery?.integrations.filter((integration) =>
        canRunFabricDiscoveryConnection(integration),
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
  const allAircraftGrounded =
    groundedConnections.length === 0 || aircraftGroundedConfirmed;
  const discoveryConnectionsEnabled =
    canConnectDevices && discovery?.physicalActuationEnabled === true;
  const rememberedRequiresGroundedConfirmation =
    rememberedConnections?.connections.some(
      (connection) => connection.requiresGroundedConfirmation,
    ) === true;
  const showAircraftGroundedConfirmation =
    groundedConnections.length > 0 || rememberedRequiresGroundedConfirmation;
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
  const preferredSmartPlugSession = useMemo(
    () =>
      preferredSmartPlugControlSession(
        sessions,
        smartPlugNodes.map((node) => node.nodeId),
      ),
    [sessions, smartPlugNodes],
  );
  const spheroNodes = useMemo(
    () => availableNodes.filter(isSpheroNode),
    [availableNodes],
  );
  const preferredSpheroSession = useMemo(
    () =>
      preferredSpheroControlSession(
        sessions,
        spheroNodes.map((node) => node.nodeId),
      ),
    [sessions, spheroNodes],
  );
  const controlledSmartPlugNodes = useMemo(
    () => smartPlugNodes.slice(0, 2),
    [smartPlugNodes],
  );
  const smartPlugControlSession =
    preferredSmartPlugSession !== undefined &&
    sessionCoversNodes(
      preferredSmartPlugSession,
      controlledSmartPlugNodes,
      (role) => isSmartPlugRole(role),
    )
      ? preferredSmartPlugSession
      : undefined;
  const controlledSpheroNodes = useMemo(
    () => spheroNodes.slice(0, 8),
    [spheroNodes],
  );
  const spheroControlSession =
    preferredSpheroSession !== undefined &&
    sessionCoversNodes(preferredSpheroSession, controlledSpheroNodes)
      ? preferredSpheroSession
      : undefined;
  const telloNodes = useMemo(
    () => availableNodes.filter(isTelloNode),
    [availableNodes],
  );
  const controlledTelloNodes = useMemo(
    () => telloNodes.slice(0, 8),
    [telloNodes],
  );
  const preferredTelloSession = useMemo(
    () =>
      preferredTelloControlSession(
        sessions,
        controlledTelloNodes.map((node) => node.nodeId),
      ),
    [sessions, controlledTelloNodes],
  );
  const telloControlSession =
    preferredTelloSession !== undefined &&
    sessionCoversNodes(
      preferredTelloSession,
      controlledTelloNodes,
      isSafetyDroneRole,
    )
      ? preferredTelloSession
      : undefined;
  const assignedDrones = useMemo(
    () =>
      plannedControlAssignments(
        controlledTelloNodes,
        telloControlSession,
        (index) => `safety_drone_${index + 1}`,
        isSafetyDroneRole,
      ),
    [controlledTelloNodes, telloControlSession?.roleBindings],
  );
  const assignedWonderRobots = useMemo(
    () =>
      (selectedSession?.roleBindings ?? []).flatMap((binding) => {
        const node = availableNodes.find(
          (candidate) =>
            candidate.nodeId === binding.nodeId && isWonderNode(candidate),
        );
        return node === undefined ? [] : [{ role: binding.role, node }];
      }),
    [availableNodes, selectedSession?.roleBindings],
  );
  const assignedSpheroRobots = useMemo(
    () =>
      plannedControlAssignments(
        controlledSpheroNodes,
        spheroControlSession,
        (index) => `robot_sensor_${index + 1}`,
      ),
    [controlledSpheroNodes, spheroControlSession?.roleBindings],
  );
  const synchronizedMotionSession = sessions.find(
    (session) => session.sessionId === synchronizedMotionSessionId,
  );
  const synchronizedInputNodes = useMemo(() => {
    const assignedNodeIds = new Set(
      synchronizedMotionSession?.roleBindings.map(
        (binding) => binding.nodeId,
      ) ?? [],
    );
    return availableNodes.filter((node) => assignedNodeIds.has(node.nodeId));
  }, [availableNodes, synchronizedMotionSession?.roleBindings]);
  const synchronizedInputs = useMemo(
    () => synchronizedInputKinds(synchronizedInputNodes),
    [synchronizedInputNodes],
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
  const fleetSequenceControllerNodes = useMemo(
    () => availableNodes.filter(isFleetSequenceControllerNode),
    [availableNodes],
  );
  const fleetControlSession = useMemo(
    () =>
      preferredFleetSequenceControlSession(
        sessions,
        fleetSequenceControllerNodes.map((node) => node.nodeId),
      ),
    [fleetSequenceControllerNodes, sessions],
  );
  const fleetSequenceBinding = fleetControlSession?.roleBindings.find(
    (binding) => binding.role === "fleet_sequence_controller",
  );
  const fleetSequenceController = fleetSequenceControllerNodes.find(
    (node) =>
      node.nodeId === fleetSequenceBinding?.nodeId &&
      isFleetSequenceControllerNode(node),
  );
  const fleetSequenceInputNodes = useMemo(
    () =>
      assignedFleetSequenceInputNodes(
        availableNodes,
        fleetControlSession?.roleBindings ?? [],
      ),
    [availableNodes, fleetControlSession?.roleBindings],
  );
  const fleetSequenceStatus = useMemo(
    () =>
      latestFleetSequenceStatus(fleetEvents, fleetSequenceController?.nodeId),
    [fleetEvents, fleetSequenceController?.nodeId],
  );
  const assignedSmartPlugs = useMemo(
    () =>
      plannedControlAssignments(
        controlledSmartPlugNodes,
        smartPlugControlSession,
        (index) =>
          index === 0 ? "classroom_plug" : `classroom_plug_${index + 1}`,
        isSmartPlugRole,
      ).map(({ role, node }) => ({
        role,
        node,
        state:
          latestSmartPlugState(events, node.nodeId) ??
          smartPlugStateFromHealth(node),
      })),
    [controlledSmartPlugNodes, events, smartPlugControlSession?.roleBindings],
  );
  const selectedSmartPlug = assignedSmartPlugs[0]?.node;
  const sensorReadings = useMemo(() => latestSensorReadings(events), [events]);
  const canTurnSmartPlugOff =
    canSubmitCommands && busy === null && selectedSmartPlug !== undefined;
  const canPrepareSmartPlugControls =
    canManageSessions &&
    (smartPlugControlSession !== undefined || canAssignRoles);
  const canTurnSmartPlugOn =
    canTurnSmartPlugOff &&
    (canPrepareSmartPlugControls ||
      (smartPlugControlSession?.state === "active" &&
        (smartPlugControlSession.mode !== "physical" ||
          smartPlugControlSession.armed === true)));
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
        const rememberedPromise = client
          .listRememberedConnections()
          .catch((caught: unknown) => {
            if (caught instanceof FabricApiError && caught.status === 404)
              return null;
            throw caught;
          });
        const installationPromise = canReadInstallation
          ? client.getInstallationInfo().catch((caught: unknown) => {
              if (caught instanceof FabricApiError && caught.status === 404)
                return null;
              throw caught;
            })
          : Promise.resolve(null);
        const [
          nextNodes,
          nextDiscovery,
          nextCourses,
          nextSessions,
          nextMediaSources,
          nextRememberedConnections,
          nextInstallation,
        ] = await Promise.all([
          client.listNodes(),
          client.getDiscovery(),
          client.listCoursePacks(),
          client.listSessions(),
          canReadMedia ? client.listMediaSources() : Promise.resolve([]),
          rememberedPromise,
          installationPromise,
        ]);
        setNodes(nextNodes);
        setDiscovery(nextDiscovery);
        setCoursePacks(nextCourses);
        setSessions(nextSessions);
        setMediaSources(nextMediaSources);
        setRememberedConnections(nextRememberedConnections);
        setInstallation(nextInstallation);
        const nextFleetControllerIds = nextNodes
          .filter(
            (node) =>
              isAvailableFabricNode(node) &&
              isFleetSequenceControllerNode(node),
          )
          .map((node) => node.nodeId);
        const nextFleetSession = preferredFleetSequenceControlSession(
          nextSessions,
          nextFleetControllerIds,
        );
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
        if (nextFleetSession === undefined) {
          setFleetEvents([]);
        } else {
          try {
            setFleetEvents(await client.listEvents(nextFleetSession.sessionId));
          } catch (caught) {
            if (!(caught instanceof FabricApiError && caught.status === 403))
              throw caught;
          }
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
    [
      canReadInstallation,
      canReadMedia,
      client,
      principal,
      selectedSessionId,
      t,
    ],
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
      roleSelectionSessionId.current = "";
      setRoleSelections({});
      return;
    }
    const sameSession =
      roleSelectionSessionId.current === selectedSession.sessionId;
    roleSelectionSessionId.current = selectedSession.sessionId;
    const requirements = (selectedCourse?.roles ?? []).map((requirement) => ({
      role: requirement.role,
      optional: requirement.optional,
      candidateNodeIds: compatibleNodes(
        nodes,
        selectedSession,
        requirement,
      ).map((node) => node.nodeId),
    }));
    setRoleSelections((current) =>
      reconciledRoleSelections(
        current,
        sameSession,
        selectedSession.roleBindings,
        requirements,
      ),
    );
  }, [nodes, selectedCourse, selectedSession]);

  useEffect(() => {
    if (safetyConfirmationSessionId.current === selectedSessionId) return;
    safetyConfirmationSessionId.current = selectedSessionId;
    setSafetyConfirmed(false);
    clearFlightSafetyConfirmation();
  }, [selectedSessionId]);

  useEffect(() => {
    if (!safetyConfirmed) setIncludeTelloInSynchronizedMotion(false);
  }, [safetyConfirmed]);

  useEffect(() => {
    if (
      synchronizedMotionEnabled &&
      synchronizedMotionSession !== undefined &&
      (synchronizedMotionSession.state !== "active" ||
        synchronizedMotionSession.armed !== true)
    ) {
      setSynchronizedMotionEnabled(false);
      setIncludeTelloInSynchronizedMotion(false);
      setSynchronizedMotionSessionId("");
    }
  }, [synchronizedMotionEnabled, synchronizedMotionSession]);

  useEffect(() => {
    if (synchronizedMotionSessionId !== "") return;
    const active = sessions
      .filter(
        (session) =>
          session.coursePackId === "synchronized-motor-control" &&
          session.state === "active" &&
          session.armed === true,
      )
      .sort(
        (left, right) =>
          (Date.parse(right.updatedAt) || 0) -
          (Date.parse(left.updatedAt) || 0),
      )[0];
    if (active === undefined) return;
    setSynchronizedMotionSessionId(active.sessionId);
    setSynchronizedMotionEnabled(true);
  }, [sessions, synchronizedMotionSessionId]);

  useEffect(() => {
    if (
      !physicalModeDefaulted.current &&
      selectedSessionId === "" &&
      discovery?.physicalActuationEnabled === true
    ) {
      physicalModeDefaulted.current = true;
      setSessionMode("physical");
    }
  }, [discovery?.physicalActuationEnabled, selectedSessionId]);

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
    clearAircraftGroundedConfirmation();
    clearFlightSafetyConfirmation();
    setPrincipal(null);
    setNodes([]);
    setDiscovery(null);
    setRememberedConnections(null);
    setInstallation(null);
    setCoursePacks([]);
    setSessions([]);
    setSessionStartPolicy(null);
    setEvents([]);
    setFleetEvents([]);
    setMediaSources([]);
    setMediaPairing(null);
    setLifecycle([]);
    setAudit([]);
    setSafetyConfirmed(false);
    setAircraftGroundedConfirmed(false);
    setSynchronizedMotionEnabled(false);
    setIncludeTelloInSynchronizedMotion(false);
    setSynchronizedMotionSessionId("");
    physicalModeDefaulted.current = false;
    setNotice(t("notice.signedOut"));
  };

  const downloadInstallation = () =>
    runAction("busy.downloadingInstaller", async () => {
      const artifact = selectWindowsInstallationArtifact(installation);
      if (artifact === undefined) {
        throw new Error(t("installation.unavailableBody"));
      }
      const downloaded = await client.downloadInstallationArtifact(
        artifact.artifactId,
      );
      try {
        if (
          downloaded.sha256 !== undefined &&
          downloaded.sha256 !== artifact.sha256
        ) {
          throw new Error("response checksum mismatch");
        }
        await verifyInstallationArtifact(downloaded.blob, artifact.sha256);
      } catch {
        throw new Error(t("installation.checksumFailed"));
      }
      saveBlobAsFile(downloaded.blob, artifact.fileName);
      setNotice(t("notice.installerDownloaded"));
    });

  const downloadSiteTemplate = () =>
    runAction("busy.downloadingSiteTemplate", async () => {
      saveTextAsFile(
        createSiteTemplate(siteId, roomId),
        "cit-site-template.json",
        "application/json",
      );
      setNotice(
        t("notice.siteTemplateDownloaded", { site: siteId, room: roomId }),
      );
    });

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
      const defaults = automaticRoleAssignments(
        prepared.roleBindings,
        coursePack.roles.map((requirement) => ({
          role: requirement.role,
          optional: requirement.optional,
          candidateNodeIds: compatibleNodes(nodes, prepared, requirement).map(
            (node) => node.nodeId,
          ),
        })),
      );
      for (const [role, nodeId] of Object.entries(defaults)) {
        if (
          prepared.roleBindings.some(
            (binding) => binding.role === role && binding.nodeId === nodeId,
          )
        ) {
          continue;
        }
        prepared = await client.assignRole(prepared.sessionId, role, nodeId);
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

  const ensureSmartPlugControlSession = async () => {
    if (controlledSmartPlugNodes.length === 0) {
      throw new Error(t("error.noSmartPlugs"));
    }
    if (smartPlugControlSession !== undefined) return smartPlugControlSession;
    if (!canManageSessions || !canAssignRoles) {
      throw new Error(t("error.smartPlugSetupPermission"));
    }
    const coursePack = coursePacks.find(
      (candidate) => candidate.coursePackId === "smart-plug-control",
    );
    if (coursePack === undefined) {
      throw new Error(t("error.smartPlugCourse"));
    }
    let prepared = await client.createSession({
      coursePackId: coursePack.coursePackId,
      coursePackVersion: coursePack.version,
      siteId,
      roomId,
      mode: "physical",
    });
    for (const [index, node] of controlledSmartPlugNodes.entries()) {
      prepared = await client.assignRole(
        prepared.sessionId,
        index === 0 ? "classroom_plug" : "classroom_plug_2",
        node.nodeId,
      );
    }
    setSessions((current) => [...current, prepared]);
    return prepared;
  };

  const ensureSpheroControlSession = async () => {
    if (controlledSpheroNodes.length === 0) {
      throw new Error(t("error.noSpheroRobots"));
    }
    if (spheroControlSession !== undefined) return spheroControlSession;
    if (!canManageSessions || !canAssignRoles) {
      throw new Error(t("error.spheroSetupPermission"));
    }
    const coursePack = coursePacks.find(
      (candidate) => candidate.coursePackId === "device-monitoring",
    );
    if (coursePack === undefined) {
      throw new Error(t("error.spheroCourse"));
    }
    let prepared = await client.createSession({
      coursePackId: coursePack.coursePackId,
      coursePackVersion: coursePack.version,
      siteId,
      roomId,
      mode: "physical",
    });
    for (const [index, node] of controlledSpheroNodes.entries()) {
      prepared = await client.assignRole(
        prepared.sessionId,
        `robot_sensor_${index + 1}`,
        node.nodeId,
      );
    }
    setSessions((current) => [...current, prepared]);
    return prepared;
  };

  const ensureTelloControlSession = async () => {
    if (controlledTelloNodes.length === 0) {
      throw new Error(t("error.noTelloDrones"));
    }
    if (telloControlSession !== undefined) return telloControlSession;
    if (!canManageSessions || !canAssignRoles) {
      throw new Error(t("error.telloSetupPermission"));
    }
    const coursePack = coursePacks.find(
      (candidate) => candidate.coursePackId === "device-monitoring",
    );
    if (coursePack === undefined) {
      throw new Error(t("error.telloCourse"));
    }
    let prepared = await client.createSession({
      coursePackId: coursePack.coursePackId,
      coursePackVersion: coursePack.version,
      siteId,
      roomId,
      mode: "physical",
    });
    for (const [index, node] of controlledTelloNodes.entries()) {
      prepared = await client.assignRole(
        prepared.sessionId,
        `safety_drone_${index + 1}`,
        node.nodeId,
      );
    }
    setSessions((current) => [...current, prepared]);
    return prepared;
  };

  const createSynchronizedMotionSession = async () => {
    if (controlledSpheroNodes.length === 0) {
      throw new Error(t("error.noSynchronizedMotors"));
    }
    if (!canManageSessions || !canAssignRoles) {
      throw new Error(t("error.spheroSetupPermission"));
    }
    const coursePack = coursePacks.find(
      (candidate) => candidate.coursePackId === "synchronized-motor-control",
    );
    if (coursePack === undefined) {
      throw new Error(t("error.spheroCourse"));
    }
    const firstTarget = controlledSpheroNodes[0];
    if (firstTarget === undefined) {
      throw new Error(t("error.noSynchronizedMotors"));
    }
    let prepared = await client.createSession({
      coursePackId: coursePack.coursePackId,
      coursePackVersion: coursePack.version,
      siteId: firstTarget.siteId,
      roomId: firstTarget.roomId,
      mode: "physical",
    });
    for (const [index, node] of controlledSpheroNodes.entries()) {
      prepared = await client.assignRole(
        prepared.sessionId,
        `ground_output_${index + 1}`,
        node.nodeId,
      );
    }
    const fleetController = fleetSequenceControllerNodes.find(
      (node) =>
        node.siteId === prepared.siteId && node.roomId === prepared.roomId,
    );
    if (fleetController !== undefined) {
      prepared = await client.assignRole(
        prepared.sessionId,
        "fleet_sequence_controller",
        fleetController.nodeId,
      );
    }
    setSessions((current) => [...current, prepared]);
    setSynchronizedMotionSessionId(prepared.sessionId);
    return prepared;
  };

  const attachSynchronizedInputs = async (session: InteractionSession) => {
    let prepared = session;
    if (prepared.state === "active") {
      prepared = await client.sessionAction(prepared.sessionId, "pause");
    }
    if (prepared.mode === "physical" && prepared.armed !== true) {
      prepared = await client.sessionAction(prepared.sessionId, "arm");
    }

    const errors: unknown[] = [];
    const hasWearableProjection = availableNodes.some(
      (node) => node.pluginId === "cit.agent-mesh-bridge",
    );
    if (hasWearableProjection) {
      try {
        await client.runDiscoveryAction(
          "cit.glasses-device-control.connect",
          false,
          prepared.sessionId,
        );
      } catch (caught) {
        errors.push(caught);
      }
    }

    const hasMindWave = availableNodes.some(
      (node) => node.metadata.model === "mindwave-mobile2",
    );
    if (hasMindWave) {
      try {
        await client.runDiscoveryAction(
          "cit.synchronized-mindwave.connect",
          false,
          prepared.sessionId,
        );
      } catch (caught) {
        errors.push(caught);
      }
    }

    const latest = (await client.listSessions()).find(
      (candidate) => candidate.sessionId === prepared.sessionId,
    );
    if (latest !== undefined) prepared = latest;
    if (prepared.state !== "active") {
      prepared = await client.sessionAction(prepared.sessionId, "start");
    }
    setSessions((current) => replaceSession(current, prepared));
    return { session: prepared, errors };
  };

  const setSynchronizedMotion = (enabled: boolean) =>
    runAction(
      enabled ? "busy.syncPreparing" : "busy.syncDisabling",
      async () => {
        if (enabled) {
          const created = await createSynchronizedMotionSession();
          await attachSynchronizedInputs(created);
          setSynchronizedMotionEnabled(true);
          setNotice(t("sync.ready", { count: controlledSpheroNodes.length }));
          return;
        }

        const session = synchronizedMotionSession;
        if (
          session !== undefined &&
          !["stopped", "emergency_stopped", "failed"].includes(session.state)
        ) {
          if (session.state === "active") {
            const correlationId = crypto.randomUUID();
            const groundBindings = session.roleBindings.filter((binding) =>
              /^ground_output_[1-8]$/.test(binding.role),
            );
            await Promise.allSettled(
              groundBindings.map((binding, index) =>
                client.submitCommand({
                  messageId: crypto.randomUUID(),
                  schemaVersion: "1.0",
                  messageType: "command.requested",
                  action: SPHERO_STOP_CAPABILITY,
                  target: { role: binding.role },
                  sessionId: session.sessionId,
                  parameters: {},
                  priority: "instructor_override",
                  idempotencyKey: `console-sync:disable:${index}:${correlationId}`,
                  requestedAt: new Date().toISOString(),
                  ttlMs: 1_000,
                  safetyProfile: session.safetyProfile,
                  correlationId,
                }),
              ),
            );
          }
          const stopped = await client.sessionAction(session.sessionId, "stop");
          setSessions((current) => replaceSession(current, stopped));
        }
        setSynchronizedMotionEnabled(false);
        setIncludeTelloInSynchronizedMotion(false);
        setSynchronizedMotionSessionId("");
        setNotice(t("sync.disabled"));
      },
    );

  const connectSynchronizedInputs = () =>
    runAction("busy.syncWearables", async () => {
      if (
        !synchronizedMotionEnabled ||
        synchronizedMotionSession === undefined
      ) {
        throw new Error(t("error.noSynchronizedMotors"));
      }
      const hasInput = availableNodes.some(
        (node) =>
          node.pluginId === "cit.agent-mesh-bridge" ||
          node.metadata.model === "mindwave-mobile2",
      );
      if (!hasInput) throw new Error(t("error.noSynchronizedInputs"));
      const attached = await attachSynchronizedInputs(
        synchronizedMotionSession,
      );
      if (attached.errors.length > 0) throw attached.errors[0];
      setNotice(t("sync.ready", { count: controlledSpheroNodes.length }));
    });

  const sendSynchronizedMotion = (direction: SynchronizedMotionDirection) =>
    runAction("busy.syncCommand", async () => {
      if (
        !synchronizedMotionEnabled ||
        synchronizedMotionSession === undefined
      ) {
        throw new Error(t("error.noSynchronizedMotors"));
      }
      let groundSession = synchronizedMotionSession;
      if (direction !== "stop") {
        groundSession = await prepareDirectControlSession(groundSession);
      }
      const groundRobots = controlledSpheroNodes.flatMap((node) => {
        const binding = groundSession.roleBindings.find(
          (candidate) =>
            candidate.nodeId === node.nodeId &&
            /^ground_output_[1-8]$/.test(candidate.role),
        );
        return binding === undefined ? [] : [{ role: binding.role, node }];
      });

      let flightSession: InteractionSession | undefined;
      let drones: typeof assignedDrones = [];
      if (
        includeTelloInSynchronizedMotion &&
        safetyConfirmed &&
        direction !== "stop" &&
        controlledTelloNodes.length > 0
      ) {
        flightSession = await ensureTelloControlSession();
        flightSession = await prepareDirectControlSession(flightSession);
        drones = plannedControlAssignments(
          controlledTelloNodes,
          flightSession,
          (index) => `safety_drone_${index + 1}`,
          isSafetyDroneRole,
        );
      }

      const commands = synchronizedMotionCommands({
        direction,
        groundRobots,
        drones,
        includeTello: includeTelloInSynchronizedMotion,
        flightConfirmed: safetyConfirmed,
      });
      if (commands.length === 0) {
        throw new Error(t("error.noSynchronizedMotors"));
      }
      const correlationId = crypto.randomUUID();
      const results = await Promise.allSettled(
        commands.map((command, index) => {
          const session =
            command.kind === "flight" ? flightSession : groundSession;
          if (session === undefined) {
            return Promise.reject(new Error("Missing bounded control session"));
          }
          return client.submitCommand({
            messageId: crypto.randomUUID(),
            schemaVersion: "1.0",
            messageType: "command.requested",
            action: command.action,
            target: { role: command.role },
            sessionId: session.sessionId,
            parameters: command.parameters,
            priority: "instructor_override",
            idempotencyKey: `console-sync:${direction}:${index}:${correlationId}`,
            requestedAt: new Date().toISOString(),
            ttlMs: command.kind === "flight" ? 10_000 : 2_000,
            safetyProfile: session.safetyProfile,
            correlationId,
          });
        }),
      );
      const succeeded = results.filter(
        (result) =>
          result.status === "fulfilled" &&
          result.value.lifecycle.at(-1)?.stage === "SUCCEEDED",
      ).length;
      if (succeeded !== commands.length) {
        throw new Error(
          t("error.syncPartial", {
            failed: commands.length - succeeded,
            count: commands.length,
          }),
        );
      }
      setNotice(
        t("sync.sent", {
          direction: t(`sync.${direction}` as "sync.forward"),
          count: succeeded,
        }),
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
      if (action === "disarm" || action === "stop") {
        updateSafetyConfirmation(false);
      }
      setNotice(
        t("notice.lessonStatus", {
          status: fabricSessionState(updated, t),
        }),
      );
    });

  const prepareDirectControlSession = async (
    session: InteractionSession,
  ): Promise<InteractionSession> => {
    let updated = session;
    for (const action of directControlSessionActions(session)) {
      updated = await client.sessionAction(updated.sessionId, action);
      setSessions((current) => replaceSession(current, updated));
    }
    if (
      updated.state !== "active" ||
      (updated.mode === "physical" && updated.armed !== true)
    ) {
      throw new Error(t("error.directControlSessionNotReady"));
    }
    return updated;
  };

  const startSelectedSession = () =>
    runAction("busy.changingSession", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.selectSession"));
      if (
        requiresPositionSafetyConfirmation &&
        !safetyConfirmed &&
        selectedSession.armed !== true
      ) {
        throw new Error(t("error.safetyConfirmation"));
      }
      let updated = selectedSession;
      if (
        updated.mode === "physical" &&
        updated.armed !== true &&
        requiresArmingForStart
      ) {
        updated = await client.sessionAction(updated.sessionId, "arm");
        setSessions((current) => replaceSession(current, updated));
      }
      updated = await client.sessionAction(updated.sessionId, "start");
      setSessions((current) => replaceSession(current, updated));
      setNotice(
        t("notice.lessonStatus", {
          status: fabricSessionState(updated, t),
        }),
      );
    });

  const stopAll = () =>
    runAction("busy.emergencyStop", async () => {
      updateSafetyConfirmation(false);
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

  const scanIntegration = (integration: FabricIntegrationDiscovery) =>
    runAction(
      "busy.scanningIntegration",
      async () => {
        const report = await client.scanDevices();
        setDiscovery(report);
        const refreshed = report.integrations.find(
          (candidate) => candidate.integrationId === integration.integrationId,
        );
        setNotice(
          t("notice.integrationScanned", {
            name: integration.displayName,
            status: discoveryStatus(refreshed?.status ?? "not_found", t).label,
          }),
        );
      },
      { name: integration.displayName },
    );

  const reconnectRememberedDevices = useCallback(
    async (confirmGrounded: boolean): Promise<boolean> => {
      if (busy !== null || principal === null) return false;
      setBusy({ key: "busy.connectingRemembered" });
      setError(null);
      try {
        const result = await client.reconnectRememberedDevices(confirmGrounded);
        const [nextNodes, nextSessions, nextRememberedConnections] =
          await Promise.all([
            client.listNodes(),
            client.listSessions(),
            client.listRememberedConnections(),
          ]);
        setDiscovery(result.report);
        setNodes(nextNodes);
        setSessions(nextSessions);
        setRememberedConnections(nextRememberedConnections);
        setNotice(
          t("notice.rememberedConnected", {
            connected: result.connectedCount,
            already: result.alreadyConnectedCount,
            skipped: result.skippedCount,
          }),
        );
        const failures = result.outcomes.filter(
          (outcome) => outcome.status === "failed",
        );
        if (failures.length > 0) {
          setError(
            t("notice.someAttention", {
              details: failures
                .map((outcome) => `${outcome.actionId}: ${outcome.message}`)
                .join(" "),
            }),
          );
        }
        return true;
      } catch (caught) {
        setError(describeFabricError(caught, t));
        return false;
      } finally {
        setBusy(null);
      }
    },
    [busy, client, principal, t],
  );

  const connectDiscovered = (integration: FabricIntegrationDiscovery) => {
    const name = localizeFabricIntegration(locale, integration, t).displayName;
    setIntegrationActionFeedback({
      integrationId: integration.integrationId,
      tone: "pending",
      message: `${t("busy.connectingDevice", { name })}…`,
    });
    return runAction(
      "busy.connectingDevice",
      async () => {
        try {
          if (integration.actionId === undefined) {
            throw new Error(t("error.setupFirst"));
          }
          const confirmed = aircraftGroundedConfirmed;
          if (integration.requiresGroundedConfirmation && !confirmed) {
            throw new Error(t("error.grounded"));
          }
          const result = await client.runDiscoveryAction(
            integration.actionId,
            confirmed,
          );
          const [nextNodes, nextSessions] = await Promise.all([
            client.listNodes(),
            client.listSessions(),
          ]);
          const successMessage = t("notice.integrationConnected", { name });
          setDiscovery(result.report);
          setNodes(nextNodes);
          setSessions(nextSessions);
          setNotice(successMessage);
          setIntegrationActionFeedback({
            integrationId: integration.integrationId,
            tone: "success",
            message: successMessage,
          });
        } catch (caught) {
          setIntegrationActionFeedback({
            integrationId: integration.integrationId,
            tone: "error",
            message: describeFabricError(caught, t),
          });
          throw caught;
        }
      },
      { name },
    );
  };

  const connectGlassesControlInputs = () =>
    runAction("busy.connectingGlassesControl", async () => {
      if (
        selectedSession === undefined ||
        selectedSession.coursePackId !== "glasses-device-control"
      ) {
        throw new Error(t("error.glassesControlSession"));
      }
      if (selectedSession.mode !== "physical") {
        throw new Error(t("error.glassesControlPhysical"));
      }
      const result = await client.runDiscoveryAction(
        "cit.glasses-device-control.connect",
        false,
        selectedSession.sessionId,
      );
      const [nextNodes, nextSessions] = await Promise.all([
        client.listNodes(),
        client.listSessions(),
      ]);
      setDiscovery(result.report);
      setNodes(nextNodes);
      setSessions(nextSessions);
      setNotice(t("notice.glassesControlConnected"));
    });

  const commissionMatterPlug = (setupCode: string) =>
    runAction("busy.addingMatter", async () => {
      const result = await client.commissionMatterPlug(setupCode);
      setDiscovery(result.report);
      setNotice(t("notice.matterAdded"));
    });

  const configureMatterWifi = (ssid: string, password: string) =>
    runAction("busy.configuringMatterWifi", async () => {
      const result = await client.configureMatterWifi(ssid, password);
      setDiscovery(result.report);
      setNotice(t("notice.matterWifiConfigured"));
    });

  const connectLegoHub = (configuration: LegoConnectionConfiguration) =>
    runAction("busy.connectingLego", async () => {
      const result = await client.connectLegoHub(configuration);
      setDiscovery(result.report);
      setNotice(t("notice.legoConnected"));
    });

  const connectWonderWorkshop = (robots: WonderRobotSelection[]) =>
    runAction("busy.connectingWonder", async () => {
      const result = await client.connectWonderWorkshop(robots);
      setDiscovery(result.report);
      const [nextNodes, nextSessions] = await Promise.all([
        client.listNodes(),
        client.listSessions(),
      ]);
      setNodes(nextNodes);
      setSessions(nextSessions);
      const connectedIds = new Set(
        result.report.integrations.find(
          (integration) =>
            integration.integrationId === "wonder-workshop-dash-dot",
        )?.connectedNodeIds ?? [],
      );
      const monitoringSession = [...nextSessions]
        .reverse()
        .find((session) =>
          session.roleBindings.some((binding) =>
            connectedIds.has(binding.nodeId),
          ),
        );
      if (monitoringSession !== undefined) {
        setSelectedSessionId(monitoringSession.sessionId);
      }
      setNotice(t("notice.wonderConnected", { count: robots.length }));
    });

  const connectSpheroBolts = (robots: SpheroBoltSelection[]) =>
    runAction("busy.connectingSphero", async () => {
      const result = await client.connectSpheroBolts(robots);
      setDiscovery(result.report);
      const [nextNodes, nextSessions] = await Promise.all([
        client.listNodes(),
        client.listSessions(),
      ]);
      setNodes(nextNodes);
      setSessions(nextSessions);
      const connectedIds = new Set(
        result.report.integrations.find(
          (integration) => integration.integrationId === "sphero-bolt",
        )?.connectedNodeIds ?? [],
      );
      const monitoringSession = [...nextSessions]
        .reverse()
        .find((session) =>
          session.roleBindings.some((binding) =>
            connectedIds.has(binding.nodeId),
          ),
        );
      if (monitoringSession !== undefined) {
        setSelectedSessionId(monitoringSession.sessionId);
      }
      setNotice(t("notice.spheroConnected", { count: robots.length }));
    });

  const connectSpheroOllies = (robots: SpheroOllieSelection[]) =>
    runAction("busy.connectingOllie", async () => {
      const result = await client.connectSpheroOllies(robots);
      setDiscovery(result.report);
      const [nextNodes, nextSessions] = await Promise.all([
        client.listNodes(),
        client.listSessions(),
      ]);
      setNodes(nextNodes);
      setSessions(nextSessions);
      const connectedIds = new Set(
        result.report.integrations.find(
          (integration) => integration.integrationId === "sphero-ollie",
        )?.connectedNodeIds ?? [],
      );
      const monitoringSession = [...nextSessions]
        .reverse()
        .find((session) =>
          session.roleBindings.some((binding) =>
            connectedIds.has(binding.nodeId),
          ),
        );
      if (monitoringSession !== undefined) {
        setSelectedSessionId(monitoringSession.sessionId);
      }
      setNotice(t("notice.ollieConnected", { count: robots.length }));
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
      const [nextNodes, nextSessions] = await Promise.all([
        client.listNodes(),
        client.listSessions(),
      ]);
      setNodes(nextNodes);
      setSessions(nextSessions);

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

  const setSmartPlugPower = (role: string, on: boolean) =>
    runAction("busy.smartPlug", async () => {
      let controlSession = await ensureSmartPlugControlSession();
      const binding = controlSession.roleBindings.find(
        (candidate) => candidate.role === role,
      );
      if (
        !isSmartPlugRole(role) ||
        binding === undefined ||
        !smartPlugNodes.some((node) => node.nodeId === binding.nodeId)
      )
        throw new Error(t("error.assignPlug"));
      if (on) {
        controlSession = await prepareDirectControlSession(controlSession);
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
        action: POWER_SET_CAPABILITY,
        target: { role },
        sessionId: controlSession.sessionId,
        parameters: { on },
        priority,
        idempotencyKey: `console-smart-plug:${role}:${on ? "on" : "off"}:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 2_000,
        safetyProfile: controlSession.safetyProfile,
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

  const sendTelloCommand = (
    role: string,
    action: string,
    parameters: Record<string, unknown>,
    label: string,
  ) =>
    runAction("busy.telloCommand", async () => {
      let controlSession = await ensureTelloControlSession();
      const binding = controlSession.roleBindings.find(
        (candidate) => candidate.role === role,
      );
      if (
        !isSafetyDroneRole(role) ||
        binding === undefined ||
        !telloNodes.some((node) => node.nodeId === binding.nodeId)
      ) {
        throw new Error(t("error.droneUnassigned"));
      }
      const isSafeState =
        action === FLIGHT_LAND_CAPABILITY ||
        action === FLIGHT_EMERGENCY_STOP_CAPABILITY;
      if (!isSafeState) {
        controlSession = await prepareDirectControlSession(controlSession);
      }
      const correlationId = crypto.randomUUID();
      const emergency = action === FLIGHT_EMERGENCY_STOP_CAPABILITY;
      if (emergency) updateSafetyConfirmation(false);
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action,
        target: { role },
        sessionId: controlSession.sessionId,
        parameters,
        priority: emergency ? "emergency_stop" : "instructor_override",
        idempotencyKey: `console-tello:${action}:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: action === FLIGHT_LAND_CAPABILITY ? 5_000 : 10_000,
        safetyProfile: controlSession.safetyProfile,
        correlationId,
      });
      setNotice(commandResultNotice(label, result.lifecycle.at(-1)?.stage, t));
    });

  const sendWonderCommand = (
    role: string,
    action: string,
    parameters: Record<string, number>,
    label: string,
  ) =>
    runAction("busy.wonderCommand", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.monitoringSession"));
      if (
        !selectedSession.roleBindings.some((binding) => binding.role === role)
      )
        throw new Error(t("error.wonderUnassigned"));
      const controlSession =
        action === WONDER_STOP_CAPABILITY
          ? selectedSession
          : await prepareDirectControlSession(selectedSession);
      const correlationId = crypto.randomUUID();
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action,
        target: { role },
        sessionId: controlSession.sessionId,
        parameters,
        priority: "instructor_override",
        idempotencyKey: `console-wonder:${role}:${action}:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: action === "mobility.ground.stop" ? 1_000 : 2_000,
        safetyProfile: controlSession.safetyProfile,
        correlationId,
      });
      setNotice(commandResultNotice(label, result.lifecycle.at(-1)?.stage, t));
    });

  const sendSpheroCommand = (
    role: string,
    action: string,
    parameters: Record<string, number>,
    label: string,
  ) =>
    runAction("busy.spheroCommand", async () => {
      let controlSession = await ensureSpheroControlSession();
      if (!controlSession.roleBindings.some((binding) => binding.role === role))
        throw new Error(t("error.spheroUnassigned"));
      if (action !== SPHERO_STOP_CAPABILITY) {
        controlSession = await prepareDirectControlSession(controlSession);
      }
      const correlationId = crypto.randomUUID();
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action,
        target: { role },
        sessionId: controlSession.sessionId,
        parameters,
        priority: "instructor_override",
        idempotencyKey: `console-sphero:${role}:${action}:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: action === "mobility.ground.stop" ? 1_000 : 2_000,
        safetyProfile: controlSession.safetyProfile,
        correlationId,
      });
      setNotice(commandResultNotice(label, result.lifecycle.at(-1)?.stage, t));
    });

  const armBrainDemo = (settings: BrainDemoSettings) =>
    runAction("busy.brainArm", async () => {
      if (selectedSession === undefined)
        throw new Error(t("error.monitoringSession"));
      if (brainDemoBinding === undefined || brainDemoController === undefined)
        throw new Error(t("error.brainController"));
      const controlSession = await prepareDirectControlSession(selectedSession);
      const correlationId = crypto.randomUUID();
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: BRAIN_DEMO_ARM_CAPABILITY,
        target: { role: "brain_flight_demo" },
        sessionId: controlSession.sessionId,
        parameters: { ...settings },
        priority: "instructor_override",
        idempotencyKey: `console-brain-demo:arm:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 5_000,
        safetyProfile: controlSession.safetyProfile,
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
      if (fleetControlSession === undefined)
        throw new Error(t("error.fleetLesson"));
      if (
        fleetSequenceBinding === undefined ||
        fleetSequenceController === undefined
      )
        throw new Error(t("error.fleetController"));
      const controlSession =
        await prepareDirectControlSession(fleetControlSession);
      const correlationId = crypto.randomUUID();
      const result = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: FLEET_SEQUENCE_ARM_CAPABILITY,
        target: { role: "fleet_sequence_controller" },
        sessionId: controlSession.sessionId,
        parameters: { ...settings },
        priority: "instructor_override",
        idempotencyKey: `console-fleet-sequence:arm:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 5_000,
        safetyProfile: controlSession.safetyProfile,
        correlationId,
      });
      setNotice(
        commandResultNotice(t("fleet.arm"), result.lifecycle.at(-1)?.stage, t),
      );
    });

  const startFleetSequence = () =>
    runAction("busy.fleetStart", async () => {
      if (fleetControlSession === undefined)
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
        sessionId: fleetControlSession.sessionId,
        parameters: {},
        priority: "instructor_override",
        idempotencyKey: `console-fleet-sequence:start:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 2_000,
        safetyProfile: fleetControlSession.safetyProfile,
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

  const launchFleetSequence = (settings: FleetSequenceSettings) =>
    runAction("busy.fleetStart", async () => {
      if (fleetControlSession === undefined)
        throw new Error(t("error.fleetLesson"));
      if (
        fleetSequenceBinding === undefined ||
        fleetSequenceController === undefined
      )
        throw new Error(t("error.fleetController"));
      const controlSession =
        await prepareDirectControlSession(fleetControlSession);
      const armCorrelationId = crypto.randomUUID();
      const armResult = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: FLEET_SEQUENCE_ARM_CAPABILITY,
        target: { role: "fleet_sequence_controller" },
        sessionId: controlSession.sessionId,
        parameters: { ...settings },
        priority: "instructor_override",
        idempotencyKey: `console-fleet-sequence:arm-and-start:${armCorrelationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 5_000,
        safetyProfile: controlSession.safetyProfile,
        correlationId: armCorrelationId,
      });
      const armStage = (await awaitFabricCommandTerminal(client, armResult))
        .stage;
      if (armStage !== "SUCCEEDED") {
        throw new Error(commandResultNotice(t("fleet.arm"), armStage, t));
      }
      const startCorrelationId = crypto.randomUUID();
      const startResult = await client.submitCommand({
        messageId: crypto.randomUUID(),
        schemaVersion: "1.0",
        messageType: "command.requested",
        action: FLEET_SEQUENCE_START_CAPABILITY,
        target: { role: "fleet_sequence_controller" },
        sessionId: controlSession.sessionId,
        parameters: {},
        priority: "instructor_override",
        idempotencyKey: `console-fleet-sequence:start:${startCorrelationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 2_000,
        safetyProfile: controlSession.safetyProfile,
        correlationId: startCorrelationId,
      });
      setNotice(
        commandResultNotice(
          t("fleet.takeoffOneByOne"),
          startResult.lifecycle.at(-1)?.stage,
          t,
        ),
      );
    });

  const stopFleetSequence = () =>
    runAction("busy.fleetStop", async () => {
      if (fleetControlSession === undefined)
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
        sessionId: fleetControlSession.sessionId,
        parameters: {},
        priority: "instructor_override",
        idempotencyKey: `console-fleet-sequence:stop:${correlationId}`,
        requestedAt: new Date().toISOString(),
        ttlMs: 5_000,
        safetyProfile: fleetControlSession.safetyProfile,
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
  const localizedDiscoveryIntegrations = (discovery?.integrations ?? []).map(
    (integration) => localizeFabricIntegration(locale, integration, t),
  );
  const discoveryGroups = groupFabricIntegrationsByReadiness(
    localizedDiscoveryIntegrations,
  );
  const discoveryTierPresentation = {
    connected: {
      marker: "✓",
      title: t("discovery.tier.connected.title"),
      empty: t("discovery.tier.connected.empty"),
      count: connectedFabricDeviceCount(discoveryGroups.connected),
    },
    available: {
      marker: "+",
      title: t("discovery.tier.available.title"),
      empty: t("discovery.tier.available.empty"),
      count: discoveryGroups.available.length,
    },
    unavailable: {
      marker: "!",
      title: t("discovery.tier.unavailable.title"),
      empty: t("discovery.tier.unavailable.empty"),
      count: discoveryGroups.unavailable.length,
    },
  } as const;
  const courseRoleGroups = groupFabricCourseRolesByIo(
    selectedSession === undefined || selectedCourse === undefined
      ? []
      : visibleRoleRequirements(
          selectedCourse.roles,
          selectedSession.roleBindings,
          selectedSession.state !== "active",
        ),
  );

  const inlineControlsForIntegration = (
    integration: FabricIntegrationDiscovery,
    connectedNodes: IntegrationNode[],
  ): ReactNode => {
    const connectedNodeIds = new Set(connectedNodes.map((node) => node.nodeId));
    switch (integration.integrationId) {
      case "matter-smart-plugs":
        return (
          <FabricSmartPlugPanel
            plugs={assignedSmartPlugs.filter(({ node }) =>
              connectedNodeIds.has(node.nodeId),
            )}
            sessionState={smartPlugControlSession?.state ?? ""}
            sessionMode={smartPlugControlSession?.mode}
            sessionArmed={smartPlugControlSession?.armed === true}
            busy={busy !== null}
            canSubmit={canSubmitCommands}
            canManageSession={
              canManageSessions &&
              (smartPlugControlSession !== undefined || canAssignRoles)
            }
            requiredRolesReady={assignedSmartPlugs.length > 0}
            onPower={(role, on) => void setSmartPlugPower(role, on)}
            t={t}
          />
        );
      case "sphero-bolt":
      case "sphero-ollie":
        return (
          <FabricSpheroPanel
            robots={assignedSpheroRobots.filter(({ node }) =>
              connectedNodeIds.has(node.nodeId),
            )}
            variant={
              integration.integrationId === "sphero-ollie" ? "ollie" : "bolt"
            }
            sessionState={spheroControlSession?.state ?? ""}
            sessionArmed={spheroControlSession?.armed === true}
            busy={busy !== null}
            canSubmit={canSubmitCommands}
            canManageSession={
              canManageSessions &&
              (spheroControlSession !== undefined || canAssignRoles)
            }
            onCommand={(role, action, parameters, label) =>
              void sendSpheroCommand(role, action, parameters, label)
            }
            t={t}
          />
        );
      case "wonder-workshop-dash-dot":
        return (
          <FabricWonderWorkshopPanel
            robots={assignedWonderRobots.filter(({ node }) =>
              connectedNodeIds.has(node.nodeId),
            )}
            sessionState={selectedSession?.state ?? ""}
            sessionArmed={selectedSession?.armed === true}
            busy={busy !== null}
            canSubmit={canSubmitCommands}
            canManageSession={canManageSessions}
            onCommand={(role, action, parameters, label) =>
              void sendWonderCommand(role, action, parameters, label)
            }
            t={t}
          />
        );
      case "tello-drones":
        return (
          <>
            <FabricDronePanel
              drones={assignedDrones.filter(({ node }) =>
                connectedNodeIds.has(node.nodeId),
              )}
              sessionState={telloControlSession?.state ?? ""}
              sessionArmed={telloControlSession?.armed === true}
              busy={busy !== null}
              canSubmit={canSubmitCommands}
              canManageSession={
                canManageSessions &&
                (telloControlSession !== undefined || canAssignRoles)
              }
              safetyConfirmed={safetyConfirmed}
              onSafetyConfirmedChange={updateSafetyConfirmation}
              onCommand={(role, action, parameters, label) =>
                void sendTelloCommand(role, action, parameters, label)
              }
              t={t}
            />
            {fleetSequenceController !== undefined &&
              fleetControlSession !== undefined && (
                <FabricFleetSequencePanel
                  controllerName={fleetSequenceController.displayName}
                  simulated={fleetSequenceController.simulated}
                  {...(fleetSequenceStatus === undefined
                    ? {}
                    : { status: fleetSequenceStatus })}
                  inputNodes={fleetSequenceInputNodes}
                  sessionState={fleetControlSession.state}
                  sessionArmed={fleetControlSession.armed === true}
                  busy={busy !== null}
                  canSubmit={canSubmitCommands}
                  canManageSession={canManageSessions}
                  safetyConfirmed={safetyConfirmed}
                  onSafetyConfirmedChange={updateSafetyConfirmation}
                  onArm={(settings) => void armFleetSequence(settings)}
                  onLaunch={(settings) => void launchFleetSequence(settings)}
                  onStart={() => void startFleetSequence()}
                  onStop={() => void stopFleetSequence()}
                  locale={locale}
                  t={t}
                />
              )}
          </>
        );
      case "leap-motion":
        return (
          <FabricLeapPanel
            client={client}
            sessionId={selectedSession?.sessionId}
            nodes={connectedNodes}
            locale={locale}
            t={t}
          />
        );
      default:
        return undefined;
    }
  };

  const renderDiscoveryCards = (
    integrations: FabricIntegrationDiscovery[],
    emptyMessage: string,
  ) => (
    <div className="fabric-discovery-grid">
      {integrations.map((integration) => {
        const connectedNodes = integration.connectedNodeIds.flatMap(
          (nodeId) => {
            const node = availableNodes.find(
              (candidate) => candidate.nodeId === nodeId,
            );
            return node === undefined ? [] : [node];
          },
        );
        return (
          <FabricDiscoveryCard
            key={integration.integrationId}
            integration={integration}
            connectedNodes={connectedNodes}
            readings={sensorReadings}
            inlineControls={inlineControlsForIntegration(
              integration,
              connectedNodes,
            )}
            locale={locale}
            t={t}
            busy={busy}
            {...(integrationActionFeedback?.integrationId ===
            integration.integrationId
              ? { actionFeedback: integrationActionFeedback }
              : {})}
            canConnect={discoveryConnectionsEnabled}
            groundedConfirmed={
              !integration.requiresGroundedConfirmation ||
              aircraftGroundedConfirmed
            }
            onScan={() => void scanIntegration(integration)}
            onConnect={() => void connectDiscovered(integration)}
            onCopySetup={() => void copySetupCommand(integration)}
            onMatterCommission={commissionMatterPlug}
            onMatterWifiConfigure={configureMatterWifi}
            onLegoConnect={(configuration) =>
              void connectLegoHub(configuration)
            }
            onWonderConnect={(robots) => void connectWonderWorkshop(robots)}
            onSpheroConnect={(robots) => void connectSpheroBolts(robots)}
            onSpheroOllieConnect={(robots) => void connectSpheroOllies(robots)}
          />
        );
      })}
      {integrations.length === 0 && (
        <p className="fabric-empty fabric-tier-empty">{emptyMessage}</p>
      )}
    </div>
  );

  return (
    <div className="fabric-console">
      <header className="fabric-header">
        <div>
          <p className="eyebrow">{t("header.eyebrow")}</p>
          <h1>{t("header.title")}</h1>
        </div>
        <FabricLanguageSwitch locale={locale} onChange={setLocale} t={t} />
        <a
          className="fabric-install-link"
          href="#install-another-pc"
          onClick={() => {
            const installation = document.getElementById("install-another-pc");
            if (installation instanceof HTMLDetailsElement) {
              installation.open = true;
            }
          }}
        >
          {t("header.installAnother")}
        </a>
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

        <FabricSetupProgress
          ariaLabel={t("guide.progress")}
          currentStep={guide.step}
          steps={[
            { label: t("guide.step.find"), targetId: "device-discovery" },
            { label: t("guide.step.choose"), targetId: "lesson-setup" },
            { label: t("guide.step.assign"), targetId: "device-setup" },
            { label: t("guide.step.safety"), targetId: "lesson-safety" },
            { label: t("guide.step.teach"), targetId: "live-controls" },
          ]}
        />

        <section
          className="fabric-panel fabric-discovery-panel"
          id="device-discovery"
          aria-labelledby="device-discovery-title"
        >
          <div className="fabric-discovery-heading">
            <div>
              <p className="eyebrow">{t("discovery.step")}</p>
              <div className="fabric-title-with-info">
                <h2 id="device-discovery-title">{t("discovery.title")}</h2>
                <FabricInfoDisclosure label={t("common.moreInfo")}>
                  <p>{t("discovery.intro")}</p>
                  <strong>{t("discovery.safeTitle")}</strong>
                  <p>{t("discovery.safeBody")}</p>
                </FabricInfoDisclosure>
              </div>
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

          {showAircraftGroundedConfirmation && (
            <label className="fabric-grounded-confirmation fabric-shared-grounded-confirmation">
              <input
                type="checkbox"
                checked={aircraftGroundedConfirmed}
                onChange={(event) => {
                  const confirmed = event.target.checked;
                  setAircraftGroundedConfirmed(confirmed);
                  saveAircraftGroundedConfirmation(confirmed);
                }}
              />
              <span>{t("discovery.aircraftGrounded")}</span>
            </label>
          )}

          <div className="fabric-discovery-connect-grid">
            {rememberedConnections !== null &&
              rememberedConnections.connections.length > 0 && (
                <div className="fabric-connect-all fabric-remembered-connect">
                  <div>
                    <div className="fabric-compact-title">
                      <strong>
                        {t("discovery.rememberedReady", {
                          count: rememberedConnections.connections.length,
                        })}
                      </strong>
                      <FabricInfoDisclosure label={t("common.moreInfo")}>
                        <p>{t("discovery.rememberedHelp")}</p>
                      </FabricInfoDisclosure>
                    </div>
                  </div>
                  <button
                    className="fabric-primary-action fabric-connect-all-button"
                    type="button"
                    disabled={!discoveryConnectionsEnabled || busy !== null}
                    onClick={() =>
                      void reconnectRememberedDevices(aircraftGroundedConfirmed)
                    }
                  >
                    {busy?.key === "busy.connectingRemembered"
                      ? t("discovery.reconnectingRemembered")
                      : t("discovery.connectRemembered")}
                    <small>
                      {discovery?.physicalActuationEnabled
                        ? t("discovery.rememberedNoScan")
                        : t("discovery.startHost")}
                    </small>
                  </button>
                </div>
              )}

            {connectableIntegrations.length > 0 && (
              <div className="fabric-connect-all">
                <div>
                  <div className="fabric-compact-title">
                    <strong>
                      {t("discovery.connectionsReady", {
                        count: connectableIntegrations.length,
                      })}
                    </strong>
                    <FabricInfoDisclosure label={t("common.moreInfo")}>
                      <p>{t("discovery.connectAllHelp")}</p>
                    </FabricInfoDisclosure>
                  </div>
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
          </div>

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

          <FabricSynchronizedMotionPanel
            enabled={synchronizedMotionEnabled}
            includeTello={includeTelloInSynchronizedMotion}
            groundCount={controlledSpheroNodes.length}
            telloCount={controlledTelloNodes.length}
            availableInputs={synchronizedInputs}
            busy={busy !== null}
            canManage={canManageSessions && canAssignRoles && canSubmitCommands}
            flightConfirmed={safetyConfirmed}
            onEnabledChange={(enabled) => void setSynchronizedMotion(enabled)}
            onIncludeTelloChange={setIncludeTelloInSynchronizedMotion}
            onAssignInputs={() => void connectSynchronizedInputs()}
            onMove={(direction) => void sendSynchronizedMotion(direction)}
            t={t}
          />

          {discovery === null ? (
            <div className="fabric-empty-state fabric-discovery-loading">
              <span aria-hidden="true">…</span>
              <strong>{t("discovery.loading")}</strong>
              <p>{t("discovery.loadingHelp")}</p>
            </div>
          ) : (
            <>
              <div className="fabric-discovery-tiers">
                {(["connected", "available", "unavailable"] as const).map(
                  (kind) => {
                    const tier = discoveryTierPresentation[kind];
                    const openByDefault = fabricDiscoveryTierOpenByDefault(
                      kind,
                      discoveryGroups.connected.length,
                    );
                    return (
                      <details
                        className={`fabric-discovery-tier is-${kind}`}
                        id={`device-tier-${kind}`}
                        aria-labelledby={`device-tier-${kind}-title`}
                        open={openByDefault}
                        key={`${kind}:${String(openByDefault)}`}
                      >
                        <summary className="fabric-discovery-tier-heading">
                          <span aria-hidden="true">{tier.marker}</span>
                          <div>
                            <h3 id={`device-tier-${kind}-title`}>
                              {tier.title}
                            </h3>
                          </div>
                          <strong
                            aria-label={t("discovery.tier.count", {
                              count: tier.count,
                            })}
                          >
                            {tier.count}
                          </strong>
                          <i aria-hidden="true">⌄</i>
                        </summary>
                        {renderDiscoveryCards(
                          discoveryGroups[kind],
                          tier.empty,
                        )}
                      </details>
                    );
                  },
                )}
              </div>
            </>
          )}
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
              <details className="fabric-lesson-overview">
                <summary>
                  <span aria-hidden="true">ⓘ</span>
                  {t("lesson.overview")}
                </summary>
                <p>{fabricCourseText(selectedCourse, t).description}</p>
              </details>
            )}
            {selectedCourse?.coursePackId === "glasses-device-control" && (
              <section className="fabric-glasses-lesson-connect">
                <div>
                  <strong>{t("lesson.glassesControl.title")}</strong>
                  <small>{t("lesson.glassesControl.body")}</small>
                </div>
                <button
                  type="button"
                  disabled={
                    !canConnectDevices ||
                    !canAssignRoles ||
                    busy !== null ||
                    selectedSession === undefined ||
                    selectedSession.mode !== "physical"
                  }
                  onClick={() => void connectGlassesControlInputs()}
                >
                  {t("lesson.glassesControl.connect")}
                </button>
                {(selectedSession === undefined ||
                  selectedSession.mode !== "physical") && (
                  <small>{t("lesson.glassesControl.prepare")}</small>
                )}
              </section>
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
              <div className="fabric-compact-title fabric-safety-status">
                <strong>
                  {selectedSession === undefined
                    ? t("safety.setupFirst")
                    : selectedSession.mode === "simulation"
                      ? t("safety.simulation")
                      : selectedSession.armed
                        ? t("safety.enabled")
                        : t("safety.locked")}
                </strong>
                <FabricInfoDisclosure label={t("common.moreInfo")}>
                  <p>
                    {selectedSession?.mode === "physical"
                      ? requiresPositionSafetyConfirmation
                        ? t("safety.physicalHelp")
                        : t("safety.nonSpatialHelp")
                      : t("safety.simulationHelp")}
                  </p>
                </FabricInfoDisclosure>
              </div>
            </div>
          </div>

          {selectedSession?.mode === "physical" &&
            !selectedSession.armed &&
            requiresPositionSafetyConfirmation && (
              <label className="fabric-safety-confirmation">
                <input
                  type="checkbox"
                  checked={safetyConfirmed}
                  onChange={(event) =>
                    updateSafetyConfirmation(event.target.checked)
                  }
                />
                <span>{t("safety.confirm")}</span>
              </label>
            )}

          <div className="fabric-session-actions">
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
                (requiresPositionSafetyConfirmation &&
                  selectedSession?.armed !== true &&
                  !safetyConfirmed)
              }
              onClick={() => void startSelectedSession()}
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

        <details className="fabric-collapsible-section fabric-lesson-materials">
          <summary>
            <div>
              <strong>{t("lesson.materials")}</strong>
              <span>{t("lesson.materialsSummary")}</span>
            </div>
            <i aria-hidden="true">⌄</i>
          </summary>
          <div className="fabric-collapsible-section-content">
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
                            time: fabricFormatTime(
                              mediaPairing.expiresAt,
                              locale,
                            ),
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
                        onPower={(on) =>
                          void setSmartPlugPower("classroom_plug", on)
                        }
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
              <FabricInfoDisclosure label={t("common.moreInfo")}>
                <p>{t("sensor.intro")}</p>
              </FabricInfoDisclosure>
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
                        <span>
                          {fabricFormatTime(reading.observedAt, locale)}
                        </span>
                      </header>
                      <div className="fabric-sensor-values">
                        {reading.values.map((value) => (
                          <div key={value.label}>
                            <span>{value.label}</span>
                            <strong>{value.value}</strong>
                          </div>
                        ))}
                      </div>
                      <small>
                        {nodeDisplayName(nodes, reading.sourceNodeId)}
                      </small>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        </details>

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
            canManageSession={canManageSessions}
            safetyConfirmed={safetyConfirmed}
            onSafetyConfirmedChange={updateSafetyConfirmation}
            onArm={(settings) => void armBrainDemo(settings)}
            onStop={() => void stopBrainDemo()}
            locale={locale}
            t={t}
          />
        )}

        <details className="fabric-collapsible-section fabric-node-directory">
          <summary>
            <div>
              <strong>{t("nodes.title")}</strong>
              <span>{t("nodes.directorySummary")}</span>
            </div>
            <i aria-hidden="true">⌄</i>
          </summary>
          <div className="fabric-collapsible-section-content">
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
          </div>
        </details>

        <FabricInstallationPanel
          info={installation}
          locale={locale}
          busy={busy !== null}
          canDownload={canReadInstallation}
          onDownload={() => void downloadInstallation()}
          onDownloadSiteTemplate={() => void downloadSiteTemplate()}
          t={t}
        />

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
            {node.displayName} · {node.nodeId} ·{" "}
            {fabricConnectionState(node, t)}
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

export function FabricDiscoveryCard({
  integration,
  connectedNodes,
  readings,
  inlineControls,
  locale,
  t,
  busy,
  actionFeedback,
  canConnect,
  groundedConfirmed,
  onScan,
  onConnect,
  onCopySetup,
  onMatterCommission,
  onMatterWifiConfigure,
  onLegoConnect,
  onWonderConnect,
  onSpheroConnect,
  onSpheroOllieConnect = () => undefined,
}: {
  integration: FabricIntegrationDiscovery;
  connectedNodes: IntegrationNode[];
  readings: FabricSensorReading[];
  inlineControls: ReactNode;
  locale: Locale;
  t: FabricTranslate;
  busy: BusyAction;
  actionFeedback?: FabricDiscoveryActionFeedback;
  canConnect: boolean;
  groundedConfirmed: boolean;
  onScan: () => void;
  onConnect: () => void;
  onCopySetup: () => void;
  onMatterCommission: (setupCode: string) => Promise<boolean>;
  onMatterWifiConfigure: (ssid: string, password: string) => Promise<boolean>;
  onLegoConnect: (configuration: LegoConnectionConfiguration) => void;
  onWonderConnect: (robots: WonderRobotSelection[]) => void;
  onSpheroConnect: (robots: SpheroBoltSelection[]) => void;
  onSpheroOllieConnect?: (robots: SpheroOllieSelection[]) => void;
}) {
  const status = discoveryStatus(integration.status, t);
  const connected = integration.status === "connected";
  const canRunConnection = canRunFabricDiscoveryConnection(integration);
  const isGlassesIntegration =
    integration.integrationId === "even-realities-g2" ||
    integration.integrationId === "meta-rayban";
  const showGenericCandidatePaths =
    integration.candidates.length > 0 &&
    integration.integrationId !== "matter-smart-plugs" &&
    integration.integrationId !== "wonder-workshop-dash-dot" &&
    integration.integrationId !== "sphero-bolt" &&
    integration.integrationId !== "sphero-ollie";
  const candidatePaths = showGenericCandidatePaths ? (
    <FabricCandidateList candidates={integration.candidates} t={t} />
  ) : null;
  const discoveryActions = (
    <FabricDiscoveryActions
      actionLabel={integration.actionLabel}
      busy={busy !== null}
      canConnect={canConnect}
      connected={connected}
      {...(actionFeedback === undefined ? {} : { feedback: actionFeedback })}
      showConnectWhenConnected={connected && canRunConnection}
      groundedConfirmed={groundedConfirmed}
      hasConnectAction={integration.actionId !== undefined}
      hasSetupCommand={integration.setupCommand !== undefined}
      requiresGroundedConfirmation={integration.requiresGroundedConfirmation}
      onConnect={onConnect}
      onCopySetup={onCopySetup}
      onScan={onScan}
      t={t}
    />
  );
  return (
    <article
      id={`integration-${integration.integrationId}`}
      className={`fabric-discovery-card is-${integration.status.replaceAll("_", "-")}${connectedNodes.length > 0 ? " has-live-io" : ""}`}
    >
      <figure
        className={`fabric-device-visual is-${integration.category.replaceAll("_", "-")}`}
        aria-hidden="true"
      >
        {integration.imagePath !== undefined && (
          <img
            src={integration.imagePath}
            alt=""
            width="960"
            height="640"
            loading="lazy"
            decoding="async"
            onError={(event) => {
              event.currentTarget.hidden = true;
            }}
          />
        )}
        <span className="fabric-discovery-icon">
          {DISCOVERY_ICONS[integration.icon ?? ""] ?? "IO"}
        </span>
      </figure>
      <header>
        <div>
          <h3>{integration.displayName}</h3>
          <small>{integration.connectionMethod}</small>
          <span className={`fabric-io-label is-${integration.ioType}`}>
            {fabricIoLabel(integration.ioType, t)}
          </span>
          <FabricInfoDisclosure
            className="fabric-card-info"
            label={t("common.moreInfo")}
          >
            <p>{integration.summary}</p>
          </FabricInfoDisclosure>
        </div>
        <strong className={`fabric-discovery-status is-${status.tone}`}>
          {status.label}
        </strong>
      </header>

      {isGlassesIntegration && (
        <FabricG2Guide t={t}>{discoveryActions}</FabricG2Guide>
      )}

      {connectedNodes.length > 0 && (
        <div className="fabric-inline-device-shell">
          {inlineControls !== undefined && (
            <div className="fabric-inline-device-controls">
              {inlineControls}
            </div>
          )}
          <FabricDeviceIoPanel
            nodes={connectedNodes}
            readings={readings}
            locale={locale}
            t={t}
          />
        </div>
      )}

      {integration.integrationId === "matter-smart-plugs" && (
        <FabricMatterSetup
          candidates={integration.candidates}
          commissioning={busy?.key === "busy.addingMatter"}
          configuringWifi={busy?.key === "busy.configuringMatterWifi"}
          canConnect={canConnect}
          connected={connected}
          onCommission={onMatterCommission}
          onConfigureWifi={onMatterWifiConfigure}
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

      {integration.integrationId === "wonder-workshop-dash-dot" &&
        !connected && (
          <FabricWonderWorkshopSetup
            candidates={integration.candidates}
            busy={busy?.key === "busy.connectingWonder"}
            canConnect={canConnect}
            onConnect={onWonderConnect}
            t={t}
          />
        )}

      {integration.integrationId === "sphero-bolt" && !connected && (
        <FabricSpheroSetup
          candidates={integration.candidates}
          busy={busy?.key === "busy.connectingSphero"}
          canConnect={canConnect}
          onConnect={onSpheroConnect}
          t={t}
        />
      )}

      {integration.integrationId === "sphero-ollie" && !connected && (
        <FabricSpheroSetup
          candidates={integration.candidates}
          variant="ollie"
          busy={busy?.key === "busy.connectingOllie"}
          canConnect={canConnect}
          onConnect={onSpheroOllieConnect}
          t={t}
        />
      )}

      {!connected && candidatePaths !== null && (
        <details className="fabric-candidate-disclosure">
          <summary>
            {t("discovery.detectedPaths", {
              count: integration.candidates.length,
            })}
          </summary>
          {candidatePaths}
        </details>
      )}

      {!isGlassesIntegration && discoveryActions}

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
        {connected && candidatePaths !== null && (
          <section className="fabric-device-connection-paths">
            <strong>
              {t("discovery.detectedPaths", {
                count: integration.candidates.length,
              })}
            </strong>
            {candidatePaths}
          </section>
        )}
        <p>{integration.safetyNote}</p>
      </details>
    </article>
  );
}

function FabricCandidateList({
  candidates,
  t,
}: {
  candidates: FabricDiscoveryCandidate[];
  t: FabricTranslate;
}) {
  return (
    <ul className="fabric-candidate-list">
      {candidates.map((candidate, index) => (
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
            <FabricInfoDisclosure
              className="fabric-candidate-info"
              label={t("common.moreInfo")}
            >
              <p>{candidate.detail}</p>
            </FabricInfoDisclosure>
          </div>
        </li>
      ))}
    </ul>
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
  const [previewRate, setPreviewRate] = useState(0);
  const [frameMessage, setFrameMessage] = useState(() => t("media.waitFrame"));
  const etag = useRef<string | undefined>(undefined);
  const frameUrlRef = useRef<string | null>(null);
  const frameTimes = useRef<number[]>([]);
  const frameAvailable = fabricMediaFrameAvailable(source);

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
    if (!frameAvailable) {
      etag.current = undefined;
      frameTimes.current = [];
      setPreviewRate(0);
      setVisibleSequence(0);
      setFrameMessage(t("media.waitFrame"));
      if (frameUrlRef.current !== null) {
        URL.revokeObjectURL(frameUrlRef.current);
        frameUrlRef.current = null;
        setFrameUrl(null);
      }
      return;
    }
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
          const receivedAt = performance.now();
          frameTimes.current = [...frameTimes.current, receivedAt].filter(
            (value) => receivedAt - value <= 3_000,
          );
          const first = frameTimes.current[0];
          setPreviewRate(
            first === undefined || receivedAt <= first
              ? 0
              : ((frameTimes.current.length - 1) * 1_000) /
                  (receivedAt - first),
          );
        }
      } catch (caught) {
        if (!active) return;
        setFrameMessage(
          caught instanceof FabricApiError && caught.status === 404
            ? t("media.waitFrame")
            : describeFabricError(caught, t),
        );
      } finally {
        if (active)
          timer = window.setTimeout(
            () => void load(),
            source.captureMode === "video" ? 250 : 1_500,
          );
      }
    };
    void load();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [client, frameAvailable, source.captureMode, source.sourceId, t]);

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
        {source.captureMode === "video" && previewRate > 0 && (
          <span>
            {t("media.previewRate", { rate: previewRate.toFixed(1) })}
          </span>
        )}
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
  ring: "R1",
  sphero: "SB",
  wonder: "DD",
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
const isGroundOutputRole = (role: string) => /^ground_output_[1-8]$/.test(role);

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
        : isGroundOutputRole(requirement.role)
          ? "ground_output"
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

export const describeFabricError = (caught: unknown, t: FabricTranslate) => {
  if (caught instanceof FabricApiError) {
    if (
      caught.code === "BRAIN2DEVICES_CONNECTION_REJECTED" &&
      caught.message.includes(
        "Automatic fleet setup found no powered TELLO-* or RMTT-* access point",
      )
    ) {
      return t("error.telloNotVisible");
    }
    if (
      caught.code === "BRAIN2DEVICES_CONNECTION_REJECTED" &&
      caught.message
        .toLocaleLowerCase()
        .includes(
          "local wi-fi routes cannot change while an affected aircraft session may be active",
        )
    ) {
      return t("error.telloSessionActive");
    }
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

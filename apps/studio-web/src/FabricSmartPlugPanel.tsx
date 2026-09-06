import { useEffect, useMemo, useRef, useState } from "react";

import type { IntegrationNode } from "@citxr/protocol";

import {
  fabricConnectionState,
  fabricRoleText,
  type FabricTranslate,
} from "./fabric-i18n.js";
import { isAvailableFabricNode } from "./fabric-node-io.js";
import {
  formatMatterSetupCode,
  readSmartPlugSelection,
  retainKnownSmartPlugSelection,
  saveSmartPlugSelection,
  setupCodeMappingForMatterNode,
  type MatterSetupCodeMapping,
  type SmartPlugState,
} from "./fabric-smart-plug.js";

export interface FabricSmartPlugAssignment {
  role: string;
  node: IntegrationNode;
  state: SmartPlugState | undefined;
}

const UNKNOWN_STATE_MARK = "--";

export function FabricSmartPlugPanel({
  plugs,
  setupCodes = [],
  sessionState,
  sessionMode,
  sessionArmed,
  busy,
  canSubmit,
  canManageSession,
  canRename = false,
  requiredRolesReady,
  onPower,
  onGroupPower,
  onRename,
  t,
}: {
  plugs: FabricSmartPlugAssignment[];
  setupCodes?: readonly MatterSetupCodeMapping[];
  sessionState: string;
  sessionMode: "simulation" | "physical" | undefined;
  sessionArmed: boolean;
  busy: boolean;
  canSubmit: boolean;
  canManageSession: boolean;
  canRename?: boolean;
  requiredRolesReady: boolean;
  onPower: (role: string, on: boolean) => void;
  onGroupPower: (roles: readonly string[], on: boolean) => void;
  onRename?: (matterNodeId: string, name: string) => Promise<boolean>;
  t: FabricTranslate;
}) {
  const [pendingRoles, setPendingRoles] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [selectedNodeIds, setSelectedNodeIds] = useState<ReadonlySet<string>>(
    readSmartPlugSelection,
  );
  const [editingMatterNodeId, setEditingMatterNodeId] = useState<
    string | undefined
  >(undefined);
  const [draftName, setDraftName] = useState("");
  const selectAllRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!busy) setPendingRoles(new Set());
  }, [busy]);

  const availablePlugs = useMemo(
    () => plugs.filter(({ node }) => isAvailableFabricNode(node)),
    [plugs],
  );
  const knownNodeIds = useMemo(
    () => new Set(plugs.map(({ node }) => node.nodeId)),
    [plugs],
  );
  const selectedPlugs = availablePlugs.filter(({ node }) =>
    selectedNodeIds.has(node.nodeId),
  );
  const allAvailableSelected =
    availablePlugs.length > 0 && selectedPlugs.length === availablePlugs.length;

  useEffect(() => {
    if (plugs.length === 0) return;
    setSelectedNodeIds((current) => {
      const next = retainKnownSmartPlugSelection(current, knownNodeIds);
      return next.size === current.size ? current : next;
    });
  }, [knownNodeIds, plugs.length]);

  useEffect(() => {
    saveSmartPlugSelection(selectedNodeIds);
  }, [selectedNodeIds]);

  useEffect(() => {
    if (selectAllRef.current !== null) {
      selectAllRef.current.indeterminate =
        selectedPlugs.length > 0 && !allAvailableSelected;
    }
  }, [allAvailableSelected, selectedPlugs.length]);

  const canUseOrPrepareSession = sessionState !== "" || canManageSession;
  const canTurnOff =
    canSubmit &&
    !busy &&
    plugs.length > 0 &&
    requiredRolesReady &&
    canUseOrPrepareSession;
  const controlsAlreadyReady =
    sessionState === "active" && (sessionMode !== "physical" || sessionArmed);
  const canTurnOn = canTurnOff && (controlsAlreadyReady || canManageSession);

  if (plugs.length === 0) return null;

  return (
    <section
      className="fabric-smart-plug-panel"
      id="smart-plug-controls"
      aria-label={t("plug.title")}
    >
      <div
        className="fabric-plug-group-controls"
        role="group"
        aria-label={t("plug.groupControls")}
      >
        <label className="fabric-plug-select-all">
          <input
            ref={selectAllRef}
            type="checkbox"
            checked={allAvailableSelected}
            disabled={busy || availablePlugs.length === 0}
            onChange={(event) => {
              setSelectedNodeIds(
                event.target.checked
                  ? new Set(availablePlugs.map(({ node }) => node.nodeId))
                  : new Set(),
              );
            }}
          />
          <span>{t("plug.selectAll")}</span>
        </label>
        <span className="fabric-plug-selected-count" aria-live="polite">
          {t("plug.selectedCount", { count: selectedPlugs.length })}
        </span>
        <div className="fabric-plug-group-actions">
          <button
            className="fabric-plug-group-on"
            type="button"
            disabled={selectedPlugs.length === 0 || !canTurnOn}
            onClick={() => {
              const roles = selectedPlugs.map(({ role }) => role);
              setPendingRoles(new Set(roles));
              onGroupPower(roles, true);
            }}
          >
            {t(allAvailableSelected ? "plug.turnOnAll" : "plug.turnOnSelected")}
          </button>
          <button
            className="fabric-plug-group-off"
            type="button"
            disabled={selectedPlugs.length === 0 || !canTurnOff}
            onClick={() => {
              const roles = selectedPlugs.map(({ role }) => role);
              setPendingRoles(new Set(roles));
              onGroupPower(roles, false);
            }}
          >
            {t(
              allAvailableSelected ? "plug.turnOffAll" : "plug.turnOffSelected",
            )}
          </button>
        </div>
      </div>
      <ul className="fabric-smart-plug-list">
        {plugs.map(({ role, node, state }) => {
          const available = isAvailableFabricNode(node);
          const rawMatterNodeId = node.metadata.matterNodeId;
          const matterNodeId =
            typeof rawMatterNodeId === "string" &&
            /^[1-9][0-9]*$/.test(rawMatterNodeId)
              ? rawMatterNodeId
              : undefined;
          const setupCodeMapping = setupCodeMappingForMatterNode(
            node,
            setupCodes,
          );
          const setupCode = setupCodeMapping?.setupCode;
          const turnOn = state?.on === false;
          const action = available
            ? t(turnOn ? "plug.turnOn" : "plug.turnOff")
            : t("plug.controlUnavailable");
          const defaultName = fabricRoleText(role, t).name;
          const name = setupCodeMapping?.name ?? defaultName;
          const canRenamePlug =
            canRename &&
            matterNodeId !== undefined &&
            setupCodeMapping !== undefined &&
            onRename !== undefined;
          const editing = canRenamePlug && editingMatterNodeId === matterNodeId;
          const normalizedDraftName = draftName.trim();
          const draftNameIsValid =
            normalizedDraftName.length > 0 &&
            Array.from(normalizedDraftName).length <= 64 &&
            !Array.from(normalizedDraftName).some((character) => {
              const code = character.charCodeAt(0);
              return code < 32 || code === 127;
            });
          const pending = busy && pendingRoles.has(role);
          const tone = !available
            ? "is-unavailable"
            : state === undefined
              ? "is-unknown"
              : state.on
                ? "is-on"
                : "is-off";
          const unavailableHelp = t("plug.offlineHelp");
          return (
            <li
              className={`fabric-plug-row${available ? "" : " is-unavailable"}`}
              key={`${role}:${node.nodeId}`}
              {...(pending ? { "aria-busy": true } : {})}
            >
              <label className="fabric-plug-select-one">
                <input
                  type="checkbox"
                  checked={available && selectedNodeIds.has(node.nodeId)}
                  aria-label={t("plug.selectOne", { name })}
                  disabled={!available || busy}
                  onChange={(event) => {
                    setSelectedNodeIds((current) => {
                      const next = new Set(current);
                      if (event.target.checked) next.add(node.nodeId);
                      else next.delete(node.nodeId);
                      return next;
                    });
                  }}
                />
              </label>
              <div className="fabric-plug-identity">
                {editing ? (
                  <form
                    className="fabric-plug-rename-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (
                        !draftNameIsValid ||
                        normalizedDraftName === name ||
                        matterNodeId === undefined ||
                        onRename === undefined
                      ) {
                        return;
                      }
                      void onRename(matterNodeId, normalizedDraftName).then(
                        (saved) => {
                          if (saved) {
                            setEditingMatterNodeId(undefined);
                            setDraftName("");
                          }
                        },
                      );
                    }}
                  >
                    <input
                      className="fabric-plug-name-input"
                      type="text"
                      value={draftName}
                      maxLength={64}
                      aria-label={t("plug.nameInput", { name })}
                      autoFocus
                      disabled={busy}
                      onChange={(event) => setDraftName(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key !== "Escape") return;
                        setEditingMatterNodeId(undefined);
                        setDraftName("");
                      }}
                    />
                    <button
                      className="fabric-plug-name-save"
                      type="submit"
                      disabled={
                        busy ||
                        !draftNameIsValid ||
                        normalizedDraftName === name
                      }
                    >
                      {t("plug.renameSave")}
                    </button>
                    <button
                      className="fabric-plug-name-cancel"
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        setEditingMatterNodeId(undefined);
                        setDraftName("");
                      }}
                    >
                      {t("plug.renameCancel")}
                    </button>
                  </form>
                ) : (
                  <span className="fabric-plug-name-line">
                    <span className="fabric-plug-name">{name}</span>
                    {canRenamePlug && (
                      <button
                        className="fabric-plug-rename"
                        type="button"
                        aria-label={t("plug.rename", { name })}
                        title={t("plug.rename", { name })}
                        disabled={busy}
                        onClick={() => {
                          setEditingMatterNodeId(matterNodeId);
                          setDraftName(name);
                        }}
                      >
                        {t("plug.renameAction")}
                      </button>
                    )}
                  </span>
                )}
                {matterNodeId !== undefined && (
                  <small className="fabric-plug-matter-id">
                    {t("plug.matterNodeId", { id: matterNodeId })}
                  </small>
                )}
                {setupCode !== undefined && (
                  <small className="fabric-plug-setup-code">
                    {t("plug.matterSetupCode", {
                      code: formatMatterSetupCode(setupCode),
                    })}
                  </small>
                )}
              </div>
              <span
                className={`fabric-plug-state ${tone}`}
                {...(!available
                  ? { title: unavailableHelp }
                  : state === undefined
                    ? { title: t("plug.stateUnknown") }
                    : {})}
              >
                {!available
                  ? fabricConnectionState(node, t)
                  : state === undefined
                    ? UNKNOWN_STATE_MARK
                    : t(state.on ? "plug.onState" : "plug.offState")}
              </span>
              <button
                className={`fabric-power-toggle ${!available ? "fabric-power-unavailable" : turnOn ? "fabric-power-on" : "fabric-power-off"}${pending ? " is-pending" : ""}`}
                type="button"
                aria-label={`${name}: ${action}`}
                {...(!available ? { title: unavailableHelp } : {})}
                disabled={!available || (turnOn ? !canTurnOn : !canTurnOff)}
                onClick={() => {
                  if (!available) return;
                  setPendingRoles(new Set([role]));
                  onPower(role, turnOn);
                }}
              >
                {action}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

import type { FabricTranslate } from "./fabric-i18n.js";

export type FabricDiscoveryActionFeedback = {
  tone: "pending" | "success" | "error";
  message: string;
};

export function FabricDiscoveryActions({
  actionLabel,
  busy,
  canConnect,
  connected,
  feedback,
  showConnectWhenConnected = false,
  groundedConfirmed,
  hasConnectAction,
  hasSetupCommand,
  requiresGroundedConfirmation,
  onConnect,
  onCopySetup,
  onScan,
  t,
}: {
  actionLabel: string | undefined;
  busy: boolean;
  canConnect: boolean;
  connected: boolean;
  feedback?: FabricDiscoveryActionFeedback;
  showConnectWhenConnected?: boolean;
  groundedConfirmed: boolean;
  hasConnectAction: boolean;
  hasSetupCommand: boolean;
  requiresGroundedConfirmation: boolean;
  onConnect: () => void;
  onCopySetup: () => void;
  onScan: () => void;
  t: FabricTranslate;
}) {
  return (
    <div className="fabric-discovery-action-shell">
      <div className="fabric-discovery-actions">
        <button
          className="fabric-scan-device"
          type="button"
          disabled={busy}
          onClick={onScan}
        >
          {t("discovery.scanThisDevice")}
        </button>
        {hasConnectAction && (!connected || showConnectWhenConnected) && (
          <button
            className="fabric-connect-device"
            type="button"
            disabled={
              !canConnect ||
              busy ||
              (requiresGroundedConfirmation && !groundedConfirmed)
            }
            onClick={onConnect}
          >
            {actionLabel ?? t("discovery.connect")}
          </button>
        )}
        {hasSetupCommand && !connected && (
          <button
            className="fabric-copy-setup"
            type="button"
            disabled={busy}
            onClick={onCopySetup}
          >
            {t("discovery.copySetup")}
          </button>
        )}
      </div>
      {feedback !== undefined && (
        <p
          className={`fabric-discovery-action-feedback is-${feedback.tone}`}
          role={feedback.tone === "error" ? "alert" : "status"}
        >
          {feedback.message}
        </p>
      )}
    </div>
  );
}

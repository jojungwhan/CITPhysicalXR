import {
  useEffect,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  type SyntheticEvent,
} from "react";

import type { FabricDeviceControlKind } from "./fabric-device-controls.js";
import type { FabricTranslate } from "./fabric-i18n.js";

export interface FabricDeviceControlSection {
  kind: FabricDeviceControlKind;
  label: string;
  deviceCount: number;
  content: ReactNode;
}

export function FabricDeviceControlModal({
  open,
  activeKind,
  sections,
  onActiveKindChange,
  onClose,
  t,
}: {
  open: boolean;
  activeKind: FabricDeviceControlKind | undefined;
  sections: readonly FabricDeviceControlSection[];
  onActiveKindChange: (kind: FabricDeviceControlKind) => void;
  onClose: () => void;
  t: FabricTranslate;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const activeSection =
    sections.find((section) => section.kind === activeKind) ?? sections[0];
  const resolvedActiveKind = activeSection?.kind;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  useEffect(() => {
    if (!open || resolvedActiveKind === undefined) return;
    const frame = window.requestAnimationFrame(() =>
      document
        .getElementById(`device-control-tab-${resolvedActiveKind}`)
        ?.scrollIntoView({ block: "nearest", inline: "nearest" }),
    );
    return () => window.cancelAnimationFrame(frame);
  }, [open, resolvedActiveKind]);

  const closeFromDialog = (event: SyntheticEvent<HTMLDialogElement>) => {
    if (event.type === "cancel") event.preventDefault();
    onClose();
  };

  const closeFromBackdrop = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === event.currentTarget) onClose();
  };

  const moveTabFocus = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    let nextIndex: number | undefined;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % sections.length;
    if (event.key === "ArrowLeft")
      nextIndex = (index - 1 + sections.length) % sections.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = sections.length - 1;
    if (nextIndex === undefined) return;

    event.preventDefault();
    const next = sections[nextIndex];
    if (next === undefined) return;
    onActiveKindChange(next.kind);
    window.requestAnimationFrame(() =>
      document.getElementById(`device-control-tab-${next.kind}`)?.focus(),
    );
  };

  if (sections.length === 0) return null;
  return (
    <dialog
      className="fabric-device-control-dialog"
      ref={dialogRef}
      aria-labelledby="device-control-dialog-title"
      aria-describedby="device-control-dialog-description"
      onCancel={closeFromDialog}
      onClose={closeFromDialog}
      onClick={closeFromBackdrop}
    >
      <div className="fabric-device-control-shell">
        <header className="fabric-device-control-header">
          <div>
            <p className="eyebrow">{t("deviceControls.eyebrow")}</p>
            <h2 id="device-control-dialog-title">
              {t("deviceControls.title")}
            </h2>
            <p id="device-control-dialog-description">
              {t("deviceControls.description")}
            </p>
          </div>
          <button
            className="fabric-device-control-close"
            type="button"
            aria-label={t("deviceControls.close")}
            onClick={onClose}
            autoFocus
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>

        <nav
          className="fabric-device-control-tabs"
          role="tablist"
          aria-label={t("deviceControls.categories")}
        >
          {sections.map((section, index) => {
            const selected = section.kind === activeSection?.kind;
            return (
              <button
                id={`device-control-tab-${section.kind}`}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={`device-control-panel-${section.kind}`}
                tabIndex={selected ? 0 : -1}
                className={selected ? "is-current" : undefined}
                key={section.kind}
                onClick={() => onActiveKindChange(section.kind)}
                onKeyDown={(event) => moveTabFocus(event, index)}
              >
                <span>{section.label}</span>
                <strong>{section.deviceCount}</strong>
              </button>
            );
          })}
        </nav>

        {activeSection !== undefined && (
          <div className="fabric-device-control-body">
            <div
              id={`device-control-panel-${activeSection.kind}`}
              role="tabpanel"
              aria-labelledby={`device-control-tab-${activeSection.kind}`}
              tabIndex={0}
            >
              {activeSection.content}
            </div>
          </div>
        )}

        <footer className="fabric-device-control-footer">
          <span>{t("deviceControls.escapeHint")}</span>
          <button type="button" onClick={onClose}>
            {t("deviceControls.done")}
          </button>
        </footer>
      </div>
    </dialog>
  );
}

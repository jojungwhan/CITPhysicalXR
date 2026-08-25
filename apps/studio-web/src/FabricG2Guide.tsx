import type { ReactNode } from "react";

import type { FabricTranslate } from "./fabric-i18n.js";

export function FabricG2Guide({
  children,
  t,
}: {
  children?: ReactNode;
  t: FabricTranslate;
}) {
  return (
    <details className="fabric-g2-guide">
      <summary>
        <strong>{t("g2.guide.title")}</strong>
        <span aria-hidden="true">⌄</span>
      </summary>
      <div className="fabric-g2-guide-content">
        <ul>
          <li>{t("g2.guide.input")}</li>
          <li>{t("g2.guide.output")}</li>
          <li>{t("g2.guide.deviceControl")}</li>
        </ul>
        <p>
          <strong>{t("g2.guide.commandsTitle")}</strong>{" "}
          {t("g2.guide.commands")}
        </p>
        <small>{t("g2.guide.controlSetup")}</small>
        <p>{t("g2.guide.telegram")}</p>
        <small>{t("g2.guide.directMessage")}</small>
        {children !== undefined && (
          <div className="fabric-g2-guide-actions">{children}</div>
        )}
      </div>
    </details>
  );
}

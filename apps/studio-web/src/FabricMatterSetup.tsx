import { useState } from "react";

import type { FabricTranslate } from "./fabric-i18n.js";

export function FabricMatterSetup({
  busy,
  canConnect,
  connected,
  onCommission,
  t,
}: {
  busy: boolean;
  canConnect: boolean;
  connected: boolean;
  onCommission: (setupCode: string) => Promise<boolean>;
  t: FabricTranslate;
}) {
  const [setupCode, setSetupCode] = useState("");

  const commission = async () => {
    const normalized = setupCode.trim();
    if (await onCommission(normalized)) setSetupCode("");
  };

  return (
    <div className="fabric-matter-setup">
      <strong>{connected ? t("matter.addAnother") : t("matter.add")}</strong>
      <p>{t("matter.help")}</p>
      <label>
        {t("matter.code")}
        <input
          type="text"
          value={setupCode}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          placeholder={t("matter.placeholder")}
          onChange={(event) => setSetupCode(event.target.value)}
        />
      </label>
      <button
        className="fabric-connect-device"
        type="button"
        disabled={!canConnect || busy || setupCode.trim().length < 11}
        onClick={() => void commission()}
      >
        {busy
          ? t("matter.adding")
          : connected
            ? t("matter.addAnotherButton")
            : t("matter.addLocally")}
      </button>
      <small>{t("matter.memory")}</small>
    </div>
  );
}

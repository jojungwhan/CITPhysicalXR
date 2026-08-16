import { useState, type FormEvent } from "react";

import { LOCALES, type Locale, type Translate } from "./i18n.js";
import type { Identity, Role, RuntimeClient } from "./runtime-client.js";

/**
 * The gate every other view is behind (ADR-027).
 *
 * The language switch is here as well as in Settings, because a student who
 * cannot read this page cannot reach Settings to fix it.
 */
export function SignIn({
  client,
  t,
  locale,
  onLocale,
  onSignedIn,
  runtimeError,
}: {
  client: RuntimeClient;
  t: Translate;
  locale: Locale;
  onLocale: (locale: Locale) => void;
  onSignedIn: (identity: Identity) => void;
  runtimeError: string | null;
}) {
  const [actorId, setActorId] = useState("");
  const [role, setRole] = useState<Role>("student");
  const [passcode, setPasscode] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      onSignedIn(
        await client.join({
          actorId: actorId.trim(),
          role,
          displayName: actorId.trim(),
          ...(role === "instructor" ? { passcode } : {}),
        }),
      );
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="signin-heading">
      <h2 id="signin-heading">{t("signin.heading")}</h2>
      <p className="muted">{t("signin.explain")}</p>

      <form className="stack" onSubmit={submit}>
        <label>
          <span>{t("signin.name")}</span>
          <input
            value={actorId}
            onChange={(event) => setActorId(event.target.value)}
            autoComplete="off"
            required
            maxLength={128}
          />
        </label>

        <fieldset className="row">
          <legend>{t("signin.role")}</legend>
          {(["student", "instructor"] as const).map((option) => (
            <label key={option} className="choice">
              <input
                type="radio"
                name="role"
                value={option}
                checked={role === option}
                onChange={() => setRole(option)}
              />
              <span>{t(`signin.role.${option}`)}</span>
            </label>
          ))}
        </fieldset>

        {role === "instructor" && (
          <label>
            <span>{t("signin.passcode")}</span>
            <input
              value={passcode}
              onChange={(event) => setPasscode(event.target.value)}
              autoComplete="off"
              maxLength={128}
            />
            <small className="muted">{t("signin.passcodeHint")}</small>
          </label>
        )}

        <div className="row">
          <button type="submit" disabled={busy || actorId.trim() === ""}>
            {t("signin.submit")}
          </button>
          {LOCALES.map((option) => (
            <button
              key={option}
              type="button"
              className={option === locale ? "chip current" : "chip"}
              onClick={() => onLocale(option)}
              aria-pressed={option === locale}
            >
              {option === "en" ? "English" : "한국어"}
            </button>
          ))}
        </div>
      </form>

      {failure !== null && (
        <div className="notice bad" role="alert">
          {failure}
        </div>
      )}
      {failure === null && runtimeError !== null && (
        <div className="notice bad" role="alert">
          {runtimeError}
        </div>
      )}
    </section>
  );
}

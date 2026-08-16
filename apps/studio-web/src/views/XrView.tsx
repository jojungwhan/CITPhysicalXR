import type { Translate } from "../i18n.js";

/**
 * UI 11.1 lists XR in the navigation, and Milestone 5 is what fills it.
 *
 * The tab exists and says so plainly. There is deliberately no simulated
 * headset here: a fake Quest panel would tell an instructor that XR worked on a
 * machine where no headset has ever been paired, and finding that out during a
 * lesson is worse than finding it out here.
 */
export function XrView({ t }: { t: Translate }) {
  return (
    <section aria-labelledby="xr-heading">
      <h2 id="xr-heading">{t("xr.heading")}</h2>
      <div className="notice">{t("xr.notInThisMilestone")}</div>
      <h3>{t("xr.plannedHeading")}</h3>
      <ul className="events">
        <li>{t("xr.plannedPairing")}</li>
        <li>{t("xr.plannedTelemetry")}</li>
        <li>{t("xr.plannedDeadman")}</li>
      </ul>
    </section>
  );
}

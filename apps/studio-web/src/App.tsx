import { foundationStatus } from "./foundation-status.js";

const foundations = [
  ["Protocol", "Version 1 schema with generated TypeScript and Python models"],
  ["Adapters", "In-memory S1, Leap, LEGO, and Quest contract fakes"],
  ["Safety", "Expiry, duplicate, lease, and denial boundaries under test"],
] as const;

export function App() {
  const status = foundationStatus();

  return (
    <main>
      <p className="eyebrow">CIT Physical XR Studio</p>
      <h1>Foundation workspace</h1>
      <p className="lede">
        Milestone {status.milestone} establishes contracts and build gates. This
        scaffold does not run student programs or control physical devices.
      </p>

      <section aria-labelledby="foundation-heading">
        <h2 id="foundation-heading">Verified foundation areas</h2>
        <div className="cards">
          {foundations.map(([title, description]) => (
            <article key={title}>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <aside aria-label="Current limitations">
        <strong>Foundation only</strong>
        <span>
          Physical control disabled · Agent Mesh optional · no Quest build
          claimed
        </span>
      </aside>
    </main>
  );
}

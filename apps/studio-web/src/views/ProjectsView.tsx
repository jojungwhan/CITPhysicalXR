import { useCallback, useEffect, useState } from "react";

import { createProject } from "@citxr/project-format";

import type { Translate } from "../i18n.js";
import type { ProjectSummaryView, RuntimeClient } from "../runtime-client.js";

/**
 * FR-001. Projects that outlive the tab that made them.
 *
 * Until Milestone 6 a project lived in browser memory, so closing the tab and
 * deleting the work were the same act. The list here is what the runtime has on
 * disk; opening one sets it as the project the Program view edits.
 */
export function ProjectsView({
  client,
  t,
  run,
  busy,
}: {
  client: RuntimeClient;
  t: Translate;
  run: (work: () => Promise<void>) => Promise<void>;
  busy: boolean;
}) {
  const [projects, setProjects] = useState<ProjectSummaryView[]>([]);

  const refresh = useCallback(async () => {
    setProjects(await client.projects());
  }, [client]);

  useEffect(() => {
    void run(refresh);
  }, [refresh, run]);

  const create = () =>
    run(async () => {
      const now = new Date().toISOString();
      const project = createProject({
        projectId: crypto.randomUUID(),
        name: `Project ${projects.length + 1}`,
        now,
      });
      await client.saveProject(
        project.projectId,
        project as unknown as Record<string, unknown>,
      );
      await refresh();
    });

  const remove = (projectId: string) =>
    run(async () => {
      if (!window.confirm(t("projects.confirmDelete"))) return;
      await client.deleteProject(projectId);
      await refresh();
    });

  const open = (projectId: string) => {
    window.localStorage.setItem("citxr.openProject", projectId);
    window.location.hash = "#/program";
  };

  return (
    <section aria-labelledby="projects-heading">
      <div className="bar">
        <h2 id="projects-heading">{t("projects.heading")}</h2>
        <div className="row">
          <button
            type="button"
            onClick={() => void run(refresh)}
            disabled={busy}
          >
            {t("action.refresh")}
          </button>
          <button type="button" onClick={create} disabled={busy}>
            {t("projects.new")}
          </button>
        </div>
      </div>

      {projects.length === 0 ? (
        <p className="muted">{t("projects.none")}</p>
      ) : (
        <ul className="events">
          {projects.map((project) => (
            <li key={project.projectId}>
              <strong>{project.name}</strong>
              <span className="pill">{project.authoringMode}</span>
              <span className="muted">
                {t("projects.updated")}{" "}
                {project.updatedAt.slice(0, 16).replace("T", " ")}
              </span>
              <span className="muted">
                {t("projects.owner")} {project.ownerId ?? "—"}
              </span>
              <button type="button" onClick={() => open(project.projectId)}>
                {t("projects.open")}
              </button>
              <button
                type="button"
                onClick={() => remove(project.projectId)}
                disabled={busy}
              >
                {t("projects.delete")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

import type { IntegrationNode } from "@citxr/protocol";

import { selectedDemonstrationNodes } from "./fabric-demonstration.js";
import { fabricConnectionState, type FabricTranslate } from "./fabric-i18n.js";
import { FabricInfoDisclosure } from "./FabricInfoDisclosure.js";

export function FabricDemonstrationSelector({
  nodes,
  selectedNodeIds,
  nodeName = (node) => node.displayName,
  onSelectAll,
  onClear,
  onToggle,
  t,
}: {
  nodes: readonly IntegrationNode[];
  selectedNodeIds: ReadonlySet<string>;
  nodeName?: (node: IntegrationNode) => string;
  onSelectAll: () => void;
  onClear: () => void;
  onToggle: (nodeId: string, selected: boolean) => void;
  t: FabricTranslate;
}) {
  const selectedNodes = selectedDemonstrationNodes(nodes, selectedNodeIds);
  const allSelected = nodes.length > 0 && selectedNodes.length === nodes.length;

  return (
    <section
      className="fabric-panel fabric-demonstration-selector"
      aria-labelledby="demonstration-device-title"
    >
      <header>
        <div>
          <p className="eyebrow">{t("demonstration.eyebrow")}</p>
          <div className="fabric-title-with-info">
            <h2 id="demonstration-device-title">{t("demonstration.title")}</h2>
            <FabricInfoDisclosure label={t("common.moreInfo")}>
              <p>{t("demonstration.help")}</p>
              <p>{t("demonstration.safety")}</p>
            </FabricInfoDisclosure>
          </div>
        </div>
        <strong>
          {t("demonstration.selected", {
            selected: selectedNodes.length,
            count: nodes.length,
          })}
        </strong>
      </header>

      <div className="fabric-demonstration-actions">
        <button type="button" disabled={allSelected} onClick={onSelectAll}>
          {t("demonstration.selectAll")}
        </button>
        <button
          type="button"
          disabled={selectedNodes.length === 0}
          onClick={onClear}
        >
          {t("demonstration.clear")}
        </button>
      </div>

      {nodes.length === 0 ? (
        <p className="fabric-empty">{t("demonstration.none")}</p>
      ) : (
        <div className="fabric-demonstration-devices">
          {nodes.map((node) => {
            const name = nodeName(node);
            const model =
              typeof node.metadata.model === "string"
                ? node.metadata.model
                : node.pluginId;
            return (
              <label key={node.nodeId}>
                <input
                  type="checkbox"
                  checked={selectedNodeIds.has(node.nodeId)}
                  aria-label={t("demonstration.toggle", {
                    device: name,
                  })}
                  onChange={(event) =>
                    onToggle(node.nodeId, event.target.checked)
                  }
                />
                <span>
                  <strong>{name}</strong>
                  <small>
                    {model} · {fabricConnectionState(node, t)}
                  </small>
                </span>
              </label>
            );
          })}
        </div>
      )}
    </section>
  );
}

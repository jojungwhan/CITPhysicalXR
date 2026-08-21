import { loadBridgeConfig } from "./config.js";
import { runBridgeForever } from "./bridge.js";

const controller = new AbortController();
for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.once(signal, () => controller.abort());
}

try {
  const config = loadBridgeConfig();
  await runBridgeForever(config, {
    signal: controller.signal,
    onDiagnostic: (message) =>
      console.error(`[cit-agent-mesh-bridge] ${message}`),
  });
} catch (error) {
  const message =
    error instanceof Error
      ? error.message.slice(0, 500)
      : "Bridge startup failed";
  console.error(`[cit-agent-mesh-bridge] ${message}`);
  process.exitCode = 1;
}

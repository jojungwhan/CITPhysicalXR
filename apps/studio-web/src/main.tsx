import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App.js";
import { registerFabricPwa } from "./pwa.js";
import "./style.css";

void registerFabricPwa().catch(() => {
  // The controls remain a normal same-origin web app when PWA installation is
  // unavailable. Runtime connectivity is reported by the console itself.
});

const root = document.querySelector<HTMLDivElement>("#root");
if (root === null) {
  throw new Error("Studio scaffold is missing its #root element");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

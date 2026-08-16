import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App.js";
import "./style.css";

const root = document.querySelector<HTMLDivElement>("#root");
if (root === null) {
  throw new Error("Studio scaffold is missing its #root element");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

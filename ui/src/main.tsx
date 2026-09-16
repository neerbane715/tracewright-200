import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
// Bundled locally -- no CDN, so the app works air-gapped.
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./tokens.css";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);

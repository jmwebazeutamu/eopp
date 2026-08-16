import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "antd/dist/reset.css";

// Self-hosted rather than fetched from Google Fonts: the brief's users are on
// 3G or worse, and a blocking third-party font request is the worst thing on
// that connection. Weights are the four the handoff loads.
import "@fontsource/archivo/400.css";
import "@fontsource/archivo/500.css";
import "@fontsource/archivo/600.css";
import "@fontsource/archivo/700.css";
import "@fontsource/noto-sans-ethiopic/400.css";
import "@fontsource/noto-sans-ethiopic/500.css";
import "@fontsource/noto-sans-ethiopic/600.css";
import "@fontsource/noto-sans-ethiopic/700.css";

import "./styles/tokens.css";
import "./styles/base.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

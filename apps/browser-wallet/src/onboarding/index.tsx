import React from "react";
import ReactDOM from "react-dom/client";

import { OnboardingApp } from "./routes/Welcome";
import "../popup/styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <OnboardingApp />
  </React.StrictMode>,
);

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { LangRoot } from "./i18n";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LangRoot><App /></LangRoot>
  </StrictMode>,
);

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { httpSource } from "./httpSource";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App source={httpSource} />
  </StrictMode>,
);

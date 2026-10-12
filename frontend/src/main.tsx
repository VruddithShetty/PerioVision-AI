import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "@/app/App";
import "@/styles/index.css";
import "@/store/theme";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

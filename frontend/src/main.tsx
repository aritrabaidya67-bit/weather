import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { PlatformProvider } from "./state/PlatformContext";
import "./index.css";

const stored = window.localStorage.getItem("eip-theme");
if (stored === "light") {
  document.documentElement.classList.remove("dark");
} else if (stored === "dark") {
  document.documentElement.classList.add("dark");
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <PlatformProvider>
        <App />
      </PlatformProvider>
    </BrowserRouter>
  </React.StrictMode>,
);

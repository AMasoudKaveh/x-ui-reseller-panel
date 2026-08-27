import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./dashboard.css";
import "./users.css";
import "./settings.css";
import "./login.css";
import "./admin.css";
import "./admin-settings.css";
import "./theme.css";
import "./persistent-sidebar.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

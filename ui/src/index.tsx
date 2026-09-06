#!/usr/bin/env node
import React from "react";
import { render } from "ink";
import App from "./app.js";

const { unmount, waitUntilExit } = render(React.createElement(App));

// Handle cleanup
process.on("SIGINT", () => {
  unmount();
  process.exit(0);
});

process.on("SIGTERM", () => {
  unmount();
  process.exit(0);
});

waitUntilExit();

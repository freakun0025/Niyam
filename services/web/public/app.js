"use strict";

const VERSION_TIMEOUT_MS = 5000;

function showService(state, message) {
  document.getElementById("service-dot").dataset.state = state;
  document.getElementById("service-status").textContent = message;
}

async function loadVersion() {
  const promptVersion = document.getElementById("prompt-version");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), VERSION_TIMEOUT_MS);

  try {
    const response = await fetch("/version", { cache: "no-store", signal: controller.signal });
    if (!response.ok) {
      throw new Error(`Unexpected status ${response.status}`);
    }
    const version = await response.json();
    promptVersion.textContent = version.prompt_version;
    showService("online", "Service online");
  } catch {
    promptVersion.textContent = "unavailable";
    showService("offline", "Service unavailable");
  } finally {
    clearTimeout(timer);
  }
}

loadVersion();

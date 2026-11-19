/**
 * Project Golu - Browser Extension Background Service Worker
 * Isolates X-Golu-Token from webpage DOM and proxies API calls securely.
 */

const BASE_URL = "http://127.0.0.1:8000";
const WS_URL = "ws://127.0.0.1:8000/ws/browser";

let sessionToken = null;
let websocket = null;

// Initialize session token via local handshake
async function initSessionToken() {
  try {
    const res = await fetch(`${BASE_URL}/api/token`);
    if (res.ok) {
      const data = await res.json();
      sessionToken = data.session_token;
      await chrome.storage.local.set({ goluToken: sessionToken });
      console.log("[Golu Background] Handshake successful. Token secured.");
      connectWebSocket();
    }
  } catch (err) {
    console.warn("[Golu Background] Orchestrator offline during boot:", err.message);
  }
}

// Ensure token is loaded
async function getToken() {
  if (sessionToken) return sessionToken;
  const stored = await chrome.storage.local.get("goluToken");
  if (stored && stored.goluToken) {
    sessionToken = stored.goluToken;
    return sessionToken;
  }
  await initSessionToken();
  return sessionToken;
}

// Persistent WebSocket connection for voice & automation triggers
function connectWebSocket() {
  if (websocket && websocket.readyState === WebSocket.OPEN) return;

  try {
    websocket = new WebSocket(WS_URL);

    websocket.onopen = () => {
      console.log("[Golu Background] WebSocket bridge connected.");
    };

    websocket.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.action === "FILL_CURRENT_FORM") {
          const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
          if (tab && tab.id) {
            chrome.tabs.sendMessage(tab.id, { action: "TRIGGER_BATCH_FILL" });
          }
        }
      } catch (e) {
        console.error("[Golu Background] WS message error:", e);
      }
    };

    websocket.onclose = () => {
      setTimeout(connectWebSocket, 5000);
    };

    websocket.onerror = () => {
      if (websocket) websocket.close();
    };
  } catch (err) {
    console.debug("[Golu Background] WS connection attempt failed.");
  }
}

// Message Router for Content Scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "SUGGEST_FIELD") {
    handleSuggestField(message.payload)
      .then(sendResponse)
      .catch((err) => sendResponse({ error: err.message }));
    return true; // Keep channel open for async response
  }

  if (message.action === "SAVE_MEMORY") {
    handleSaveMemory(message.payload)
      .then(sendResponse)
      .catch((err) => sendResponse({ error: err.message }));
    return true;
  }

  if (message.action === "CHECK_HEALTH") {
    fetch(`${BASE_URL}/api/health`)
      .then((res) => res.json())
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});

async function handleSuggestField(payload) {
  const token = await getToken();
  const res = await fetch(`${BASE_URL}/api/suggest-field`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Golu-Token": token || ""
    },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    throw new Error(`Orchestrator error: ${res.status}`);
  }
  return await res.json();
}

async function handleSaveMemory(payload) {
  const token = await getToken();
  const res = await fetch(`${BASE_URL}/api/save-memory`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Golu-Token": token || ""
    },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    throw new Error(`Save failed: ${res.status}`);
  }
  return await res.json();
}

chrome.runtime.onInstalled.addListener(() => {
  initSessionToken();
});

chrome.runtime.onStartup.addListener(() => {
  initSessionToken();
});

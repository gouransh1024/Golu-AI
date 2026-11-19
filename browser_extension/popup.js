/**
 * Project Golu - Extension Popup Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  const statusDot = document.getElementById("statusDot");
  const vramStatus = document.getElementById("vramStatus");
  const vaultCount = document.getElementById("vaultCount");
  const batchFillBtn = document.getElementById("batchFillBtn");

  // Query orchestrator status
  chrome.runtime.sendMessage({ action: "CHECK_HEALTH" }, (res) => {
    if (chrome.runtime.lastError || !res || !res.ok) {
      statusDot.className = "status-dot offline";
      vramStatus.innerText = "Offline";
      return;
    }

    const data = res.data;
    statusDot.className = "status-dot";
    const usedMb = data.vram?.used_mb || 0;
    vramStatus.innerText = `${usedMb.toFixed(0)} MB`;
    vaultCount.innerText = data.vault_entries || "0";
  });

  // Batch fill action
  batchFillBtn.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id) {
      chrome.tabs.sendMessage(tab.id, { action: "TRIGGER_BATCH_FILL" });
      window.close();
    }
  });
});

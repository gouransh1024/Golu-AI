/**
 * Project Golu - Content Script
 * Non-intrusive DOM autofill assistant, React/Vue event dispatcher, and Deny-List guard.
 */

const BLOCKED_TYPES = new Set(["password", "hidden", "submit", "button", "reset", "file"]);
const SENSITIVE_KEYWORDS = [
  "password", "passwd", "pwd", "otp", "pin", "cvv", "cvc",
  "card_number", "credit_card", "debit_card", "aadhaar", "aadhar", "pan_card", "ssn"
];

let activePill = null;
let currentField = null;
let pendingSuggestion = null;

// ================= DOM Utilities =================

function isElementVisible(el) {
  if (!el || el.offsetParent === null) return false;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity) === 0) {
    return false;
  }
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function isSensitiveField(el) {
  const type = (el.type || "").toLowerCase();
  if (BLOCKED_TYPES.has(type)) return true;

  const identifiers = [
    el.name,
    el.id,
    el.placeholder,
    el.getAttribute("aria-label"),
    el.getAttribute("autocomplete")
  ].filter(Boolean).join(" ").toLowerCase();

  for (const kw of SENSITIVE_KEYWORDS) {
    if (identifiers.includes(kw)) return true;
  }

  // Cross-origin payment iframe check
  try {
    if (window.self !== window.top) {
      const origin = window.location.origin.toLowerCase();
      if (origin.includes("stripe") || origin.includes("razorpay") || origin.includes("paypal")) {
        return true;
      }
    }
  } catch (e) {
    return true;
  }

  return false;
}

function getFieldLabel(el) {
  // Check aria-label or placeholder first
  if (el.getAttribute("aria-label")) return el.getAttribute("aria-label").trim();
  if (el.placeholder) return el.placeholder.trim();

  // Associated <label for="id">
  if (el.id) {
    const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (label && isElementVisible(label)) {
      return label.innerText.trim();
    }
  }

  // Enclosing <label>
  const parentLabel = el.closest("label");
  if (parentLabel && isElementVisible(parentLabel)) {
    const clone = parentLabel.cloneNode(true);
    const inputs = clone.querySelectorAll("input, textarea, select");
    inputs.forEach((i) => i.remove());
    if (clone.innerText.trim()) return clone.innerText.trim();
  }

  // Preceding sibling or nearby header text
  let prev = el.previousElementSibling;
  while (prev) {
    if (["LABEL", "SPAN", "P", "H4", "H5"].includes(prev.tagName) && isElementVisible(prev)) {
      const txt = prev.innerText.trim();
      if (txt && txt.length < 50) return txt;
    }
    prev = prev.previousElementSibling;
  }

  return el.name || el.id || "";
}

// React / Vue / Angular native event dispatcher
function setNativeValue(element, value) {
  const valueSetter = Object.getOwnPropertyDescriptor(element.__proto__, "value")?.set;
  const prototype = Object.getPrototypeOf(element);
  const prototypeValueSetter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;

  if (prototypeValueSetter && valueSetter !== prototypeValueSetter) {
    prototypeValueSetter.call(element, value);
  } else if (valueSetter) {
    valueSetter.call(element, value);
  } else {
    element.value = value;
  }

  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

// ================= Floating Pill UI =================

function removePill() {
  if (activePill && activePill.parentNode) {
    activePill.parentNode.removeChild(activePill);
  }
  activePill = null;
  pendingSuggestion = null;
}

function showPill(targetEl, suggestionData) {
  removePill();
  if (!suggestionData || !suggestionData.suggestion) return;

  const rect = targetEl.getBoundingClientRect();
  const pill = document.createElement("div");
  pill.className = "golu-pill-container";

  const isVault = suggestionData.source === "vault";
  const badgeClass = isVault ? "golu-pill-vault" : "golu-pill-rag";
  const badgeText = isVault ? "⚡ Vault" : "🧠 Golu AI";

  pill.innerHTML = `
    <span class="golu-pill-badge ${badgeClass}">${badgeText}</span>
    <span class="golu-pill-text" title="${suggestionData.suggestion}">${suggestionData.suggestion}</span>
    <span class="golu-pill-kbd">Tab</span>
  `;

  // Position above or below input
  const top = window.scrollY + rect.bottom + 4;
  const left = window.scrollX + rect.left;
  pill.style.top = `${top}px`;
  pill.style.left = `${left}px`;

  pill.addEventListener("mousedown", (e) => {
    e.preventDefault();
    applySuggestion(targetEl, suggestionData.suggestion);
  });

  document.body.appendChild(pill);
  activePill = pill;
  pendingSuggestion = suggestionData.suggestion;
  currentField = targetEl;
}

function applySuggestion(element, value) {
  if (!element || !value) return;
  setNativeValue(element, value);
  element.classList.add("golu-field-highlight");
  setTimeout(() => element.classList.remove("golu-field-highlight"), 2000);
  removePill();
}

// ================= Field Listeners =================

document.addEventListener("focusin", (e) => {
  const el = e.target;
  if (!el || !["INPUT", "TEXTAREA"].includes(el.tagName)) return;
  if (isSensitiveField(el) || !isElementVisible(el)) return;

  const label = getFieldLabel(el);
  const payload = {
    field_name: el.name || el.id || "unnamed_field",
    field_type: (el.type || el.tagName).toLowerCase(),
    field_label: label,
    placeholder: el.placeholder || null,
    maxlength: el.maxLength > 0 ? el.maxLength : null
  };

  chrome.runtime.sendMessage({ action: "SUGGEST_FIELD", payload }, (response) => {
    if (chrome.runtime.lastError || !response || response.error) return;
    if (document.activeElement === el) {
      showPill(el, response);
    }
  });
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Tab" && activePill && currentField && pendingSuggestion) {
    if (document.activeElement === currentField && !currentField.value) {
      e.preventDefault();
      applySuggestion(currentField, pendingSuggestion);
    }
  } else if (e.key === "Escape") {
    removePill();
  }
});

document.addEventListener("focusout", (e) => {
  setTimeout(() => {
    if (!document.activeElement || document.activeElement !== currentField) {
      removePill();
    }
  }, 200);
});

// ================= Batch Full-Form Mode =================

async function handleBatchFill() {
  const inputs = Array.from(document.querySelectorAll("input, textarea")).filter((el) => {
    return isElementVisible(el) && !isSensitiveField(el) && !el.value;
  });

  if (inputs.length === 0) return;

  console.log(`[Golu Content] Batch filling ${inputs.length} detected fields...`);

  for (const el of inputs) {
    const label = getFieldLabel(el);
    const payload = {
      field_name: el.name || el.id || "field",
      field_type: (el.type || el.tagName).toLowerCase(),
      field_label: label,
      placeholder: el.placeholder || null,
      maxlength: el.maxLength > 0 ? el.maxLength : null
    };

    chrome.runtime.sendMessage({ action: "SUGGEST_FIELD", payload }, (res) => {
      if (res && res.suggestion) {
        setNativeValue(el, res.suggestion);
        el.classList.add("golu-field-highlight");
      }
    });
  }
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === "TRIGGER_BATCH_FILL") {
    handleBatchFill();
  }
});

// ================= Active Learning Toast =================

document.addEventListener("change", (e) => {
  const el = e.target;
  if (!el || !["INPUT", "TEXTAREA"].includes(el.tagName)) return;
  if (isSensitiveField(el) || !el.value.trim() || el.value.length < 2) return;

  const label = getFieldLabel(el);
  if (!label || label.length > 40) return;

  showActiveLearningToast(label, el.value.trim());
});

function showActiveLearningToast(label, val) {
  const existing = document.getElementById("golu-active-learning-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "golu-active-learning-toast";
  toast.className = "golu-toast";
  toast.innerHTML = `
    <span>Save <strong>${label}</strong> to Golu's encrypted vault?</span>
    <button class="golu-toast-save">Save</button>
    <button class="golu-toast-dismiss">Dismiss</button>
  `;

  toast.querySelector(".golu-toast-save").onclick = () => {
    chrome.runtime.sendMessage({
      action: "SAVE_MEMORY",
      payload: {
        field_name: label.toLowerCase().replace(/[^a-z0-9]/g, "_"),
        value: val,
        category: "personal",
        save_to_vault: true
      }
    });
    toast.remove();
  };

  toast.querySelector(".golu-toast-dismiss").onclick = () => toast.remove();
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 7000);
}

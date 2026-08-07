const stateKey = "fly_print_state";

export const defaultPaperSize = "A4";
export const defaultOrientation = "portrait";
export const minScalePercent = 50;
export const maxScalePercent = 150;
export const scaleStepPercent = 10;

export function normalizeOrientation(value) {
  const orientation = String(value || "").trim().toLowerCase();
  return orientation === "landscape" || orientation === "横向" ? "landscape" : defaultOrientation;
}

export function orientationFromPaperSize(value) {
  const raw = String(value || "").trim().toLowerCase();
  return raw.includes("(landscape)") || raw.includes("横向")
    ? "landscape"
    : defaultOrientation;
}

export function normalizePaperSize(value, fallback = defaultPaperSize) {
  const raw = String(value || "").trim();
  const base = raw.replace(/\s*[\uFF08(](?:\u6A2A\u5411|landscape)[\uFF09)]\s*$/i, "").trim();
  return base || fallback;
}

export function normalizeScalePercent(value, fallback = 100) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  const stepped = Math.round(parsed / scaleStepPercent) * scaleStepPercent;
  return Math.min(maxScalePercent, Math.max(minScalePercent, stepped));
}

export function createDefaultOptions() {
  return {
    copies: 1,
    duplex: "simplex",
    color_mode: "color",
    paper_size: defaultPaperSize,
    orientation: defaultOrientation,
    scale_percent: 100,
  };
}

function loadState() {
  try {
    const raw = sessionStorage.getItem(stateKey);
    return raw
      ? JSON.parse(raw)
      : {
          options: createDefaultOptions(),
          file: {},
          identity: null,
          pendingPrintRequest: null,
        };
  } catch {
    return {
      options: createDefaultOptions(),
      file: {},
      identity: null,
      pendingPrintRequest: null,
    };
  }
}

export function normalizeOpsContacts(rawContacts) {
  if (!Array.isArray(rawContacts)) return [];
  return rawContacts
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const name = String(item.name || "").trim();
      const phone = String(item.phone || "").trim();
      if (!name || !phone) return null;
      return { name, phone };
    })
    .filter(Boolean);
}

export function normalizeRuntimeSettings(rawSettings) {
  const settings = rawSettings && typeof rawSettings === "object" ? rawSettings : {};
  const copiesMin = Math.max(1, Number.parseInt(settings.copies_min, 10) || 1);
  const parsedMax = Number.parseInt(settings.copies_max, 10) || 3;
  const copiesMax = Math.max(copiesMin, parsedMax);
  const maxFileSizeBytes = Math.max(0, Number.parseInt(settings.max_file_size_bytes, 10) || 0);
  const maxDocumentPages = Math.max(0, Number.parseInt(settings.max_document_pages, 10) || 0);
  const maxListItems = Math.max(0, Number.parseInt(settings.max_list_items, 10) || 0);
  const defaultPaper = String(settings.default_paper_size || defaultPaperSize);
  const defaultScalePercent = normalizeScalePercent(settings.default_scale_percent, 100);
  return {
    copies_min: copiesMin,
    copies_max: copiesMax,
    max_file_size_bytes: maxFileSizeBytes,
    max_document_pages: maxDocumentPages,
    max_list_items: maxListItems,
    default_paper_size: defaultPaper,
    default_scale_percent: defaultScalePercent,
    ops_contacts: normalizeOpsContacts(settings.ops_contacts),
  };
}

export function createDefaultCapabilityState() {
  return {
    duplexSupported: false,
    colorSupported: false,
  };
}

export const state = loadState();
state.identity = state.identity && typeof state.identity === "object" ? state.identity : null;
state.runtimeSettings = normalizeRuntimeSettings(state.runtimeSettings);
state.opsContacts = normalizeOpsContacts(state.opsContacts || state.runtimeSettings?.ops_contacts);
state.capabilityState =
  state.capabilityState && typeof state.capabilityState === "object"
    ? state.capabilityState
    : createDefaultCapabilityState();

export function setOpsContacts(contacts) {
  state.opsContacts = normalizeOpsContacts(contacts);
  return state.opsContacts;
}

export function getCopyLimitState() {
  const normalized = normalizeRuntimeSettings(state.runtimeSettings);
  state.runtimeSettings = normalized;
  return {
    min: normalized.copies_min,
    max: normalized.copies_max,
  };
}

export function normalizeCopies(value) {
  const { min, max } = getCopyLimitState();
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return min;
  return Math.min(max, Math.max(min, parsed));
}

export function ensureStateOptions() {
  const merged = {
    ...createDefaultOptions(),
    ...(state.options && typeof state.options === "object" ? state.options : {}),
  };
  merged.copies = normalizeCopies(merged.copies);
  merged.paper_size = defaultPaperSize;
  merged.orientation = normalizeOrientation(merged.orientation);
  merged.scale_percent = normalizeScalePercent(merged.scale_percent);
  state.options = merged;
}

ensureStateOptions();

export function saveSessionState() {
  sessionStorage.setItem(stateKey, JSON.stringify(state));
}

export function setPendingPrintRequest(request) {
  state.pendingPrintRequest = request || null;
  saveSessionState();
}

export function clearPendingPrintRequest() {
  state.pendingPrintRequest = null;
  saveSessionState();
}

export function currentSessionId() {
  return state.session_id || "";
}

export function setDoneResult(type, message, extra = {}) {
  state.doneResult = {
    type: type || "success",
    message: message || "",
    ts: Date.now(),
    ...(extra && typeof extra === "object" ? extra : {}),
  };
  saveSessionState();
}

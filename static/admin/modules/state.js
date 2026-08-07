export function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function createAdminState() {
  return {
    config: null,
    initialConfig: null,
    activeSection: "cloud",
    saving: false,
    testingCloud: false,
    loading: false,
    printersRefreshing: false,
    managed: [],
    discovered: [],
    defaultPrinterId: "",
    startupEnabled: false,
    startupLoading: false,
    startupSaving: false,
    printersLoadedOnce: false,
    printersInvalidated: false,
    cloudStatus: null,
    lastApplyResult: null,
    pendingActions: new Set(),
    printerTests: {},
    ippProbeUri: "",
    ippProbeResult: null,
    ippProbing: false,
  };
}

export function configModel(state) {
  if (!state.config) {
    return {
      cloud: {},
      settings: {},
      network: {},
      meta: { restart_required_fields: [], masked_fields: [] },
    };
  }
  return state.config;
}

export function buildConfigPayloadFromConfig(cfg) {
  const rawScalePercent = cfg.settings.default_scale_percent;
  const normalizedScalePercent = rawScalePercent === "" || rawScalePercent == null ? 100 : Number(rawScalePercent);
  const rawCopiesMin = cfg.settings.copies_min;
  const rawCopiesMax = cfg.settings.copies_max;
  const normalizedCopiesMin = rawCopiesMin === "" || rawCopiesMin == null ? "" : Number(rawCopiesMin);
  const normalizedCopiesMax = rawCopiesMax === "" || rawCopiesMax == null ? "" : Number(rawCopiesMax);
  const rawMaxFileSizeBytes = cfg.settings.max_file_size_bytes;
  const rawMaxDocumentPages = cfg.settings.max_document_pages;
  const rawMaxListItems = cfg.settings.max_list_items;
  const normalizedMaxFileSizeBytes = rawMaxFileSizeBytes === "" || rawMaxFileSizeBytes == null ? "" : Number(rawMaxFileSizeBytes);
  const normalizedMaxDocumentPages = rawMaxDocumentPages === "" || rawMaxDocumentPages == null ? "" : Number(rawMaxDocumentPages);
  const normalizedMaxListItems = rawMaxListItems === "" || rawMaxListItems == null ? "" : Number(rawMaxListItems);

  return {
    cloud: {
      base_url: cfg.cloud.base_url || "",
      node_name: cfg.cloud.node_name || "",
      location: cfg.cloud.location || "",
      heartbeat_interval: Number(cfg.cloud.heartbeat_interval || 30),
    },
    settings: {
      default_paper_size: cfg.settings.default_paper_size || "",
      default_scale_percent: normalizedScalePercent,
      copies_min: normalizedCopiesMin,
      copies_max: normalizedCopiesMax,
      max_file_size_bytes: normalizedMaxFileSizeBytes,
      max_document_pages: normalizedMaxDocumentPages,
      max_list_items: normalizedMaxListItems,
      libreoffice_path: cfg.settings.libreoffice_path || "",
    },
  };
}

export function buildConfigPayload(state) {
  return buildConfigPayloadFromConfig(configModel(state));
}

export function isDirty(state) {
  if (!state.config || !state.initialConfig) return false;
  return JSON.stringify(state.config) !== JSON.stringify(state.initialConfig);
}

function actionKey(action, value) {
  return `${action}:${value}`;
}

export function isActionPending(state, action, value) {
  return state.pendingActions.has(actionKey(action, value));
}

export function isPrinterActionPending(state, printerId) {
  return ["default", "test", "reregister", "delete", "clear-unconfirmed"]
    .some((action) => isActionPending(state, action, printerId));
}

export function setActionPending(state, action, value, pending) {
  const key = actionKey(action, value);
  if (pending) {
    state.pendingActions.add(key);
  } else {
    state.pendingActions.delete(key);
  }
}

export function printerName(item) {
  return item?.name || item?.printer_name || item?.display_name || "未命名打印机";
}

export function printerAddr(item) {
  if (item?.ipp_uri) return item.ipp_uri;
  const ip = item?.ip || item?.host || item?.address || "-";
  const port = item?.port || item?.tcp_port || "-";
  return `${ip}:${port}`;
}

export function restartRequiredHint(state) {
  const result = state.lastApplyResult;
  return Array.isArray(result?.restart_required) && result.restart_required.length > 0;
}

export function updateField(state, section, key, rawValue, type) {
  if (!state.config) return;
  const next = deepClone(state.config);
  let value = rawValue;
  if (type === "checkbox") {
    value = !!rawValue;
  } else if (type === "number") {
    value = rawValue === "" ? "" : Number(rawValue);
  }
  next[section][key] = value;
  state.config = next;
}

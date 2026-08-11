export const api = {
  qr: "/api/qr_code",
  events: "/api/events",
  printerAvailability: "/api/printer/availability",
  sessionCurrent: "/api/session/current",
  preview: "/api/preview",
  print: "/api/print",
  cleanup: "/api/cleanup",
  prpProviders: "/api/prp/providers",
  prpSelection: "/api/prp/selection",
};

function requestError(json, status) {
  const error = new Error(json?.message || `HTTP ${status}`);
  error.code = json?.error_code || json?.code || "";
  error.status = status;
  return error;
}

export async function getJson(url, options = {}) {
  const res = await fetch(url, { cache: "no-store", ...options });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw requestError(json, res.status);
  return json;
}

export async function postJson(url, data, options = {}) {
  const res = await fetch(url, {
    ...options,
    method: "POST",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    body: JSON.stringify(data || {}),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.success === false) {
    throw requestError(json, res.status);
  }
  return json;
}

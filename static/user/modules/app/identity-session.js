function publicText(value) {
  return String(value || "").trim();
}

export function applyIdentityReady(appState, payload) {
  if (!appState?.session || !payload || typeof payload !== "object") return false;

  const identity = {
    session_id: publicText(payload.session_id || payload.terminal_session_id),
    site_portal_code: publicText(payload.site_portal_code),
    site_portal_display_name: publicText(payload.site_portal_display_name) || publicText(payload.site_portal_code),
    cloud_user_id: publicText(payload.cloud_user_id),
    external_user_id: publicText(payload.external_user_id),
    display_name: publicText(payload.display_name),
  };
  if (!identity.session_id || !identity.site_portal_code || !identity.display_name) return false;

  appState.session.session_id = identity.session_id;
  appState.session.identity = identity;
  appState.sessionPhase = "identity_ready";
  return true;
}

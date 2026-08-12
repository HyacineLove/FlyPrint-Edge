import assert from "node:assert/strict";
import test from "node:test";

import { applyIdentityReady } from "../static/user/modules/app/identity-session.js";

test("Cloud-provided Site Portal display name becomes public Edge identity state", () => {
  const appState = { session: {}, sessionPhase: "idle" };
  const applied = applyIdentityReady(appState, {
    terminal_session_id: "session-1",
    site_portal_code: "official",
    site_portal_display_name: "Official Portal",
    cloud_user_id: "cloud-user-1",
    external_user_id: "external-user-1",
    display_name: "Test User",
  });

  assert.equal(applied, true);
  assert.equal(appState.session.identity.site_portal_display_name, "Official Portal");
  assert.equal(appState.session.identity.display_name, "Test User");
});

test("Edge uses the portal code until an older Cloud supplies a display name", () => {
  const appState = { session: {}, sessionPhase: "idle" };
  assert.equal(applyIdentityReady(appState, {
    terminal_session_id: "session-1",
    site_portal_code: "official",
    cloud_user_id: "cloud-user-1",
    external_user_id: "external-user-1",
    display_name: "Test User",
  }), true);
  assert.equal(appState.session.identity.site_portal_display_name, "official");
});

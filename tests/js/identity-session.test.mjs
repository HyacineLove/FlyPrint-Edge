import assert from "node:assert/strict";
import test from "node:test";

import { applyIdentityReady } from "../../static/user/modules/app/identity-session.js";

test("valid portal identity enters identity_ready without storing credentials", () => {
  const appState = {
    session: { session_id: null, identity: null },
    sessionPhase: "idle",
  };

  const accepted = applyIdentityReady(appState, {
    session_id: "session-1",
    site_portal_code: "official",
    cloud_user_id: "cloud-user-1",
    external_user_id: "external-user-1",
    display_name: "演示用户",
    access_token: "must-not-enter-browser-state",
    cookie: "must-not-enter-browser-state",
    password: "must-not-enter-browser-state",
  });

  assert.equal(accepted, true);
  assert.equal(appState.sessionPhase, "identity_ready");
  assert.equal(appState.session.session_id, "session-1");
  assert.deepEqual(appState.session.identity, {
    session_id: "session-1",
    site_portal_code: "official",
    cloud_user_id: "cloud-user-1",
    external_user_id: "external-user-1",
    display_name: "演示用户",
  });
});

test("identity without a display name is rejected without changing state", () => {
  const appState = {
    session: { session_id: "existing-session", identity: null },
    sessionPhase: "idle",
  };

  const accepted = applyIdentityReady(appState, {
    session_id: "session-1",
    site_portal_code: "official",
    cloud_user_id: "cloud-user-1",
    external_user_id: "external-user-1",
    display_name: " ",
  });

  assert.equal(accepted, false);
  assert.deepEqual(appState, {
    session: { session_id: "existing-session", identity: null },
    sessionPhase: "idle",
  });
});

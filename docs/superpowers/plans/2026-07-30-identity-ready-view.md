# Edge Identity Ready View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Edge user UI display and restore the public Site Portal identity after the backend reaches `identity_ready`.

**Architecture:** A pure frontend state module accepts only the credential-free identity payload. The app controller uses it for both SSE events and session snapshots, then routes to a thin identity-ready view.

**Tech Stack:** Browser ES modules, Node 22 built-in test runner, existing Edge FastAPI static frontend, Python unittest regression suite.

## Global Constraints

- Do not expose or persist `access_token`, cookies, passwords, or PRP credentials in browser state.
- Do not implement file listing, upload, preview, or printing behavior in the identity-ready view.
- Do not add a fallback login or retry path.
- Preserve the existing QR, preview, printing, and done views.

---

### Task 1: Add and route the identity-ready state

**Files:**
- Create: `static/user/modules/app/identity-session.js`
- Create: `static/user/modules/views/identity-view.js`
- Create: `tests/js/identity-session.test.mjs`
- Modify: `static/user/modules/app/app-controller.js`
- Modify: `static/user/modules/shared/runtime.js`
- Modify: `static/user/modules/shared/session-state.js`
- Modify: `static/user/css/app.css`

**Interfaces:**
- Produces: `applyIdentityReady(appState, payload) -> boolean`.
- Consumes: credential-free `portal_session_ready.data` and `/api/session/current` identity fields.
- Produces: `renderIdentityView(state)` and `bindIdentityViewEvents(context)`.

- [ ] **Step 1: Write the failing pure-state tests**

Test that a valid payload changes `sessionPhase` to `identity_ready`, stores only `session_id`, `site_portal_code`, `cloud_user_id`, `external_user_id`, and `display_name`, and rejects an empty display name without changing state.

- [ ] **Step 2: Run the focused test and confirm the module is missing**

```powershell
node --experimental-default-type=module --test tests/js/identity-session.test.mjs
```

Expected: failure because `identity-session.js` does not exist.

- [ ] **Step 3: Implement the minimal identity state module**

`applyIdentityReady` trims the five public fields, requires `session_id` and `display_name`, replaces `appState.session.identity`, sets `appState.session.session_id`, and sets `appState.sessionPhase`.

- [ ] **Step 4: Run the focused test and confirm it passes**

```powershell
node --experimental-default-type=module --test tests/js/identity-session.test.mjs
```

- [ ] **Step 5: Add the thin identity view and controller routing**

Handle `portal_session_ready` by applying the identity and routing to `identity`. Handle `portal_session_error` as a login error. During snapshot restore, apply `identity_ready` before routing. The view displays the user name, login-success message, next-slice notice, and an “结束并刷新二维码” action.

- [ ] **Step 6: Clear public identity with the session**

Set `state.identity = null` in `clearLocalUserSession` and initialize missing saved state to `null`.

- [ ] **Step 7: Run frontend and full Edge regression**

```powershell
node --experimental-default-type=module --test tests/js/identity-session.test.mjs
& '..\..\fly-print-edge\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py'
```

- [ ] **Step 8: Verify the live browser**

Restart Edge, repeat login, confirm the page switches to the identity view, refresh retains the identity view, and the end-session action returns to a new QR.

- [ ] **Step 9: Commit**

```powershell
git add static/user tests/js docs/superpowers/plans/2026-07-30-identity-ready-view.md
git commit -m "fix: show site portal identity on edge"
```

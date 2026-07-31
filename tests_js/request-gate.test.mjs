import assert from "node:assert/strict";
import test from "node:test";

import { createRequestGate } from "../static/user/modules/shared/request-gate.js";

test("request gate allows only one active operation", () => {
  const gate = createRequestGate();
  const first = gate.start();

  assert.ok(first);
  assert.equal(gate.start(), null);
  assert.equal(gate.isCurrent(first), true);
  assert.equal(gate.finish(first), true);
  assert.ok(gate.start());
});

test("request gate cancellation aborts and invalidates the active operation", () => {
  const gate = createRequestGate();
  const request = gate.start();

  gate.cancel();

  assert.equal(request.signal.aborted, true);
  assert.equal(gate.isCurrent(request), false);
  assert.equal(gate.finish(request), false);
  assert.equal(gate.start(), null);
});

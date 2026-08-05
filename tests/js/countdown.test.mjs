import assert from "node:assert/strict";
import test from "node:test";

const timers = [];
globalThis.window = {
  setInterval(callback) {
    timers.push(callback);
    return timers.length - 1;
  },
  clearInterval() {},
};

const { createMainCountdown } = await import("../../static/user/modules/shared/countdown.js");

test("main countdown stops during loading and triggers one action at zero", () => {
  const rendered = [];
  const phases = [];
  let actions = 0;
  const countdown = createMainCountdown({
    render: (value, phase) => {
      rendered.push(value);
      phases.push(phase);
    },
  });
  const tick = timers.at(-1);

  countdown.start(10, () => { actions += 1; });
  tick();
  assert.equal(rendered.at(-1), 9);
  assert.equal(phases.at(-1), "counting");

  countdown.stop("loading");
  assert.equal(rendered.at(-1), "…");
  assert.equal(phases.at(-1), "loading");
  tick();
  assert.equal(rendered.at(-1), "…");
  assert.equal(actions, 0);

  countdown.start(2, () => { actions += 1; });
  tick();
  tick();
  tick();
  assert.equal(rendered.at(-1), 0);
  assert.equal(phases.at(-1), "counting");
  assert.equal(actions, 1);

  countdown.stop();
  assert.equal(rendered.at(-1), "—");
  assert.equal(phases.at(-1), "idle");
  countdown.destroy();
});

/**
 * Single countdown controller for a user page.
 *
 * A page stops it while a request is loading, then starts it with the
 * duration and action appropriate for the settled state.
 */
export function createMainCountdown({ render } = {}) {
  let value = 0;
  let active = false;
  let onExpire = null;
  let timer = null;
  let phase = "idle";

  const draw = () => {
    const visibleValue = phase === "loading" ? "…" : phase === "idle" ? "—" : value;
    render?.(visibleValue, phase);
  };

  const stop = (nextPhase = "idle") => {
    active = false;
    onExpire = null;
    phase = nextPhase === "loading" ? "loading" : "idle";
    draw();
  };

  const start = (seconds, action) => {
    value = Math.max(0, Number(seconds) || 0);
    onExpire = typeof action === "function" ? action : null;
    active = true;
    phase = "counting";
    draw();
  };

  const tick = () => {
    if (!active) return;
    value = Math.max(0, value - 1);
    draw();
    if (value !== 0) return;
    active = false;
    phase = "counting";
    const action = onExpire;
    onExpire = null;
    if (action) void action();
  };

  timer = window.setInterval(tick, 1000);

  return {
    start,
    stop,
    get value() {
      return value;
    },
    destroy() {
      stop();
      if (timer) {
        window.clearInterval(timer);
        timer = null;
      }
    },
  };
}

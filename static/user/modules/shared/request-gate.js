export function createRequestGate() {
  let active = true;
  let busy = false;
  let generation = 0;
  let controller = null;

  function isCurrent(request) {
    return Boolean(
      active &&
      busy &&
      request &&
      request.generation === generation &&
      !request.signal.aborted
    );
  }

  return {
    start() {
      if (!active || busy) return null;
      busy = true;
      controller = new AbortController();
      return {
        generation: ++generation,
        signal: controller.signal,
      };
    },
    isCurrent,
    finish(request) {
      if (!isCurrent(request)) return false;
      busy = false;
      controller = null;
      return true;
    },
    cancel() {
      active = false;
      busy = false;
      generation += 1;
      controller?.abort();
      controller = null;
    },
  };
}

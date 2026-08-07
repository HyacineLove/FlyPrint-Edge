import { q } from "./dom.js";
import { state, saveSessionState } from "./session-state.js";

export function capabilityValues(rawValue) {
  if (Array.isArray(rawValue)) {
    return rawValue.map((item) => String(item || "").toLowerCase()).filter(Boolean);
  }
  if (rawValue == null) return [];
  return [String(rawValue).toLowerCase()];
}

export function supportsDuplex(capabilities) {
  return capabilityValues(capabilities?.duplex).some((value) => {
    return (
      value !== "none" &&
      value !== "simplex" &&
      (value.includes("duplex") || value.includes("long") || value.includes("short"))
    );
  });
}

export function supportsColor(capabilities) {
  return capabilityValues(capabilities?.color_model).some((value) => {
    return value.includes("rgb") || value.includes("color") || value.includes("colour");
  });
}

const PAPER_SIZE_ALIASES = new Map([
  ["iso_a3_297x420mm", "A3"],
  ["iso_a4_210x297mm", "A4"],
  ["iso_a5_148x210mm", "A5"],
  ["iso_b5_176x250mm", "B5"],
  ["na_letter_8.5x11in", "Letter"],
  ["na_legal_8.5x14in", "Legal"],
  ["na_ledger_11x17in", "Tabloid"],
]);

export function normalizePaperSizeCapability(value) {
  const raw = String(value || "").trim();
  return PAPER_SIZE_ALIASES.get(raw.toLowerCase()) || raw;
}

export function supportsPaperSize(capabilities, paperSize) {
  const rawValues = capabilities?.page_size ?? capabilities?.paper_sizes;
  if (!Array.isArray(rawValues) || rawValues.length === 0) return true;
  const expected = String(paperSize || "").trim().toLowerCase();
  return rawValues.some((value) => normalizePaperSizeCapability(value).toLowerCase() === expected);
}

export function applyPrinterCapabilityState(capabilities) {
  const capabilityState = {
    duplexSupported: supportsDuplex(capabilities),
    colorSupported: supportsColor(capabilities),
  };
  state.defaultPrinterCapabilities =
    capabilities && typeof capabilities === "object" ? capabilities : null;
  state.capabilityState = capabilityState;

  if (!capabilityState.duplexSupported) {
    state.options.duplex = "simplex";
  }
  if (!capabilityState.colorSupported) {
    state.options.color_mode = "mono";
  }

  saveSessionState();
  return capabilityState;
}

export function setOptionDisabledState(ids, disabled) {
  ids.forEach((id) => {
    const el = q(id);
    if (!el) return;
    el.classList.toggle("is-option-disabled", disabled);
    el.style.pointerEvents = disabled ? "none" : "auto";
    el.style.cursor = disabled ? "not-allowed" : "pointer";
    el.setAttribute("aria-disabled", disabled ? "true" : "false");
  });
}

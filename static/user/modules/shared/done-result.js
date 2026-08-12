const PRINTER_FAULT_CODES = new Set([
  "printer_fault",
  "printer_out_of_paper",
  "printer_out_of_toner",
  "printer_jammed",
  "printer_cover_open",
  "printer_offline",
  "printer_user_intervention",
]);

const UNCONFIRMED_CODES = new Set([
  "result_unconfirmed",
  "ipp_submission_unconfirmed",
  "ipp_job_query_failed",
  "ipp_cancel_failed",
]);

export function isPrinterFaultDoneResult(result) {
  return result?.type === "error" && PRINTER_FAULT_CODES.has(result.error_code);
}

export function isUnconfirmedDoneResult(result) {
  return result?.type === "error" && UNCONFIRMED_CODES.has(result.error_code);
}

export function isFaultLockedDoneResult(result) {
  return isPrinterFaultDoneResult(result) || isUnconfirmedDoneResult(result);
}

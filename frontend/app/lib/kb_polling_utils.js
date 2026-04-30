/**
 * @typedef {string | undefined | null} KbTaskStatus
 */

/**
 * @param {KbTaskStatus} status
 */
export function kbTaskIsTerminal(status) {
  const s = String(status || "").toLowerCase().trim();
  return s === "done" || s === "failed";
}

/**
 * @param {KbTaskStatus} status
 */
export function kbTaskIsActive(status) {
  return !kbTaskIsTerminal(status);
}


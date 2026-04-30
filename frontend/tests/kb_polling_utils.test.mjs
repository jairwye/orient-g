import test from "node:test";
import assert from "node:assert/strict";

import { kbTaskIsActive, kbTaskIsTerminal } from "../app/lib/kb_polling_utils.js";

test("kbTaskIsTerminal recognizes done/failed", () => {
  assert.equal(kbTaskIsTerminal("done"), true);
  assert.equal(kbTaskIsTerminal("failed"), true);
  assert.equal(kbTaskIsTerminal("DONE"), true);
  assert.equal(kbTaskIsTerminal("Failed"), true);
});

test("kbTaskIsTerminal false for active statuses", () => {
  for (const s of ["queued", "parsing", "parsed", "packaged", "", null, undefined]) {
    assert.equal(kbTaskIsTerminal(s), false);
    assert.equal(kbTaskIsActive(s), true);
  }
});


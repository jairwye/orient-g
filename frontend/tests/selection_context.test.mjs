import test from "node:test";
import assert from "node:assert/strict";

import {
  deleteSemanticsForContext,
  isSameSelectionContext,
  normalizeSourceFolderId,
} from "../app/knowledge/lib/selection_context.js";

test("normalizeSourceFolderId(null/undefined/\"\"=>null, \"  f1 \"=>\"f1\")", () => {
  assert.equal(normalizeSourceFolderId(null), null);
  assert.equal(normalizeSourceFolderId(undefined), null);
  assert.equal(normalizeSourceFolderId(""), null);
  assert.equal(normalizeSourceFolderId("   "), null);
  assert.equal(normalizeSourceFolderId("  f1 "), "f1");
});

test("isSameSelectionContext(loose vs folder) 行为", () => {
  assert.equal(isSameSelectionContext(null, null), true);
  assert.equal(isSameSelectionContext(null, "f1"), false);
  assert.equal(isSameSelectionContext("f1", null), false);
  assert.equal(isSameSelectionContext("f1", "f1"), true);
  assert.equal(isSameSelectionContext("f1", "f2"), false);
});

test("deleteSemanticsForContext(null=>hard_delete; f1=>unlink_from_folder)", () => {
  assert.deepEqual(deleteSemanticsForContext(null), { kind: "hard_delete" });
  assert.deepEqual(deleteSemanticsForContext("f1"), {
    kind: "unlink_from_folder",
    folder_id: "f1",
  });
});


import test from "node:test";
import assert from "node:assert/strict";

import { normalizeSelection } from "../app/knowledge/lib/kb_selection.js";

test("normalizeSelection defaults to Private kb", () => {
  assert.deepEqual(normalizeSelection(null), { kind: "kb", kb_kind: "Private" });
});

test("normalizeSelection keeps folder when folder_id present", () => {
  assert.deepEqual(normalizeSelection({ kind: "folder", kb_kind: "DeptPublic", folder_id: " f1 " }), {
    kind: "folder",
    kb_kind: "DeptPublic",
    folder_id: "f1",
  });
});

test("normalizeSelection downgrades to kb when folder_id missing", () => {
  assert.deepEqual(normalizeSelection({ kind: "folder", kb_kind: "DeptPublic", folder_id: "" }), { kind: "kb", kb_kind: "DeptPublic" });
});


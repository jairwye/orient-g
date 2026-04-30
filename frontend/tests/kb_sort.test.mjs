import test from "node:test";
import assert from "node:assert/strict";

import { sortKbKindsPinned } from "../app/knowledge/lib/kb_sort.js";

test("sortKbKindsPinned pins Private and CompanyPublic first", () => {
  const input = ["DeptPublic", "Private", "ProjectPublic", "CompanyPublic", "MultiDeptPublic"];
  const out = sortKbKindsPinned(input);
  assert.deepEqual(out.slice(0, 2), ["Private", "CompanyPublic"]);
});

test("sortKbKindsPinned keeps remaining order and removes duplicates", () => {
  const input = ["Private", "DeptPublic", "DeptPublic", "CompanyPublic", "ProjectPublic"];
  const out = sortKbKindsPinned(input);
  assert.deepEqual(out, ["Private", "CompanyPublic", "DeptPublic", "ProjectPublic"]);
});


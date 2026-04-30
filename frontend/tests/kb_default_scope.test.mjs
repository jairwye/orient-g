import test from "node:test";
import assert from "node:assert/strict";
import { computeDefaultScopeKinds } from "../app/knowledge/lib/kb_default_scope.js";

test("computeDefaultScopeKinds: picks 4 kinds in required order when available", () => {
  assert.deepEqual(
    computeDefaultScopeKinds({
      availableKinds: ["CompanyPublic", "ProjectPublic", "DeptPublic", "Private"],
      hasProjectAccess: true,
    }),
    ["Private", "DeptPublic", "ProjectPublic", "CompanyPublic"],
  );
});

test("computeDefaultScopeKinds: omits ProjectPublic when no access", () => {
  assert.deepEqual(
    computeDefaultScopeKinds({
      availableKinds: ["CompanyPublic", "ProjectPublic", "DeptPublic", "Private"],
      hasProjectAccess: false,
    }),
    ["Private", "DeptPublic", "CompanyPublic"],
  );
});

test("computeDefaultScopeKinds: only returns kinds that exist", () => {
  assert.deepEqual(
    computeDefaultScopeKinds({
      availableKinds: ["Private", "CompanyPublic"],
      hasProjectAccess: true,
    }),
    ["Private", "CompanyPublic"],
  );
});


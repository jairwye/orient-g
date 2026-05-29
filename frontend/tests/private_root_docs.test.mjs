import test from "node:test";
import assert from "node:assert/strict";

import {
  folderBulkCheckState,
  folderBulkToggleAll,
  isInternalPrivateFolderId,
  isUnfiledPrivateDoc,
  visibleFolderBindings,
  visibleFolderIdSet,
} from "../app/knowledge/lib/private_root_docs.js";

test("isInternalPrivateFolderId", () => {
  assert.equal(isInternalPrivateFolderId("f_private_u1"), true);
  assert.equal(isInternalPrivateFolderId("f_abc"), false);
});

test("visibleFolderIdSet excludes internal folders", () => {
  const ids = visibleFolderIdSet([
    { folder_id: "f_private_u1" },
    { folder_id: "f_contract" },
    { folder_id: "f_other" },
  ]);
  assert.equal(ids.has("f_private_u1"), false);
  assert.equal(ids.has("f_contract"), true);
});

test("isUnfiledPrivateDoc: only hidden folder binding counts as unfiled", () => {
  const visible = visibleFolderIdSet([{ folder_id: "f_contract" }]);
  assert.equal(
    isUnfiledPrivateDoc({ folder_ids: ["f_private_u1"], status: "active" }, visible),
    true,
  );
  assert.equal(
    isUnfiledPrivateDoc({ folder_ids: ["f_private_u1", "f_contract"], status: "active" }, visible),
    false,
  );
  assert.equal(isUnfiledPrivateDoc({ folder_ids: [], status: "active" }, visible), true);
});

test("isUnfiledPrivateDoc: running docs when includeRunning", () => {
  const visible = visibleFolderIdSet([]);
  assert.equal(isUnfiledPrivateDoc({ folder_ids: [], status: "running" }, visible), true);
  assert.equal(
    isUnfiledPrivateDoc({ folder_ids: [], status: "running" }, visible, { includeRunning: false }),
    false,
  );
});

test("isUnfiledPrivateDoc: filed if any non-internal folder binding (even when visibleIds empty)", () => {
  const emptyVisible = visibleFolderIdSet([]);
  assert.equal(
    isUnfiledPrivateDoc({ folder_ids: ["f_contract"], status: "active" }, emptyVisible),
    false,
  );
});

test("visibleFolderBindings respects visibleIds subset", () => {
  const visible = visibleFolderIdSet([{ folder_id: "f_a" }]);
  assert.deepEqual(
    visibleFolderBindings({ folder_ids: ["f_a", "f_b"] }, visible),
    ["f_a"],
  );
});

test("folderBulkCheckState and folderBulkToggleAll", () => {
  assert.equal(folderBulkCheckState(["a", "b"], []), "none");
  assert.equal(folderBulkCheckState(["a", "b"], ["a"]), "partial");
  assert.equal(folderBulkCheckState(["a", "b"], ["a", "b"]), "all");
  assert.deepEqual(folderBulkToggleAll("none", ["a", "b"]), ["a", "b"]);
  assert.deepEqual(folderBulkToggleAll("partial", ["a", "b"]), ["a", "b"]);
  assert.deepEqual(folderBulkToggleAll("all", ["a", "b"]), []);
});

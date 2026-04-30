import test from "node:test";
import assert from "node:assert/strict";
import { optimisticRemoveDocFromFolderDetail, folderViewHeading } from "../app/knowledge/lib/kb_folder_view.js";

test("optimisticRemoveDocFromFolderDetail removes doc_id from docs list", () => {
  const before = {
    folder: { folder_id: "f1", name: "合同管理" },
    docs: [{ doc_id: "d1" }, { doc_id: "d2" }],
  };
  const after = optimisticRemoveDocFromFolderDetail(before, "d1");
  assert.deepEqual(after.docs.map((d) => d.doc_id), ["d2"]);
});

test("optimisticRemoveDocFromFolderDetail returns same object if no match", () => {
  const before = { folder: { folder_id: "f1" }, docs: [{ doc_id: "d1" }] };
  const after = optimisticRemoveDocFromFolderDetail(before, "d2");
  assert.equal(after, before);
});

test("folderViewHeading prefers folderName, falls back to folderId", () => {
  assert.equal(folderViewHeading({ folderName: " 合同管理 ", folderId: "f1" }), "合同管理");
  assert.equal(folderViewHeading({ folderName: "", folderId: " f1 " }), "文件夹：f1");
});


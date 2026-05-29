import test from "node:test";
import assert from "node:assert/strict";

import {
  isPrivateKbRootSelection,
  pickPrivateRootDocs,
  resolveDocsForActiveKb,
} from "../app/knowledge/lib/kb_docs_for_panel.js";
import { visibleFolderIdSet } from "../app/knowledge/lib/private_root_docs.js";

const folders = [
  { folder_id: "f_contract", name: "合同管理", kind: "Private" },
  { folder_id: "f_private_u1", name: "我的私人知识库", kind: "Private" },
];

const visible = visibleFolderIdSet(folders);

test("isPrivateKbRootSelection", () => {
  assert.equal(isPrivateKbRootSelection("kb", "Private"), true);
  assert.equal(isPrivateKbRootSelection("folder", "Private"), false);
  assert.equal(isPrivateKbRootSelection("kb", "DeptPublic"), false);
});

test("pickPrivateRootDocs: only unfiled private docs", () => {
  const myDocs = [
    { doc_id: "d1", title: "a.pdf", folder_ids: ["f_private_u1"], status: "active" },
    { doc_id: "d2", title: "b.pdf", folder_ids: ["f_contract"], status: "active" },
    { doc_id: "d3", title: "c.pdf", folder_ids: [], status: "active" },
  ];
  const picked = pickPrivateRootDocs(myDocs, visible);
  assert.deepEqual(picked.map((d) => d.doc_id).sort(), ["d1", "d3"]);
});

test("resolveDocsForActiveKb: Private kb shows only private root, not all myDocs", () => {
  const myDocs = [
    { doc_id: "d1", title: "unfiled.pdf", folder_ids: ["f_private_u1"], status: "active" },
    { doc_id: "d2", title: "in-folder.pdf", folder_ids: ["f_contract"], status: "active" },
    { doc_id: "d3", title: "dept.pdf", folder_ids: ["f_dept"], status: "active" },
  ];
  const privateRoot = pickPrivateRootDocs(myDocs, visible);
  const rows = resolveDocsForActiveKb({
    selectionKind: "kb",
    activeKbKind: "Private",
    privateRootDocs: privateRoot,
    myDocs,
    folders: [...folders, { folder_id: "f_dept", name: "部门", kind: "DeptPublic" }],
  });
  assert.deepEqual(rows.map((r) => r.doc_id).sort(), ["d1"]);
});

test("resolveDocsForActiveKb: folder selection uses folder docs only", () => {
  const folderDocs = [{ doc_id: "x1", title: "in folder" }];
  const rows = resolveDocsForActiveKb({
    selectionKind: "folder",
    activeKbKind: "Private",
    folderDocs,
    myDocs: [{ doc_id: "d1", folder_ids: [], status: "active" }],
    privateRootDocs: [{ doc_id: "d1" }],
  });
  assert.deepEqual(rows, folderDocs);
});

test("resolveDocsForActiveKb: DeptPublic kb aggregates by folder kind", () => {
  const myDocs = [
    { doc_id: "d1", title: "a", folder_ids: ["f_dept"], status: "active", created_at: "2026-01-02" },
    { doc_id: "d2", title: "b", folder_ids: ["f_contract"], status: "active", created_at: "2026-01-03" },
  ];
  const rows = resolveDocsForActiveKb({
    selectionKind: "kb",
    activeKbKind: "DeptPublic",
    myDocs,
    folders: [
      { folder_id: "f_dept", kind: "DeptPublic" },
      { folder_id: "f_contract", kind: "Private" },
    ],
  });
  assert.deepEqual(rows.map((r) => r.doc_id), ["d1"]);
});

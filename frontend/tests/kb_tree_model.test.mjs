import test from "node:test";
import assert from "node:assert/strict";
import {
  folderAncestorIds,
  folderChildrenAt,
  folderChildrenOf,
  folderSubtreeDocCount,
  folderTreeBadgeCount,
  filterFoldersForTreeSearch,
  isKbKindTreeExpanded,
  kbKindRootFolders,
  privateKbRootEntries,
} from "../app/knowledge/lib/kb_tree_model.js";

test("folderChildrenAt groups by parent_folder_id", () => {
  const folders = [
    { folder_id: "a", parent_folder_id: null, name: "A" },
    { folder_id: "b", parent_folder_id: "a", name: "B" },
    { folder_id: "c", parent_folder_id: null, name: "C" },
  ];
  assert.deepEqual(folderChildrenAt(folders, null).map((f) => f.folder_id), ["a", "c"]);
  assert.deepEqual(folderChildrenAt(folders, "a").map((f) => f.folder_id), ["b"]);
});

test("folderChildrenOf includes cross-kind children (华清25 under 竞品财报25)", () => {
  const folders = [
    { folder_id: "dept_root", name: "竞品财报25", kind: "DeptPublic", parent_folder_id: null },
    { folder_id: "child", name: "华清25", kind: "Private", parent_folder_id: "dept_root" },
  ];
  assert.deepEqual(kbKindRootFolders(folders, "DeptPublic").map((f) => f.folder_id), ["dept_root"]);
  assert.deepEqual(folderChildrenOf(folders, "dept_root").map((f) => f.folder_id), ["child"]);
});

test("privateKbRootEntries: unfiled then folder roots at same level", () => {
  const folders = [
    { folder_id: "f1", name: "合同管理", kind: "Private", parent_folder_id: null },
    { folder_id: "f2", name: "数据分析", kind: "Private", parent_folder_id: null },
  ];
  const entries = privateKbRootEntries(folders, 3);
  assert.equal(entries[0].type, "unfiled");
  assert.equal(entries[0].count, 3);
  assert.deepEqual(
    entries.slice(1).map((e) => e.folder.folder_id),
    ["f1", "f2"],
  );
});

test("filterFoldersForTreeSearch keeps ancestors of matches", () => {
  const folders = [
    { folder_id: "r", parent_folder_id: null, name: "竞品财报25" },
    { folder_id: "c", parent_folder_id: "r", name: "华清25" },
  ];
  const kept = filterFoldersForTreeSearch(folders, "华清");
  assert.deepEqual(kept.map((f) => f.folder_id).sort(), ["c", "r"]);
});

test("folderAncestorIds walks up to root", () => {
  const folders = [
    { folder_id: "r", parent_folder_id: null },
    { folder_id: "c", parent_folder_id: "r" },
    { folder_id: "g", parent_folder_id: "c" },
  ];
  assert.deepEqual(folderAncestorIds(folders, "g"), ["r", "c"]);
});

test("isKbKindTreeExpanded when active or child folder selected", () => {
  assert.equal(isKbKindTreeExpanded("Private", "DeptPublic", { kind: "kb", kb_kind: "Private" }), false);
  assert.equal(isKbKindTreeExpanded("Private", "Private", { kind: "kb", kb_kind: "Private" }), true);
  assert.equal(
    isKbKindTreeExpanded("Private", "DeptPublic", { kind: "folder", kb_kind: "Private", folder_id: "f1" }),
    true,
  );
});

test("folderSubtreeDocCount prefers subtree_doc_count", () => {
  assert.equal(folderSubtreeDocCount({ subtree_doc_count: 3, resource_counts: { doc: 0 } }), 3);
  assert.equal(folderSubtreeDocCount({ resource_counts: { doc: 2 } }), 2);
});

test("folderTreeBadgeCount: direct docs, else immediate child folder count", () => {
  const folders = [
    { folder_id: "dept_root", name: "竞品财报25", resource_counts: { doc: 0 } },
    { folder_id: "child", name: "华清25", parent_folder_id: "dept_root", resource_counts: { doc: 399 } },
  ];
  assert.equal(folderTreeBadgeCount(folders[0], folders), 1);
  assert.equal(folderTreeBadgeCount(folders[1], folders), 399);
  assert.equal(folderTreeBadgeCount({ folder_id: "x", resource_counts: { doc: 2 } }, folders), 2);
});

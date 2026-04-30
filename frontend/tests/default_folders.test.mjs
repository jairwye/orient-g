import test from "node:test";
import assert from "node:assert/strict";

import { pickDeptDefaultFolderName } from "../app/knowledge/lib/default_folders.js";

test("pickDeptDefaultFolderName returns null when not wangjia", () => {
  assert.equal(pickDeptDefaultFolderName({ username: "alice", existingNames: [], candidates: ["合同管理", "合同台账"] }), null);
});

test("pickDeptDefaultFolderName picks first missing candidate", () => {
  assert.equal(
    pickDeptDefaultFolderName({ username: "wangjia", existingNames: ["财务报表"], candidates: ["合同管理", "合同台账"] }),
    "合同管理"
  );
  assert.equal(
    pickDeptDefaultFolderName({ username: "wangjia", existingNames: ["合同管理"], candidates: ["合同管理", "合同台账"] }),
    "合同台账"
  );
});


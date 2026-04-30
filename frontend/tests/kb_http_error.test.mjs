import test from "node:test";
import assert from "node:assert/strict";
import { formatHttpError } from "../app/knowledge/lib/kb_http_error.js";

test("formatHttpError prefers detail", () => {
  assert.equal(formatHttpError({ status: 409, detail: "同名" }), "HTTP 409：同名");
});

test("formatHttpError falls back to text snippet", () => {
  assert.equal(formatHttpError({ status: 500, text: "Internal Server Error" }), "HTTP 500：Internal Server Error");
});

test("formatHttpError uses fallback if no detail/text", () => {
  assert.equal(formatHttpError({ status: 401, fallback: "创建失败" }), "HTTP 401：创建失败");
});


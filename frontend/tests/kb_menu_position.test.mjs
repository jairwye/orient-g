import test from "node:test";
import assert from "node:assert/strict";
import { computeMenuPosition } from "../app/knowledge/lib/kb_menu_position.js";

test("computeMenuPosition places down when enough space below", () => {
  const r = computeMenuPosition({
    anchorTop: 100,
    anchorLeft: 300,
    anchorBottom: 120,
    anchorWidth: 20,
    menuWidth: 200,
    menuHeight: 150,
    viewportWidth: 800,
    viewportHeight: 600,
    gap: 8,
  });
  assert.equal(r.placement, "down");
  assert.ok(r.top >= 120, "top should be below anchor");
});

test("computeMenuPosition places up when not enough space below", () => {
  const r = computeMenuPosition({
    anchorTop: 520,
    anchorLeft: 300,
    anchorBottom: 540,
    anchorWidth: 20,
    menuWidth: 200,
    menuHeight: 150,
    viewportWidth: 800,
    viewportHeight: 600,
    gap: 8,
  });
  assert.equal(r.placement, "up");
  assert.ok(r.top <= 520, "top should be above anchor");
});


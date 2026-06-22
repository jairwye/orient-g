import {
  collectSnapOffsets,
  resolveActiveSnap,
  resolveScrollEndTarget,
  snapOffsetTop,
} from "../scroll_spy";

describe("resolveActiveSnap", () => {
  const ids = ["sec-01-a", "sec-01-b", "sec-01-c", "sec-02-a"] as const;

  it("首屏选中 sec-01-a", () => {
    const offsets = new Map([
      ["sec-01-a", 0],
      ["sec-01-b", 800],
      ["sec-01-c", 1600],
      ["sec-02-a", 2400],
    ]);
    expect(resolveActiveSnap(ids, offsets, 0)).toBe("sec-01-a");
    expect(resolveActiveSnap(ids, offsets, 100)).toBe("sec-01-a");
  });

  it("滚过 sec-01-b 锚点后选中 sec-01-b（probe = scrollTop + 80）", () => {
    const offsets = new Map([
      ["sec-01-a", 0],
      ["sec-01-b", 800],
      ["sec-01-c", 1600],
    ]);
    expect(resolveActiveSnap(ids, offsets, 719)).toBe("sec-01-a");
    expect(resolveActiveSnap(ids, offsets, 720)).toBe("sec-01-b");
    expect(resolveActiveSnap(ids, offsets, 1200)).toBe("sec-01-b");
  });

  it("缺失 offset 时不抛错", () => {
    const offsets = new Map([["sec-01-a", 0]]);
    expect(resolveActiveSnap(ids, offsets, 5000)).toBe("sec-01-a");
  });
});

describe("snapOffsetTop", () => {
  it("相对 scroll root 计算 offsetTop", () => {
    const root = document.createElement("div");
    Object.defineProperty(root, "scrollTop", { value: 100, writable: true });
    const child = document.createElement("div");
    root.getBoundingClientRect = () => ({ top: 50 } as DOMRect);
    child.getBoundingClientRect = () => ({ top: 450 } as DOMRect);
    expect(snapOffsetTop(child, root)).toBe(500);
  });
});

describe("collectSnapOffsets", () => {
  it("读取 data-competitor-snap 元素 offset", () => {
    const root = document.createElement("div");
    const a = document.createElement("div");
    a.dataset.competitorSnap = "sec-01-a";
    const b = document.createElement("div");
    b.dataset.competitorSnap = "sec-01-b";
    root.appendChild(a);
    root.appendChild(b);

    const spy = jest.spyOn(a, "getBoundingClientRect").mockReturnValue({ top: 0 } as DOMRect);
    jest.spyOn(b, "getBoundingClientRect").mockReturnValue({ top: 400 } as DOMRect);
    jest.spyOn(root, "getBoundingClientRect").mockReturnValue({ top: 0 } as DOMRect);
    Object.defineProperty(root, "scrollTop", { value: 0, writable: true });

    const offsets = collectSnapOffsets(root, ["sec-01-a", "sec-01-b", "sec-99-x"]);
    expect(offsets.get("sec-01-a")).toBe(0);
    expect(offsets.get("sec-01-b")).toBe(400);
    expect(offsets.has("sec-99-x")).toBe(false);

    spy.mockRestore();
  });
});

describe("resolveScrollEndTarget", () => {
  const ids = ["sec-01-a", "sec-01-b", "sec-02-a"] as const;
  const vh = 800;
  const tallMetrics = new Map([
    ["sec-01-a", { top: 0, height: 800 }],
    ["sec-01-b", { top: 800, height: 1600 }],
    ["sec-02-a", { top: 2400, height: 800 }],
  ]);

  it("仅内容上滚且屏底越过视口中线时吸下一屏", () => {
    expect(resolveScrollEndTarget(ids, tallMetrics, 2001, vh, "up")).toEqual({
      scrollTop: 2400,
      activeId: "sec-02-a",
      shouldSnap: true,
    });
    expect(resolveScrollEndTarget(ids, tallMetrics, 1990, vh, "up")).toEqual({
      scrollTop: 1990,
      activeId: "sec-01-b",
      shouldSnap: false,
    });
    expect(resolveScrollEndTarget(ids, tallMetrics, 1200, vh, "up")).toEqual({
      scrollTop: 1200,
      activeId: "sec-01-b",
      shouldSnap: false,
    });
  });

  it("等高的标准屏底越过中线时同样磁吸", () => {
    const equalMetrics = new Map([
      ["sec-01-a", { top: 0, height: 800 }],
      ["sec-01-b", { top: 800, height: 800 }],
      ["sec-02-a", { top: 1600, height: 800 }],
    ]);
    expect(resolveScrollEndTarget(["sec-01-a", "sec-01-b", "sec-02-a"], equalMetrics, 401, vh, "up")).toEqual({
      scrollTop: 800,
      activeId: "sec-01-b",
      shouldSnap: true,
    });
    expect(resolveScrollEndTarget(["sec-01-a", "sec-01-b", "sec-02-a"], equalMetrics, 350, vh, "up")).toEqual({
      scrollTop: 350,
      activeId: "sec-01-a",
      shouldSnap: false,
    });
  });

  it("向下回看时不磁吸", () => {
    expect(resolveScrollEndTarget(ids, tallMetrics, 1900, vh, "down")).toEqual({
      scrollTop: 1900,
      activeId: "sec-01-b",
      shouldSnap: false,
    });
    expect(resolveScrollEndTarget(ids, tallMetrics, 1900, vh, null)).toEqual({
      scrollTop: 1900,
      activeId: "sec-01-b",
      shouldSnap: false,
    });
  });

  it("超高屏未滚到面板底部时不提前磁吸", () => {
    expect(resolveScrollEndTarget(ids, tallMetrics, 1700, vh, "up")).toEqual({
      scrollTop: 1700,
      activeId: "sec-01-b",
      shouldSnap: false,
    });
  });
});

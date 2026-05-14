import { sanitizeRichHtml } from "@/app/utils/sanitizeHtml";

describe("sanitizeRichHtml", () => {
  it("removes script tags and inline event handlers", () => {
    const raw = `<div onclick="alert(1)"><script>alert(2)</script><img src="https://x.test/a.png" onerror="alert(3)" /></div>`;
    const out = sanitizeRichHtml(raw);
    expect(out).not.toContain("<script");
    expect(out).not.toContain("onclick=");
    expect(out).not.toContain("onerror=");
    expect(out).toContain("<img");
  });

  it("removes javascript protocol urls", () => {
    const raw = `<a href="javascript:alert(1)">x</a><a href="https://safe.test">ok</a>`;
    const out = sanitizeRichHtml(raw);
    expect(out).not.toContain("javascript:");
    expect(out).toContain('href="https://safe.test"');
  });
});


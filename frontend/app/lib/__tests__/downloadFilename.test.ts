import { parseContentDispositionFilename } from "../downloadFilename";

describe("parseContentDispositionFilename", () => {
  it("prefers filename* UTF-8", () => {
    const header =
      'attachment; filename="____2024__cn_kb.zip"; filename*=UTF-8\'\'%E4%B8%89%E4%B8%83%E4%BA%92%E5%A8%B1-2024%E5%B9%B4_cn_kb.zip';
    expect(parseContentDispositionFilename(header, "fallback.zip")).toBe(
      "三七互娱-2024年_cn_kb.zip",
    );
  });

  it("falls back to quoted filename", () => {
    expect(parseContentDispositionFilename('attachment; filename="pkg.zip"', "x.zip")).toBe("pkg.zip");
  });

  it("uses fallback when header missing", () => {
    expect(parseContentDispositionFilename(null, "default.zip")).toBe("default.zip");
  });
});

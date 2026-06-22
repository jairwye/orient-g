import { normalizeVerticalMarkdown } from "../vertical_preserved_text";

describe("normalizeVerticalMarkdown", () => {
  it("保留 MD 硬换行", () => {
    const md = "第一行\n第二行\n\n空行后";
    expect(normalizeVerticalMarkdown(md)).toBe(md);
  });

  it("去掉 blockquote 前缀", () => {
    expect(normalizeVerticalMarkdown("> 来源说明\n正文")).toBe("来源说明\n正文");
  });
});

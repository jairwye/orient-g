import { normalizeVerticalMarkdown, splitVerticalParagraphs } from "../vertical_preserved_text";

describe("normalizeVerticalMarkdown", () => {
  it("保留 MD 硬换行", () => {
    const md = "第一行\n第二行\n\n空行后";
    expect(normalizeVerticalMarkdown(md)).toBe(md);
  });

  it("去掉 blockquote 前缀", () => {
    expect(normalizeVerticalMarkdown("> 来源说明\n正文")).toBe("来源说明\n正文");
  });
});

describe("splitVerticalParagraphs", () => {
  it("子标题与列表分项", () => {
    const md = "**亮点**\n\n- 第一条\n- 第二条";
    const blocks = splitVerticalParagraphs(md);
    expect(blocks.some((b) => b.startsWith("__subhead__:亮点"))).toBe(true);
    expect(blocks.filter((b) => b.startsWith("-")).length).toBe(2);
  });
});

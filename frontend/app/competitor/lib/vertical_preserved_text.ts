/** 纵向对比正文：按段落渲染（PDF 一段 = MD 一段，段内忽略硬换行） */
export function normalizeVerticalMarkdown(markdown: string): string {
  return markdown
    .split("\n")
    .map((line) => line.replace(/^>\s?/, ""))
    .join("\n")
    .trimEnd();
}

/** 将 narrative 文本拆成段落块；表格行原样保留为独立块 */
export function splitVerticalParagraphs(markdown: string): string[] {
  const text = normalizeVerticalMarkdown(markdown);
  if (!text) return [];

  const blocks: string[] = [];
  let buf: string[] = [];

  const flush = () => {
    if (!buf.length) return;
    const joined = buf.join(" ").replace(/\s+/g, " ").trim();
    if (joined) blocks.push(joined);
    buf = [];
  };

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    if (line.startsWith("|")) {
      flush();
      blocks.push(line);
      continue;
    }
    if (/^\d+\./.test(line) || /^[·•]/.test(line)) {
      flush();
      buf = [line];
      continue;
    }
    if (/^([一二三四五六七八九十]+[、．.]|亮点总结|风险总结|洞察：|结论：)/.test(line)) {
      flush();
      buf = [line];
      continue;
    }
    if (buf.length && /[。！？；：)]$/.test(buf[buf.length - 1])) {
      flush();
      buf = [line];
    } else if (buf.length) {
      buf.push(line);
    } else {
      buf = [line];
    }
  }
  flush();
  return blocks;
}

function convertTsvTables(text: string): string {
  const lines = text.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.includes("\t") && line.split("\t").length - 1 >= 2) {
      const block: string[][] = [];
      while (i < lines.length) {
        const ln = lines[i];
        if (!ln.includes("\t") || ln.split("\t").length - 1 < 2) break;
        block.push(ln.split("\t").map((c) => c.trim()));
        i += 1;
      }
      if (block.length >= 2) {
        const head = block[0];
        out.push(`| ${head.join(" | ")} |`);
        out.push(`| ${head.map(() => "---").join(" | ")} |`);
        for (const row of block.slice(1)) {
          const cells = [...row, ...Array(Math.max(0, head.length - row.length)).fill("")];
          out.push(`| ${cells.slice(0, head.length).join(" | ")} |`);
        }
        continue;
      }
    }
    if (line.includes("\t")) {
      const cells = line.split("\t").map((c) => c.trim());
      if (cells.length >= 3 && cells[0] && !cells[0].startsWith("|")) {
        out.push(cells[0]);
        const rest = cells.slice(1).join("\t");
        if (rest.split("\t").length >= 2) {
          lines.splice(i + 1, 0, rest);
        }
        i += 1;
        continue;
      }
    }
    out.push(line);
    i += 1;
  }
  return out.join("\n");
}

export function normalizeAssistantMarkdown(text: string): string {
  let t = (text || "").trim();
  if (!t) return "";
  t = t.replace(/^(根据检索到的[^\n]+。\n?)/, "");
  t = convertTsvTables(t);
  t = t.replace(
    /^(华清\s*\d{4}[-、]\d{4}年销售费用[^\n]+报告)\s*$/gm,
    "## $1",
  );
  t = t.replace(/([\u4e00-\u9fff\d\-%]+报告)\s*(\d+\.)/g, "$1\n\n#### $2");
  t = t.replace(/(\|\s*—\s*\|)\s*(#{2,4})/g, "$1\n\n$2");
  t = t.replace(/(\|\s*[^\n|]+\|)\s*(#{2,4}\s*\d+\.)/g, "$1\n\n$2");
  t = t.replace(/(\|[^|\n]+\|)\s*(#{2,4}[^\n|]+)/g, "$1\n\n$2");
  t = t.replace(/\n\|\s*×\s*100\s*%/g, " ×100%");
  t = t.replace(/\|\s*×\s*100\s*%/g, " ×100%");
  t = t.replace(/^结论(?=[^\n#])/m, "## 结论\n\n");
  t = t.replace(/([。；;！!?])(#{2,4})(\S)/g, "$1\n\n$2 $3");
  t = t.replace(/([\u4e00-\u9fff\）\)])(\|)/g, "$1\n\n|");
  t = t.replace(/([。；;！!?])(\d+\.\s+)/g, "$1\n\n$2");
  t = t.replace(/(\|\s*—\s*\|)\s*(结论)/g, "$1\n\n\n### $2");
  t = t.replace(/([。；;！!?])(结论[：:])/g, "$1\n\n\n**$2**");
  t = t.replace(/([。；;！!?])(引用证据)/g, "$1\n\n\n**$2**");
  t = t.replace(/([。；;！!?])(说明[：:])/g, "$1\n\n\n**$2**");
  const lines = t.split("\n").map((line) => {
    if (line.includes("|") && line.includes("||")) {
      return line.replace(/\|\s*\|/g, "|\n|");
    }
    return line;
  });
  t = lines.join("\n").replace(/\n{3,}/g, "\n\n");
  return t.trim();
}

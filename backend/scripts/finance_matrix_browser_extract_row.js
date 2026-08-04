/**
 * 流式结束后采样一行报告字段（须先 poll 判定 streamDone）。
 */
() => {
  const stripTrace = (text) =>
    (text || "")
      .split("\n")
      .filter((line) => {
        const t = line.trim();
        if (!t) return false;
        if (/^[›◇◈▸•]/.test(t)) return false;
        if (
          /^(已提交任务|Evidence Pack 已就绪|深度编排|正在连接|Hermes Runs|Hermes 仍在|KB 任务禁止|orientg-debugging|●完成：Tier|模型：)/.test(
            t,
          )
        )
          return false;
        return true;
      })
      .join("\n")
      .trim();

  const pickPersonnelStructuredBody = (raw) => {
    const marker = "YYCQ vs 可比公司A · 2025 人员结构对比";
    const t = raw || "";
    const idx = t.lastIndexOf(marker);
    if (idx < 0) return null;
    return t
      .slice(idx)
      .replace(/^模型：[^\n]+\n/m, "")
      .replace(/●完成：Tier[^\n]+\n?/m, "")
      .trim();
  };

  const resolveReplaceFinalBody = (raw) => {
    const personnel = pickPersonnelStructuredBody(raw);
    if (personnel) return personnel;
    const t = raw || "";
    const tierIdx = t.indexOf("●完成：Tier");
    if (tierIdx < 0) return null;
    const after = t.slice(tierIdx);
    const modelM = after.match(/模型：[^\n]+\n([\s\S]*)/);
    const tail = modelM ? modelM[1].split(/引用证据/)[0].trim() : "";
    let head = t.slice(0, tierIdx).replace(/##\s*$/m, "").trim();
    if (/占比约/.test(head) && tail.length >= 120) {
      head = head
        .split("\n")
        .filter((ln) => !/占比约/.test(ln))
        .join("\n")
        .trim();
    }
    if (tail.length >= 200 && /1[,，]?378|\d{1,3}(?:,\d{3})+\.\d{2}/.test(tail)) {
      return head.length >= 100 ? `${head}\n\n${tail}` : tail;
    }
    if (head.length >= 150) return head;
    return tail.length >= 80 ? tail : null;
  };

  const stripOrchestration = (text) => {
    let t = text || "";
    const anchor = /(?:^|\n)(结论[:：]|YYCQ vs 可比公司A|#+\s|存货|缺少证据|无法提供|Inventory\b)/im;
    const m = anchor.exec(t);
    if (
      m &&
      m.index > 0 &&
      /Let me |The skill |Evidence Pack|Looking at the|doc_id:/i.test(t.slice(0, m.index))
    ) {
      t = t.slice(m.index).trim();
    }
    return t;
  };

  const pickAnswerElement = (block) => {
    if (!block) return null;
    const md = block.querySelector("div.space-y-3.text-sm");
    if (md && (md.innerText || "").trim().length >= 20) return md;
    const prose = block.querySelector(".prose, .markdown");
    if (prose && (prose.innerText || "").trim().length >= 20) return prose;
    return block;
  };

  const pickBestAssistantBlock = () => {
    const blocks = Array.from(
      document.querySelectorAll("main main div.flex.justify-start"),
    );
    if (!blocks.length) return null;
    let best = blocks[blocks.length - 1];
    let bestScore = 0;
    for (let i = blocks.length - 1; i >= Math.max(0, blocks.length - 5); i--) {
      const blk = blocks[i];
      const el = pickAnswerElement(blk);
      const raw = (el?.innerText || blk.innerText || "").trim();
      const cleaned = stripOrchestration(stripTrace(raw));
      const score =
        cleaned.length +
        (/\b946\b|\b242\b|1[,，]?378|\b70\b/.test(cleaned) ? 500 : 0) +
        (/结论|研发人员|员工数量|1\.1信息-人员|人员结构对照/.test(cleaned)
          ? 200
          : 0) -
        (/^执行过程|Evidence Pack 已就绪|本地 LLM 综合完成/.test(cleaned)
          ? 300
          : 0);
      if (score > bestScore) {
        bestScore = score;
        best = blk;
      }
    }
    return best;
  };

  const body = document.body?.innerText || "";
  const blocks = Array.from(
    document.querySelectorAll("main main div.flex.justify-start"),
  );
  const last = pickBestAssistantBlock() || blocks[blocks.length - 1];
  const lastBlockText = (last?.innerText || "").trim();
  const tierLine =
    (lastBlockText.match(/执行过程\([^)]+\)/) ||
      body.match(/执行过程\([^)]+\)/) ||
      [])[0] || "";
  const citeMatch =
    lastBlockText.match(/citations\s*[（(]\s*(\d+)/i) ||
    body.match(/citations\s*[（(]\s*(\d+)/i);
  const citations = citeMatch ? parseInt(citeMatch[1], 10) : 0;

  const answerEl = pickAnswerElement(last);
  const answerTextRaw = (answerEl?.innerText || "").trim();
  const finalSlice = resolveReplaceFinalBody(answerTextRaw);
  const answerText = finalSlice || answerTextRaw;
  const answerBody = stripOrchestration(
    stripTrace(
      answerText
        .replace(/^执行过程\([^)]+\)\s*/m, "")
        .replace(/^根据证据数据，直接生成报告：?\s*/m, "")
        .replace(
          /^Based on (?:the )?Evidence Pack provided,[^。.\n]*(?:needed|calls)[^。.\n]*[。.]\s*/im,
          "",
        )
        .replace(/^Based on[\s\S]*?###\s*Conclusion:\s*/im, "")
        .replace(/^Based on[\s\S]*?结论[:：]\s*/im, "")
        .replace(/\n*（Hermes 流式超时或失败[^\n）]*）\s*/g, "")
        .trim(),
    ),
  );

  const stripCiteFooter = (text) =>
    (text || "")
      .split(/引用证据/)[0]
      .replace(/(?:#+\s*)?引用说明[\s\S]*/i, "")
      .replace(/citations\s*[（(]\s*\d+\s*[）)][\s\S]*$/i, "")
      .replace(/citations\s*[（(]\s*\d+\s*[）)]/gi, "")
      .replace(
        /是否需要我[^？?\n]*[？?]?|建议[：:]?[^。.\n]*orientg_kb_ask[^。.\n]*[。.]?|如需完整对比[^。.\n]*[。.]?|通过 MCP 工具[^。.\n]*[。.]?|深度档应通过[^。.\n]*[。.]?/gi,
        "",
      )
      .trim();

  const citeFooter = stripCiteFooter(answerBody);
  const bodyForCite = citeFooter;
  const text = citeFooter || answerBody || answerText || body;
  const inlineCite =
    /\[(?:doc_chunk|evidence_pack|document)/i.test(bodyForCite) ||
    /\bud_[a-f0-9]{16,32}\b/i.test(bodyForCite) ||
    /doc_id:\s*`/i.test(bodyForCite) ||
    (/orientg_kb_ask/i.test(bodyForCite) &&
      !/not available|不可用|does not contain|未.*披露/i.test(bodyForCite)) ||
    /证据\s*`\s*`/.test(bodyForCite);
  const processInAnswer =
    /用户要求|步骤：|让我(?:先|通过|验证)|我将尝试|预检索证据|根据(?:已获取|检索结果|Evidence Pack)|很明确了|直接成稿如下|Evidence Pack中缺少|Let me search|I need to find/i.test(
      answerBody,
    ) &&
    !/^可比公司E|^结论|^#{1,3}\s|^The provided|^Based on/i.test(answerBody.slice(0, 60));

  return {
    tier_line: tierLine,
    citations,
    extract: {
      hasMoney:
        /\d{1,3}(?:,\d{3})+\.\d{2}/.test(text) ||
        /[\d,.]+万元/.test(text) ||
        /[\d,.+-]+万/.test(text) ||
        /\d+\.?\d*亿/.test(text) ||
        /\d+元/.test(text),
      honestMissing:
        /缺少证据|不确定|不确定\/缺少证据|does not contain|not contain the specific|无法进行对比|未能获取|不可用|not available|未在.*证据.*披露|未明确披露|均未.*披露|均未命中|未在预检索|未覆盖该字段|需进一步检索|缺少.*附注|不可获取|不含|永久限制|检索管道无法|未包含|无法回答|未披露|未进入.*索引|无法获取/i.test(
          text,
        ),
      hasTable: (text.includes("2025") && text.includes("2024")) || /\|.*\|/.test(text),
      badGap:
        text.includes("证据中未提供可核查的分项金额") &&
        (/\|.*\|/.test(text) || /\t\d{1,3}(?:,\d{3})+\.\d{2}/.test(text)) &&
        /\d{1,3}(?:,\d{3})+\.\d{2}/.test(text),
      badEst:
        (/约\s*[\d,.]+万|[\d]{1,3}\s*[-~至]\s*[\d]{1,3}\s*万/.test(text) &&
          !/\d{1,3}(?:,\d{3})+\.\d{2}/.test(text)) ||
        (/约\s*[\d,.]+/.test(text) &&
          /\d{1,3}(?:,\d{3})+\.\d{2}/.test(text) &&
          !/占比(?:约)?\d+(?:\.\d+)?%/.test(text) &&
          !/1[,，]?378|1378/.test(text)),
      badInlineCite: inlineCite,
      processInAnswer,
      len: text.length,
      head: text.slice(0, 800),
      body_sample: text.slice(0, Math.min(2800, text.length)),
      streamFail: /流式连接失败|(?:HTTP\s*)?502\s|502 Bad Gateway|Hermes 流式错误/.test(
        lastBlockText + body.slice(-2000),
      ),
    },
  };
};

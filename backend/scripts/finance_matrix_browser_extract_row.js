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
          /^(已提交任务|Evidence Pack 已就绪|深度编排|正在连接|Hermes Runs|Hermes 仍在|KB 任务禁止|orientg-debugging)/.test(
            t,
          )
        )
          return false;
        return true;
      })
      .join("\n")
      .trim();

  const stripOrchestration = (text) => {
    let t = text || "";
    const anchor = /(?:^|\n)(结论[:：]|#+\s|存货|缺少证据|无法提供|Inventory\b)/im;
    const m = anchor.exec(t);
    if (
      m &&
      m.index > 0 &&
      /Let me |The skill |Evidence Pack|Looking at the/i.test(t.slice(0, m.index))
    ) {
      t = t.slice(m.index).trim();
    }
    return t;
  };

  const body = document.body?.innerText || "";
  const blocks = Array.from(
    document.querySelectorAll("main main div.flex.justify-start"),
  );
  const last = blocks[blocks.length - 1];
  const lastBlockText = (last?.innerText || "").trim();
  const tierLine =
    (lastBlockText.match(/执行过程\([^)]+\)/) ||
      body.match(/执行过程\([^)]+\)/) ||
      [])[0] || "";
  const citeMatch =
    lastBlockText.match(/citations\s*[（(]\s*(\d+)/i) ||
    body.match(/citations\s*[（(]\s*(\d+)/i);
  const citations = citeMatch ? parseInt(citeMatch[1], 10) : 0;

  const answerEl = last?.querySelector(".prose, .markdown") || last;
  const answerText = (answerEl?.innerText || "").trim();
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
  const text = answerBody || answerText || body;

  const citeFooter = answerBody.split(/引用证据：/)[0];
  const bodyForCite = citeFooter.replace(
    /是否需要我[^？?\n]*[？?]?|建议[：:]?[^。.\n]*orientg_kb_ask[^。.\n]*[。.]?|如需完整对比[^。.\n]*[。.]?|通过 MCP 工具[^。.\n]*[。.]?/gi,
    "",
  );
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
    !/^华清|^结论|^#{1,3}\s|^The provided|^Based on/i.test(answerBody.slice(0, 60));

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
          /\d{1,3}(?:,\d{3})+\.\d{2}/.test(text)),
      badInlineCite: inlineCite,
      processInAnswer,
      len: text.length,
      head: text.slice(0, 800),
      streamFail: /流式连接失败|502|Hermes 流式错误/.test(lastBlockText + body.slice(-2000)),
    },
  };
};

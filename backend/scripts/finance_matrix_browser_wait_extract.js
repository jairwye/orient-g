/**
 * Chrome DevTools MCP：单条矩阵用例（含快速档顺序修复 + 答案质量探针）
 * evaluate_script function 体；args: [modeLabel, query, maxWaitMs]
 */
async (modeLabel, query, maxWaitMs) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const maxMs = Math.max(60000, Number(maxWaitMs) || 300000);
  const t0 = Date.now();

  const nav = Array.from(document.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === "智能体" && b.closest("nav"),
  );
  if (nav) {
    nav.click();
    await sleep(400);
  }

  const ta = document.querySelector("textarea");
  if (!ta) return { ok: false, err: "no textarea" };
  const setter = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype,
    "value",
  )?.set;

  const group = document.querySelector('[aria-label="智能体模式"]');
  const clickMode = async (label) => {
    const btn = group
      ? Array.from(group.querySelectorAll("button")).find(
          (b) => b.textContent?.trim() === label,
        )
      : null;
    if (btn) {
      btn.click();
      await sleep(modeLabel === "快速" ? 1500 : 250);
    }
  };

  // 快速档：先填问句 → 点「快速」→ 再发送（避免默认 standard 误走 Hermes）
  if (modeLabel === "快速") {
    setter?.call(ta, query);
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(150);
    await clickMode("快速");
  } else {
    await clickMode(modeLabel);
    setter?.call(ta, query);
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(150);
  }

  const sendBtn = () =>
    Array.from(document.querySelectorAll("button")).find(
      (b) => b.getAttribute("aria-label") === "发送" && !b.disabled,
    );
  const send = sendBtn();
  if (!send) return { ok: false, err: "send disabled before click" };
  send.click();

  let sawTier = false;
  let sawCitations = false;
  while (Date.now() - t0 < maxMs) {
    await sleep(2000);
    const body = document.body?.innerText || "";
    if (body.includes("执行过程(Tier")) sawTier = true;
    if (/citations\s*[（(]\s*\d+/i.test(body) || body.includes("citations（"))
      sawCitations = true;
    const canSend = !!sendBtn();
    const loading =
      body.includes("加载中") ||
      Array.from(document.querySelectorAll("button")).some(
        (b) => (b.textContent || "").includes("加载") && b.disabled,
      );
    if (sawCitations && canSend && !loading) break;
    if (sawTier && canSend && !loading && body.length > 800) {
      if (sawCitations || /缺少证据|不确定/.test(body)) break;
    }
  }

  const tierEl = Array.from(document.querySelectorAll("*")).find((el) =>
    (el.textContent || "").includes("执行过程(Tier"),
  );
  const tierLine =
    (tierEl?.textContent || "").match(/执行过程\([^)]+\)/)?.[0] || "";

  // 尽量只采主气泡（assistant 消息区），不含 trace 折叠块全文
  const assistantBlocks = Array.from(
    document.querySelectorAll("main main div.flex.justify-start"),
  );
  const lastAssist = assistantBlocks[assistantBlocks.length - 1];
  const answerEl =
    lastAssist?.querySelector(".prose, .markdown, [class*='whitespace-pre']") ||
    lastAssist;
  const answerText = (answerEl?.innerText || "").trim();
  const main = document.querySelector("main main") || document.querySelector("main");
  const text = main?.innerText || "";

  const inlineCite =
    /\[(?:doc_chunk|evidence_pack|document)[^\]]*\]/i.test(answerText) ||
    /\bud_[a-f0-9]{16,32}\b/i.test(answerText) ||
    /doc_id:\s*`/i.test(answerText) ||
    /orientg_kb_ask/i.test(answerText);
  const processInAnswer =
    /用户要求|步骤：|让我先|我将尝试|预检索证据|Evidence Pack/i.test(answerText);

  const hasMoney = /\d{1,3}(?:,\d{3})+\.\d{2}/.test(answerText || text);
  const honestMissing = /缺少证据|不确定\/缺少证据/.test(answerText || text);
  const hasTable =
    (answerText.includes("2025") && answerText.includes("2024")) ||
    /\|.*\|/.test(answerText);
  const badGap =
    answerText.includes("证据中未提供可核查的分项金额") && hasTable && hasMoney;
  const badEst = /约\s*[\d,.]+万/.test(answerText || text);
  const citeMatch = text.match(/citations\s*[（(]\s*(\d+)/i);
  const citations = citeMatch ? parseInt(citeMatch[1], 10) : 0;

  return {
    ok: true,
    mode: modeLabel,
    queryHead: String(query).slice(0, 48),
    tierLine,
    extract: {
      hasMoney,
      honestMissing,
      hasTable,
      badGap,
      badEst,
      badInlineCite: inlineCite,
      processInAnswer,
      len: (answerText || text).length,
      head: (answerText || text).slice(0, 800),
    },
    citations,
    sawTier,
    sawCitations,
    elapsedMs: Date.now() - t0,
    sendReady: !!sendBtn(),
  };
};

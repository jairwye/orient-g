/**
 * 单次 poll：流式是否结束 + 采样字段（Chrome DevTools 每 15–60s 调一次）。
 * loading/thinking 只看**最后一条助手消息**尾部，避免历史 trace 误判。
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

  const body = document.body?.innerText || "";
  const blocks = Array.from(
    document.querySelectorAll("main main div.flex.justify-start"),
  );
  const last = blocks[blocks.length - 1];
  const lastBlockText = (last?.innerText || "").trim();
  const lastTail = lastBlockText.slice(-900);

  const answerEl = last?.querySelector(".prose, .markdown") || last;
  const answerText = (answerEl?.innerText || "").trim();
  const answerBody = stripTrace(
    answerText
      .replace(/^执行过程\([^)]+\)\s*/m, "")
      .replace(/\n*（Hermes 流式超时或失败[^\n）]*）\s*/g, "")
      .trim(),
  );

  const thinking = /思考中…|同步中…/.test(lastTail);
  const hermesStillRunning = /Hermes 仍在执行|正在连接 Hermes|编排中…/.test(
    lastTail,
  );
  const loading =
    thinking ||
    hermesStillRunning ||
    (/连接流式通道|加载中/.test(lastTail) &&
      answerBody.length < 200 &&
      !/citations\s*[（(]\s*\d+/i.test(lastBlockText));

  const tierLine =
    (answerText.match(/执行过程\([^)]+\)/) ||
      body.match(/执行过程\([^)]+\)/) ||
      [])[0] || "";
  const citeMatch =
    lastBlockText.match(/citations\s*[（(]\s*(\d+)/i) ||
    answerText.match(/citations\s*[（(]\s*(\d+)/i);
  const citations = citeMatch ? parseInt(citeMatch[1], 10) : 0;
  const streamFail =
    /流式连接失败|502|Hermes 流式错误|后端服务不可用|深度编排失败/.test(
      lastBlockText + body.slice(-2000),
    );
  const honestMissing =
    /缺少证据|不确定|不确定\/缺少证据|未能获取|无法提取|无法进行对比|not available|does not contain|不含|永久限制|检索管道无法|未包含|无法回答/i.test(
      answerBody,
    );

  let streamDone = streamFail;
  if (citations > 0 && !loading && !thinking) streamDone = true;
  else if (
    !loading &&
    !thinking &&
    honestMissing &&
    answerBody.length >= 80 &&
    /Tier 0|本地证据/.test(tierLine)
  )
    streamDone = true;
  else if (
    !loading &&
    !thinking &&
    honestMissing &&
    answerBody.length >= 200 &&
    /Tier 1|标准/.test(tierLine)
  )
    streamDone = true;
  else if (
    !loading &&
    !thinking &&
    !hermesStillRunning &&
    answerBody.length >= 600 &&
    /Tier 2|深度/.test(tierLine)
  )
    streamDone = true;

  const thinkingInBody =
    /^思考中…|^同步中…/m.test(answerText) || /^思考中…|^同步中…/.test(answerBody);
  if (thinkingInBody) streamDone = false;
  if (/共 \d+ 步/.test(tierLine) && !/Tier [012]|深度|标准|本地证据/.test(tierLine)) {
    streamDone = false;
  }
  if (citations === 0 && /Tier [12]|深度|标准.*Hermes/.test(tierLine) === false && /共 \d+ 步/.test(tierLine)) {
    streamDone = false;
  }

  const inlineCite =
    /\[(?:doc_chunk|evidence_pack|document)/i.test(answerBody) ||
    /\bud_[a-f0-9]{16,32}\b/i.test(answerBody) ||
    /doc_id:\s*`/i.test(answerBody) ||
    /orientg_kb_ask/i.test(answerBody) ||
    /证据\s*`\s*`/.test(answerBody) ||
    /\(doc_id:\s*\)/i.test(answerBody);
  const processInAnswer =
    /用户要求|步骤：|让我先|我将尝试|预检索证据/i.test(answerBody);

  return {
    streamDone,
    streamFail,
    loading,
    thinking,
    hermesStillRunning,
    tier_line: tierLine,
    citations,
    extract: {
      hasMoney:
        /\d{1,3}(?:,\d{3})+\.\d{2}/.test(answerBody) ||
        /[\d,.]+万元/.test(answerBody) ||
        /[\d,.+-]+万/.test(answerBody) ||
        /\d+\.?\d*亿/.test(answerBody) ||
        /\d+元/.test(answerBody),
      honestMissing,
      hasTable:
        (answerBody.includes("2025") && answerBody.includes("2024")) ||
        /\|.*\|/.test(answerBody),
      badGap: false,
      badEst: /约\s*[\d,.]+万/.test(answerBody),
      badInlineCite: inlineCite,
      processInAnswer,
      len: answerBody.length,
      head: answerBody.slice(0, 800),
      streamFail,
    },
    agentReady: !!document.querySelector('[aria-label="智能体模式"]'),
    cap: localStorage.getItem("orientg.kb_scope_capsule.v1"),
  };
};

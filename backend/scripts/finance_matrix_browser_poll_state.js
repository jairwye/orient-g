/**
 * 单次 poll：流式是否结束 + 采样字段（Chrome DevTools 每 15–60s 调一次）。
 * loading/thinking 只看**最后一条助手消息**尾部，避免历史 trace 误判。
 */
() => {
  document.querySelectorAll("details").forEach((d) => {
    d.open = true;
  });

  const stripTrace = (text) =>
    (text || "")
      .split("\n")
      .filter((line) => {
        const t = line.trim();
        if (!t) return false;
        if (/^[›◇◈▸•]/.test(t)) return false;
        if (
          /^(已提交任务|Evidence Pack 已就绪|深度编排|正在连接|Hermes Runs|Hermes 仍在|KB 任务禁止|orientg-debugging|●完成：Tier|完成：Tier|模型：)/.test(
            t,
          )
        )
          return false;
        return true;
      })
      .join("\n")
      .trim();

  const pickPersonnelStructuredBody = (raw) => {
    const markers = [
      "YYCQ vs 可比公司A · 2025 人员结构对比",
      "YYCQ vs可比公司A",
      "YYCQ vs 可比公司A · 2025 人员结构对比",
      "人员结构对照",
    ];
    const t = raw || "";
    let idx = -1;
    for (const marker of markers) {
      const i = t.lastIndexOf(marker);
      if (i > idx) idx = i;
    }
    if (idx < 0) return null;
    // 若对照表前仍有取证独白，从对照表切开
    const pc = t.indexOf("人员结构对照", idx > 0 ? Math.max(0, idx - 80) : 0);
    const start = pc >= 0 && pc <= idx + 40 ? pc : idx;
    return t
      .slice(start)
      .replace(/^模型：[^\n]+\n/m, "")
      .replace(/●完成：Tier[^\n]+\n?/m, "")
      .trim();
  };

  const resolveReplaceFinalBody = (raw) => {
    const personnel = pickPersonnelStructuredBody(raw);
    if (personnel && /人员结构对照/.test(personnel)) {
      // 丢弃过程稿前缀已在 pick 内处理；勿再 head+tail 粘贴
      if (
        !/首轮取证|第二轮核证|撰写终稿|evidence_sufficient|next_action/i.test(
          personnel.slice(0, 120),
        )
      ) {
        return personnel.split(/引用证据/)[0].trim();
      }
    }
    const t = raw || "";
    const pcIdx = t.search(/人员结构对照/);
    if (
      pcIdx > 0 &&
      /首轮取证|第二轮核证|撰写终稿|evidence_sufficient|next_action|网关标记/i.test(
        t.slice(0, pcIdx),
      )
    ) {
      return t.slice(pcIdx).split(/引用证据/)[0].trim();
    }
    const tierIdx = t.indexOf("●完成：Tier");
    if (tierIdx < 0) return personnel;
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
    if (
      /首轮取证|第二轮核证|撰写终稿|evidence_sufficient|next_action|MCP\s*优先重试/i.test(
        head,
      )
    ) {
      if (tail.length >= 120 && /人员结构对照|1[,，]?378/.test(tail)) return tail;
      const cut = head.search(/人员结构对照/);
      if (cut >= 0) return head.slice(cut);
    }
    if (tail.length >= 200 && /1[,，]?378|\d{1,3}(?:,\d{3})+\.\d{2}/.test(tail)) {
      if (
        head.length >= 100 &&
        /人员结构对照/.test(head) &&
        !/首轮取证|撰写终稿|第二轮核证/i.test(head)
      ) {
        return `${head}\n\n${tail}`;
      }
      return tail;
    }
    if (head.length >= 150) return head;
    return tail.length >= 80 ? tail : personnel;
  };

  const stripOrchestration = (text) => {
    let t = text || "";
    const cnCut = t.search(
      /(?:人员结构对照|#\s*\S{1,40}\s*vs|YYCQ\s*vs\s*可比公司A)/,
    );
    if (
      cnCut > 0 &&
      /首轮取证|第二轮核证|现在可以撰写终稿|现在撰写终稿|evidence_sufficient|next_action|网关标记证据不充分|需要第二轮|MCP\s*优先重试/i.test(
        t.slice(0, cnCut),
      )
    ) {
      t = t.slice(cnCut).trim();
    }
    const anchor = /(?:^|\n)(结论[:：]|YYCQ vs 可比公司A|#+\s|存货|缺少证据|人员结构对照)/im;
    const m = anchor.exec(t);
    if (
      m &&
      m.index > 0 &&
      /Let me |The skill |Evidence Pack|Looking at the|doc_id:|首轮取证|第二轮核证|撰写终稿/i.test(
        t.slice(0, m.index),
      )
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
      const insufficientBubble =
        /证据不足|未给出合格|无法展示可靠对照|未完成可用终稿|Hermes未成稿/.test(
          cleaned,
        );
      const score =
        cleaned.length +
        ((/\|/.test(cleaned) || /\t[^\t]+\t/.test(cleaned)) &&
        /\d{2,}/.test(cleaned)
          ? 150
          : 0) +
        (/结论|研发人员|员工数量|1\.1信息-人员|人员结构对照|销售费用|对比分析/.test(
          cleaned,
        )
          ? 200
          : 0) -
        (insufficientBubble ? 800 : 0) -
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
  const traceBlob = Array.from(
    document.querySelectorAll('main ul li, [role="log"] ul li'),
    (el) => (el.innerText || "").trim(),
  ).join("\n");
  const searchBlob = `${body}\n${traceBlob}`;
  const blocks = Array.from(
    document.querySelectorAll("main main div.flex.justify-start"),
  );
  const last = pickBestAssistantBlock() || blocks[blocks.length - 1];
  const lastBlockText = (last?.innerText || "").trim();
  const completionMatch =
    lastBlockText.match(/[●•]?\s*完成：Tier\s*([012])[^·\n]*（([^）]+)）/) ||
    searchBlob.match(/[●•]?\s*完成：Tier\s*([012])[^·\n]*（([^）]+)）/);
  const tierFromComplete = completionMatch
    ? `Tier ${completionMatch[1]}（${completionMatch[2] || ""}）`.trim()
    : "";
  const completionIdx = lastBlockText.lastIndexOf("完成：Tier");
  const activeTail =
    completionIdx >= 0
      ? lastBlockText.slice(completionIdx).slice(-220)
      : lastBlockText.slice(-220);

  const answerEl = pickAnswerElement(last);
  const answerTextRaw = (answerEl?.innerText || "").trim();
  const personnelSlice = pickPersonnelStructuredBody(answerTextRaw);
  const finalSlice = resolveReplaceFinalBody(answerTextRaw);
  const answerText = finalSlice || answerTextRaw;
  const answerBody = stripOrchestration(
    stripTrace(
      answerText
        .replace(/^执行过程\([^)]+\)\s*/m, "")
        .replace(/\n*（Hermes 流式超时或失败[^\n）]*）\s*/g, "")
        .trim(),
    ),
  );

  const thinking = /思考中…|同步中…/.test(activeTail);
  const hermesStillRunning = /Hermes 仍在执行|正在连接 Hermes|编排中…/.test(
    activeTail,
  );
  const loading =
    thinking ||
    hermesStillRunning ||
    (/连接流式通道|加载中/.test(activeTail) &&
      answerBody.length < 200 &&
      !/citations\s*[（(]\s*\d+/i.test(lastBlockText));

  const completionLineMatch = searchBlob.match(/[●•]?\s*完成：Tier[^\n]+/);
  const tierLine =
    (completionLineMatch ? completionLineMatch[0].trim() : "") ||
    tierFromComplete ||
    (answerText.match(/执行过程\([^)]+\)/) ||
      body.match(/执行过程\([^)]+\)/) ||
      [])[0] ||
    "";
  const citeMatch =
    lastBlockText.match(/citations\s*[（(]\s*(\d+)/i) ||
    answerText.match(/citations\s*[（(]\s*(\d+)/i) ||
    body.match(/citations\s*[（(]\s*(\d+)/i);
  const citations = citeMatch ? parseInt(citeMatch[1], 10) : 0;
  const streamFailPattern =
    /流式连接失败|(?:HTTP\s*)?502\s|502 Bad Gateway|Hermes 流式错误|后端服务不可用|深度编排失败/;
  const streamFail = streamFailPattern.test(lastBlockText + body.slice(-2000));
  const honestMissing =
    /缺少证据|不确定\/缺少证据|未能获取|无法提取|无法进行对比|not available|does not contain|不含|永久限制|检索管道无法|无法回答|未披露|未进入.*索引|无法获取/i.test(
      answerBody,
    ) &&
    !/1[,，]?378|\b946\b|\b242\b|\b70\b|\d{1,3}(?:,\d{3})+\.\d{2}/.test(answerBody);

  let streamDone = streamFail;
  const completedTier = completionMatch ? completionMatch[1] || "" : "";
  const hasMoney =
    /\d{1,3}(?:,\d{3})+\.\d{2}/.test(answerBody) ||
    /[\d,.]+万元/.test(answerBody) ||
    /[\d,.+-]+万/.test(answerBody) ||
    /\d+\.?\d*亿/.test(answerBody) ||
    /\d+元/.test(answerBody);
  const processInAnswerEarly =
    /用户要求|步骤：|让我(?:先|通过|验证)|我将尝试|预检索证据|根据(?:已获取|检索结果|Evidence Pack)|很明确了|直接成稿如下|Evidence Pack中缺少|Let me search|I need to find|我需要(?:先|针对|查找).*?(?:MCP|检索|查找)|现在我需要(?:查找|检索|确认)|首轮检索返回|没有直接找到|更精确的检索|首轮取证|第二轮核证|现在可以撰写终稿|现在撰写终稿|evidence_sufficient|next_action\s*=|网关标记证据不充分|MCP\s*优先重试/i.test(
      answerBody,
    );
  const substantiveWithoutCites =
    hasMoney &&
    answerBody.length >= 400 &&
    !honestMissing &&
    !processInAnswerEarly;

  if (completionMatch && !loading && !thinking && !hermesStillRunning) {
    if (
      (completedTier === "1" || completedTier === "2") &&
      citations === 0 &&
      !honestMissing &&
      !substantiveWithoutCites
    ) {
      streamDone = false;
    } else if (
      answerBody.length >= 80 ||
      honestMissing ||
      substantiveWithoutCites
    ) {
      streamDone = true;
    } else {
      streamDone = false;
    }
  } else if (citations > 0 && !loading && !thinking && !hermesStillRunning) {
    if (
      answerBody.length >= 80 &&
      (!processInAnswerEarly || hasMoney || answerBody.length >= 350)
    ) {
      streamDone = true;
    }
  } else if (
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
    honestMissing &&
    answerBody.length >= 180 &&
    /Tier 2|深度/.test(tierLine)
  )
    streamDone = true;
  else if (
    !loading &&
    !thinking &&
    !hermesStillRunning &&
    honestMissing &&
    answerBody.length >= 180 &&
    /Tier 2|深度/.test(tierLine)
  )
    streamDone = true;

  const englishProcessOnly =
    /Let me |I need to find|The search results confirm/i.test(answerBody) &&
    !/^(结论|#+\s)/m.test(answerBody) &&
    !/\d{1,3}(?:,\d{3})+\.\d{2}/.test(answerBody) &&
    !honestMissing;
  if (englishProcessOnly) streamDone = false;

  const tierNeedsCites =
    completedTier === "1" ||
    completedTier === "2" ||
    /Tier [12]|深度|标准.*Hermes/.test(tierLine);
  if (streamDone && tierNeedsCites && citations === 0 && !honestMissing) {
    if (!substantiveWithoutCites) {
      streamDone = false;
    }
  }
  if (streamDone && answerBody.length < 60 && !honestMissing) {
    streamDone = false;
  }
  if (
    /本地 LLM 综合完成，正在输出正文/.test(activeTail) &&
    answerBody.length < 80 &&
    !/1[,，]?378|\b946\b|\b242\b|\d+\.\d{2}/.test(answerBody)
  ) {
    streamDone = false;
  }
  if (
    !!completionMatch &&
    !loading &&
    !thinking &&
    !hermesStillRunning &&
    answerBody.length < 80 &&
    !honestMissing
  ) {
    streamDone = false;
  }

  const thinkingInBody =
    /^思考中…|^同步中…/m.test(answerText) || /^思考中…|^同步中…/.test(answerBody);
  if (thinkingInBody) streamDone = false;
  if (/共 \d+ 步/.test(tierLine) && !/Tier [012]|深度|标准|本地证据/.test(tierLine)) {
    streamDone = false;
  }
  if (citations === 0 && /Tier [12]|深度|标准.*Hermes/.test(tierLine) === false && /共 \d+ 步/.test(tierLine)) {
    streamDone = false;
  }

  if (streamDone && processInAnswerEarly && !hasMoney && answerBody.length < 400) {
    streamDone = false;
  }
  // 手测同路径：DOM 原文仍含取证独白+对照表 → 未收束（须等 replace_reply 清洗）
  const rawDualDraft =
    /人员结构对照/.test(answerTextRaw) &&
    /首轮取证|第二轮核证|现在可以撰写终稿|现在撰写终稿|evidence_sufficient|next_action\s*=|MCP\s*优先重试/i.test(
      answerTextRaw,
    );
  if (rawDualDraft) {
    streamDone = false;
  }
  if (
    streamDone &&
    /思考中|同步中|现在我已经获取|让我用正确的参数|让我整理成对比/.test(answerBody) &&
    !/人员结构对照/.test(answerBody)
  ) {
    streamDone = false;
  }

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

  const bodyForMetrics = stripCiteFooter(answerBody);
  const bodyForCite = bodyForMetrics;
  if (streamDone && /加载中…?\s*$/.test(bodyForMetrics)) {
    streamDone = false;
  }
  const inlineCite =
    /\[(?:doc_chunk|evidence_pack|document)/i.test(bodyForCite) ||
    /\bud_[a-f0-9]{16,32}\b/i.test(bodyForCite) ||
    /doc_id:\s*`/i.test(bodyForCite) ||
    (/orientg_kb_ask/i.test(bodyForCite) &&
      !/not available|不可用|does not contain|未.*披露/i.test(bodyForCite)) ||
    /证据\s*`\s*`/.test(bodyForCite) ||
    /\(doc_id:\s*\)/i.test(bodyForCite);
  const processInAnswer =
    /用户要求|步骤：|让我(?:先|通过|验证)|我将尝试|预检索证据|根据(?:已获取|检索结果|Evidence Pack)|很明确了|直接成稿如下|Evidence Pack中缺少|Let me search|I need to find|我需要(?:先|针对|查找).*?(?:MCP|检索|查找)|现在我需要(?:查找|检索|确认)|首轮检索返回|没有直接找到|更精确的检索|首轮取证|第二轮核证|现在可以撰写终稿|现在撰写终稿|evidence_sufficient|next_action\s*=|网关标记证据不充分|MCP\s*优先重试/i.test(
      answerBody,
    );

  const agentIdleNoReply =
    !!document.querySelector('[aria-label="智能体模式"]') &&
    answerBody.length === 0 &&
    !loading &&
    !thinking &&
    !hermesStillRunning &&
    /描述任务即可/.test(body);

  const prefetchKbHits = (searchBlob.match(/预检索：orientg_kb_ask/g) || []).length;
  const gateway_kb_from_trace = prefetchKbHits > 0 ? prefetchKbHits : null;
  const gatewayKbMatch = searchBlob.match(
    /(?:网关 orientg_kb_ask|Orient-G 网关 KB)\s*×(\d+)/,
  );
  const hermesKbMatch = searchBlob.match(/Hermes 内 orientg_kb_ask ×(\d+)/);
  const hermes_kb_ask_calls = hermesKbMatch
    ? parseInt(hermesKbMatch[1], 10)
    : null;
  const gateway_kb_ask_calls = gatewayKbMatch
    ? parseInt(gatewayKbMatch[1], 10)
    : gateway_kb_from_trace;
  const orientg_kb_ask_calls =
    (hermes_kb_ask_calls || 0) + (gateway_kb_ask_calls || 0) || null;
  const replySourceMatch = searchBlob.match(
    /终稿出处[：:]\s*(Hermes|Orient-G门禁|Orient-G补检索)/,
  );
  let reply_source = null;
  let structured_gate_applied = null;
  if (replySourceMatch) {
    const label = replySourceMatch[1];
    if (label === "Hermes") reply_source = "hermes";
    else if (label === "Orient-G门禁") {
      reply_source = "orientg_structured_gate";
      structured_gate_applied = true;
    } else if (label === "Orient-G补检索") reply_source = "orientg_supplemental";
  }
  // 含「未调 MCP 补检索 / 自动执行定向 orientg_kb_ask」链（手测毁流路径）
  const kb_supplemental =
    /Orient-G 自动补检索修订|自动执行定向\s*orientg_kb_ask|Hermes 未调用 MCP 补检索/.test(
      searchBlob,
    );
  // 宽尺子 B：强制 MCP 重试可观测（理想 = 0）
  let hermes_mcp_retry_count = 0;
  if (/MCP 优先重试|hermes_mcp_retry|未调用 orientg_kb_ask，发起/.test(searchBlob)) {
    hermes_mcp_retry_count = 1;
  }
  const retryCountMatch = searchBlob.match(/hermes_mcp_retry(?:_count)?\s*[:=]\s*(\d+)/i);
  if (retryCountMatch) {
    hermes_mcp_retry_count = parseInt(retryCountMatch[1], 10);
  }

  const personnelCompareQuery =
    /对比分析YYCQ和可比公司A|YYCQ vs 可比公司A|对比.*人员结构/i.test(
      body + answerTextRaw,
    );

  // 目标3：不再等待 Orient-G gate 刷完整表；Hermes 主写骨架就绪即可（通用分项数字，禁硬编码）。
  const personnelHermesSkeletonReady =
    /人员结构对照/.test(answerBody) &&
    /对比分析/.test(answerBody) &&
    /(研发|运营|销售|管理).{0,24}\d{2,}/.test(answerBody) &&
    (answerBody.match(/\d{2,}/g) || []).length >= 3 &&
    !/doc_id:\s*[`\s,)]{0,4}/i.test(answerBody);
  const hermesAuthorshipLine = /终稿出处[：:]\s*Hermes/.test(searchBlob);
  const personnelReplacePending =
    personnelCompareQuery &&
    !personnelHermesSkeletonReady &&
    !hermesAuthorshipLine &&
    (!personnelSlice ||
      /139人的22\.6倍|22\.6\s*倍|核心指标对比/.test(answerBody));
  if (streamDone && personnelReplacePending) {
    streamDone = false;
  }
  // Spec 4.3：销售/运营仍「证据未覆盖」时不得判完成（避免过早 streamDone）
  const peerRolesStillUncovered =
    personnelCompareQuery &&
    /证据未覆盖/.test(answerBody) &&
    /(销售|运营).{0,40}证据未覆盖|证据未覆盖.{0,40}(销售|运营)/.test(answerBody);
  if (streamDone && peerRolesStillUncovered) {
    streamDone = false;
  }
  // 流已静默且 Hermes 骨架/出处就绪：勿因缺 citations DOM 或短骨架（~180–280 字）永久卡住
  if (
    personnelCompareQuery &&
    !loading &&
    !thinking &&
    !hermesStillRunning &&
    answerBody.length >= 160 &&
    (personnelHermesSkeletonReady || hermesAuthorshipLine) &&
    !peerRolesStillUncovered
  ) {
    streamDone = true;
  }

  const personnelFinalReady =
    !!personnelSlice &&
    /人员结构对照/.test(answerBody) &&
    citations > 0 &&
    !!completionMatch &&
    !personnelReplacePending;
  if (personnelFinalReady && !loading && !thinking && !hermesStillRunning) {
    streamDone = true;
  }

  const personnelStructuredReady =
    /人员结构对照/.test(answerBody) &&
    /(研发|运营|销售|管理).{0,24}\d{2,}/.test(answerBody) &&
    (answerBody.match(/\d{2,}/g) || []).length >= 4 &&
    /对比分析|口径说明/.test(answerBody) &&
    bodyForMetrics.length >= 400 &&
    !personnelReplacePending &&
    !thinking;

  const personnelEarlyStructured =
    personnelStructuredReady &&
    (hermesStillRunning || /执行过程\(共 \d+ 步\)/.test(tierLine));

  if (personnelStructuredReady && (!loading || personnelEarlyStructured)) {
    streamDone = true;
  }

  const generalDeepFinalReady =
    !!finalSlice &&
    !personnelSlice &&
    citations > 0 &&
    !!completionMatch &&
    (/\d{1,3}(?:,\d{3})+\.\d{2}/.test(finalSlice) ||
      (/\|/.test(finalSlice) && /\d/.test(finalSlice)) ||
      (finalSlice.length >= 200 && /[\u4e00-\u9fff]/.test(finalSlice))) &&
    !loading &&
    !thinking &&
    !hermesStillRunning;
  if (generalDeepFinalReady) {
    streamDone = true;
  }

  const personnelSingleReady =
    !personnelCompareQuery &&
    !personnelReplacePending &&
    !/共 \d+ 步/.test(tierLine) &&
    /研发人员情况|1\.1信息-人员|员工数量、专业构成/.test(answerTextRaw) &&
    /1[,，]?378|\b946\b|\b242\b|\b70\b|\d+\.\d{2}/.test(answerBody) &&
    answerBody.length >= 120 &&
    !thinking;
  if (personnelSingleReady && !loading && !hermesStillRunning) {
    streamDone = true;
  }

  const fastPersonnelBodyReady =
    /Tier 0|本地证据/.test(tierLine) &&
    citations > 0 &&
    answerBody.length >= 120 &&
    /1[,，]?378|\b946\b|\b242\b|\d+\.\d{2}/.test(answerBody) &&
    !loading &&
    !thinking &&
    !hermesStillRunning;
  if (fastPersonnelBodyReady) {
    streamDone = true;
  }

  return {
    streamDone,
    streamFail:
      ((streamFail &&
        !personnelFinalReady &&
        !generalDeepFinalReady &&
        !personnelStructuredReady &&
        !personnelEarlyStructured) ||
        agentIdleNoReply),
    loading,
    thinking,
    hermesStillRunning,
    agentIdleNoReply,
    tier_line: tierLine,
    citations,
    hermes_kb_ask_calls,
    gateway_kb_ask_calls,
    orientg_kb_ask_calls,
    reply_source,
    structured_gate_applied,
    kb_supplemental,
    hermes_mcp_retry_count,
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
      badEst:
        (/约\s*[\d,.]+万/.test(bodyForMetrics) &&
          !/\d{1,3}(?:,\d{3})+\.\d{2}/.test(bodyForMetrics)) ||
        (/约\s*[\d,.]+/.test(bodyForMetrics) &&
          /\d{1,3}(?:,\d{3})+\.\d{2}/.test(bodyForMetrics) &&
          !/占比(?:约)?\d+(?:\.\d+)?%/.test(bodyForMetrics) &&
          !/1[,，]?378|1378/.test(bodyForMetrics)),
      badInlineCite: inlineCite,
      processInAnswer,
      len: bodyForMetrics.length,
      head: bodyForMetrics.slice(0, 800),
      streamFail:
        streamFail &&
        !personnelFinalReady &&
        !generalDeepFinalReady &&
        !personnelStructuredReady &&
        !personnelEarlyStructured,
    },
    agentReady: !!document.querySelector('[aria-label="智能体模式"]'),
    cap: (() => {
      try {
        return localStorage.getItem("orientg.kb_scope_capsule.v1");
      } catch (e) {
        return null;
      }
    })(),
  };
};

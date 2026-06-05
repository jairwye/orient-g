/**
 * 单次轮询：流式是否结束（Chrome DevTools MCP 每 15s 调一次，禁止长循环）。
 * 完毕条件（任一）：
 *  - citations(N) + 发送可点 + 非加载中
 *  - Tier 标签 + 发送可点 + 非加载中 + (citations 或 诚实缺证/正文≥120)
 *  - 页面含流式错误/502 提示
 */
() => {
  const body = document.body?.innerText || "";
  const sendReady = !!Array.from(document.querySelectorAll("button")).find(
    (b) => b.getAttribute("aria-label") === "发送" && !b.disabled,
  );
  const loading =
    body.includes("加载中") ||
    body.includes("思考中…") ||
    body.includes("连接流式通道") ||
    Array.from(document.querySelectorAll("button")).some(
      (b) => (b.textContent || "").includes("加载") && b.disabled,
    );
  const tierLine = (body.match(/执行过程\([^)]+\)/) || [])[0] || "";
  const blocks = Array.from(
    document.querySelectorAll("main main div.flex.justify-start"),
  );
  const last = blocks[blocks.length - 1];
  const answerEl = last?.querySelector(".prose, .markdown") || last;
  const answerText = (answerEl?.innerText || "").trim();
  const citeMatch = answerText.match(/citations\s*[（(]\s*(\d+)/i);
  const citations = citeMatch ? parseInt(citeMatch[1], 10) : 0;
  const honestMissing = /缺少证据|不确定\/缺少证据/.test(answerText || body);
  const hasMoney = /\d{1,3}(?:,\d{3})+\.\d{2}/.test(answerText || body);
  const streamFail =
    /流式连接失败|502|Hermes 流式错误|未返回正文/.test(body);

  const thinking = body.includes("思考中…") || body.includes("同步中…");
  const sendIdle = sendReady || citations > 0;

  let streamDone = false;
  if (streamFail) streamDone = true;
  else if (citations > 0 && !loading && !thinking) streamDone = true;
  else if (
    tierLine &&
    sendIdle &&
    !loading &&
    !thinking &&
    (citations > 0 || honestMissing || (answerText.length >= 120 && hasMoney))
  )
    streamDone = true;

  return {
    streamDone,
    streamFail,
    sendReady,
    loading,
    tierLine,
    citations,
    answerLen: answerText.length,
    hasMoney,
    honestMissing,
    answerHead: answerText.slice(0, 400),
  };
};

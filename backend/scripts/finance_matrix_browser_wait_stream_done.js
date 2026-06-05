/**
 * Chrome DevTools MCP：发送后须等 LLM/Hermes 流式输出完毕再采样/下一条。
 * evaluate_script function 体；maxWaitMs 嵌入调用方。
 */
async () => {
  const maxWaitMs = 900000;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const t0 = Date.now();

  const sendReady = () =>
    !!Array.from(document.querySelectorAll("button")).find(
      (b) => b.getAttribute("aria-label") === "发送" && !b.disabled,
    );
  const isLoading = () => {
    const body = document.body?.innerText || "";
    if (body.includes("加载中")) return true;
    return Array.from(document.querySelectorAll("button")).some(
      (b) => (b.textContent || "").includes("加载") && b.disabled,
    );
  };
  const hasCitations = () => {
    const body = document.body?.innerText || "";
    return /citations\s*[（(]\s*\d+/i.test(body);
  };

  while (Date.now() - t0 < maxWaitMs) {
    await sleep(2000);
    if (hasCitations() && sendReady() && !isLoading()) {
      return {
        ok: true,
        elapsedMs: Date.now() - t0,
        sendReady: true,
        citations: true,
        loading: false,
      };
    }
  }

  return {
    ok: false,
    err: "stream not finished within timeout",
    elapsedMs: Date.now() - t0,
    sendReady: sendReady(),
    citations: hasCitations(),
    loading: isLoading(),
  };
};

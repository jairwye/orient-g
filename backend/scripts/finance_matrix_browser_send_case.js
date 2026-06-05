/**
 * 发送单条矩阵用例（不等待）。modeLabel/query 须由调用方嵌入字面量（勿用 args 传长串）。
 * 快速档：先填问句 → 点「快速」等 1.5s → 发送。
 */
async (modeLabel, query) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
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
      await sleep(label === "快速" ? 1500 : 300);
    }
  };

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

  const send = Array.from(document.querySelectorAll("button")).find(
    (b) => b.getAttribute("aria-label") === "发送" && !b.disabled,
  );
  if (!send) return { ok: false, err: "send disabled" };
  send.click();
  return { ok: true, mode: modeLabel, queryHead: String(query).slice(0, 48) };
};

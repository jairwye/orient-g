/**
 * 矩阵页初始化：folder 胶囊 + 等待智能体视图就绪（Chrome DevTools evaluate_script 嵌入）。
 * folderId 须字面量嵌入，勿用 args。
 */
async (folderId) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  localStorage.setItem(
    "orientg.kb_scope_capsule.v1",
    JSON.stringify({
      folder_ids: [folderId],
      collection_ids: [],
      table_ids: [],
      updated_at: Date.now(),
    }),
  );
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline) {
    const group = document.querySelector('[aria-label="智能体模式"]');
    let cap = {};
    try {
      cap = JSON.parse(
        localStorage.getItem("orientg.kb_scope_capsule.v1") || "{}",
      );
    } catch {
      cap = {};
    }
    const hasFolder = (cap.folder_ids || []).includes(folderId);
    if (group && hasFolder) {
      return { ok: true, hasMode: true, cap: JSON.stringify(cap) };
    }
    const nav = Array.from(document.querySelectorAll("nav button")).find(
      (b) => b.textContent?.trim() === "智能体",
    );
    if (nav && !group) nav.click();
    await sleep(800);
  }
  return { ok: false, err: "agent view not ready" };
};

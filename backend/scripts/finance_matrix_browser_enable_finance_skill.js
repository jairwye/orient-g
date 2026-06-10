/**
 * 矩阵实测：勾选 skill.finance.annual_report.v1（竞品财报 KB 路由）。
 * 须在智能体视图就绪后调用；Chrome DevTools evaluate_script 嵌入字面量。
 */
async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const SKILL_LABEL = "年报财务分析";
  const pop = document.getElementById("ai-skills-popover");
  const openSkills = () => {
    const btn = Array.from(document.querySelectorAll("button")).find(
      (b) => b.getAttribute("title") === "技能",
    );
    if (btn) btn.click();
  };
  if (!pop) {
    openSkills();
    await sleep(400);
  }
  const labels = Array.from(document.querySelectorAll("#ai-skills-popover label"));
  const target = labels.find((l) => l.textContent?.includes(SKILL_LABEL));
  if (!target) {
    return { ok: false, err: "finance skill label not found" };
  }
  const cb = target.querySelector('input[type="checkbox"]');
  if (!cb) return { ok: false, err: "no checkbox" };
  if (!cb.checked) {
    cb.click();
    await sleep(200);
  }
  return { ok: true, checked: cb.checked, label: target.textContent?.trim()?.slice(0, 40) };
};

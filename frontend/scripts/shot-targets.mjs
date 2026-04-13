import { chromium } from "playwright";

const url =
  process.argv[2] ||
  "http://localhost:3000/targets/21494320?snapshot_name=2026-04-10_run1&min_pct=0&max_depth=10&max_nodes=5000";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1536, height: 864 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  // 等待 mermaid 渲染与二次聚焦
  await page.waitForTimeout(3500);
  await page.screenshot({ path: "shot-targets.png", fullPage: false });
  await browser.close();
  console.log("saved shot-targets.png");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});


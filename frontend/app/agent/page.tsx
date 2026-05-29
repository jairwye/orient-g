"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { UI_AGENT } from "../lib/ui_labels";

/** 兼容旧链接 /agent → AI 互动内智能体视图 */
export default function AgentRedirectPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const q = new URLSearchParams(searchParams.toString());
    q.set("view", "agent");
    router.replace(`/ai-interaction?${q.toString()}`);
  }, [router, searchParams]);

  return (
    <div className="flex min-h-[40vh] items-center justify-center text-sm text-zinc-500">
      {UI_AGENT.redirectMessage}
    </div>
  );
}

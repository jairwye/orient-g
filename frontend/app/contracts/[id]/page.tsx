"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { PageDevInProgressNotice } from "../../components/PageDevInProgressNotice";
import { getAuthHeaders } from "../../lib/auth";

type ContractDetail = {
  contract_id: string;
  doc_id: string;
  original_filename: string;
  extracted?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export default function ContractDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id || "";
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ContractDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    async function load() {
      setLoading(true);
      setErr(null);
      try {
        const res = await fetch(`/api/contracts/${encodeURIComponent(id)}`, { credentials: "include", headers: getAuthHeaders() });
        const d = (await res.json().catch(() => ({}))) as ContractDetail & { detail?: string };
        if (!res.ok) throw new Error(typeof d.detail === "string" ? d.detail : "加载失败");
        if (!stop) setData(d);
      } catch (e) {
        if (!stop) setErr(e instanceof Error ? e.message : "加载失败");
      } finally {
        if (!stop) setLoading(false);
      }
    }
    if (id) load();
    return () => {
      stop = true;
    };
  }, [id]);

  return (
    <div className="p-6 md:p-8">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Link href="/contracts" className="text-sm text-zinc-400 hover:text-zinc-200">
          ← 合同台账
        </Link>
        <Link href="/ai-interaction" className="ml-auto text-sm text-zinc-400 hover:text-zinc-200">
          去 AI内网 →
        </Link>
      </div>

      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">合同详情</h1>
        <p className="mt-1 text-sm text-zinc-500">本版仅做最小可追溯信息，字段后续细化。</p>
        <div className="mt-3 max-w-3xl">
          <PageDevInProgressNotice />
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        {loading ? <p className="text-sm text-zinc-500">加载中…</p> : null}
        {err ? <p className="text-sm text-red-400">{err}</p> : null}
        {data && !loading && !err ? (
          <div className="space-y-4">
            <div className="text-sm text-zinc-300">
              <div>
                文件：<span className="text-zinc-100">{data.original_filename || "-"}</span>
              </div>
              <div className="mt-1 font-mono text-xs text-zinc-500">
                contract_id={data.contract_id} · doc_id={data.doc_id}
              </div>
              <div className="mt-1 text-xs text-zinc-500">
                created_at={data.created_at || "-"} · updated_at={data.updated_at || "-"}
              </div>
            </div>
            <div>
              <div className="mb-2 text-sm font-medium text-zinc-200">extracted（占位）</div>
              <pre className="whitespace-pre-wrap rounded border border-zinc-800 bg-zinc-950/40 p-4 text-xs text-zinc-200">
                {JSON.stringify(data.extracted || {}, null, 2)}
              </pre>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}


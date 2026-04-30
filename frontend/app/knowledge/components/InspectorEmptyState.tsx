"use client";

export function InspectorEmptyState() {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
      <h2 className="text-lg font-medium text-zinc-200">管理面板</h2>
      <p className="mt-2 text-sm text-zinc-500">选择一条文档查看详情；或勾选多条进行批量操作。</p>
    </section>
  );
}


export default function ExchangePage() {
  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">汇率变动趋势</h1>
        <p className="mt-1 text-sm text-zinc-500">由负责汇率模块的员工维护。</p>
      </div>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-8">
        <div className="flex min-h-[40vh] items-center justify-center rounded-lg border border-dashed border-zinc-700 text-zinc-500">
          细致页占位，待接入 ECharts 时序图与完整数据接口。
        </div>
      </div>
    </div>
  );
}

export default function KnowledgePage() {
  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">知识库</h1>
        <p className="mt-1 text-sm text-zinc-500">展位页，后续可接入外部知识库与内部知识库。</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-2 text-lg font-medium text-zinc-200">外部知识库</h2>
          <p className="mb-4 text-sm text-zinc-500">
            公网或对外文档、行业资料等，待后续接入检索与展示。
          </p>
          <div className="flex min-h-[24vh] items-center justify-center rounded-lg border border-dashed border-zinc-700 text-zinc-500 text-sm">
            展位占位，待接入外部知识库。
          </div>
        </section>

        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-2 text-lg font-medium text-zinc-200">内部知识库</h2>
          <p className="mb-4 text-sm text-zinc-500">
            内网文档、制度与内部资料等，待后续接入检索与展示。
          </p>
          <div className="flex min-h-[24vh] items-center justify-center rounded-lg border border-dashed border-zinc-700 text-zinc-500 text-sm">
            展位占位，待接入内部知识库。
          </div>
        </section>
      </div>
    </div>
  );
}

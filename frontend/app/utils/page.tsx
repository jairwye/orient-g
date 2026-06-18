import Link from "next/link";
import { ClipboardList, FileText, LayoutGrid } from "lucide-react";
import { KbInProgressBanner } from "../components/KbInProgressBanner";
import { WORKFLOW_WIP_CLASS } from "../lib/business_chart_colors";

const tools = [
  {
    href: "/utils/pdf-knowledge",
    label: "大 PDF 生知识库用文档工具",
    description: "大 PDF 生成知识库用文档。",
    icon: FileText,
  },
  {
    href: "/utils/process-doc",
    label: "流程文档工具",
    description: "自然语言生成标准财务流程文档，可编辑规则并同步飞书。",
    icon: ClipboardList,
    wip: true,
  },
  {
    href: "/utils/excel-kanban",
    label: "数据解析",
    description: "上传 Excel 生成看板与解读，支持自然语言问答、按需生图/生表。",
    icon: LayoutGrid,
    wip: true,
  },
];

export default function UtilsPage() {
  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">实用工具</h1>
        <p className="mt-1 text-sm text-zinc-500">流程文档、PDF 知识库、Excel 看板等实用 AI 工具入口。</p>
      </div>
      <div className="mb-4 max-w-3xl">
        <KbInProgressBanner />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {tools.map(({ href, label, description, icon: Icon, wip }) => (
          <Link
            key={href}
            href={href}
            className={[
              "flex flex-col rounded-lg p-5 transition-colors",
              wip
                ? WORKFLOW_WIP_CLASS.cardBorder
                : "border border-zinc-800 bg-zinc-900/50 hover:border-zinc-700 hover:bg-zinc-900",
            ].join(" ")}
          >
            <Icon className={`mb-3 h-8 w-8 ${wip ? "text-zinc-500" : "text-zinc-400"}`} />
            <div className="flex flex-wrap items-center gap-2">
              <h2 className={`text-sm font-medium ${wip ? WORKFLOW_WIP_CLASS.listTitle : "text-zinc-200"}`}>{label}</h2>
              {wip ? <span className={WORKFLOW_WIP_CLASS.badge}>开发中</span> : null}
            </div>
            <p className="mt-1 text-xs text-zinc-500">{description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}

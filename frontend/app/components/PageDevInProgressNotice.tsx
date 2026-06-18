import { WORKFLOW_WIP_CLASS } from "../lib/business_chart_colors";

type Props = {
  children?: React.ReactNode;
};

/** 整页「开发中」提示条（与 AI 内网工作流 WIP 同色系） */
export function PageDevInProgressNotice({ children }: Props) {
  return (
    <div className={WORKFLOW_WIP_CLASS.pageBanner}>
      <span className={WORKFLOW_WIP_CLASS.badge}>开发中</span>
      <span>{children ?? "本页功能仍在完善，部分能力尚不可用。"}</span>
    </div>
  );
}

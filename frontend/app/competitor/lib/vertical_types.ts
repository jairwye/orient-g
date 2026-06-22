export type VerticalReportBlock =
  | { kind: "narrative"; anchor?: string; markdown: string }
  | {
      kind: "table";
      anchor?: string;
      headers: string[];
      header_keys?: string[];
      rows: Record<string, string | number | null>[];
    };

export type VerticalReportSection = {
  id: string;
  title: string;
  blocks: VerticalReportBlock[];
};

export type VerticalReportCompany = {
  id: string;
  snap_id: string;
  name: string;
  /** 按 ### 一、二、… 分节 */
  sections: VerticalReportSection[];
  /** 兼容：全公司 blocks 扁平列表 */
  blocks: VerticalReportBlock[];
};

export type VerticalReportSnapshot = {
  version: number;
  meta: {
    title?: string;
    parser_version?: string;
    company_count?: number;
  };
  intro?: VerticalReportBlock[];
  companies: VerticalReportCompany[];
  warnings?: string[];
};

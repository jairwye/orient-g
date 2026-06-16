export type TableBlock = {
  kind: "table";
  anchor: string;
  headers: string[];
  rows: Record<string, string | number | null>[];
};

export type NarrativeBlock = {
  kind: "narrative";
  anchor?: string;
  markdown: string;
};

export type ReportBlock = TableBlock | NarrativeBlock;

export type CompetitorSection = {
  id: string;
  title: string;
  blocks: ReportBlock[];
};

export type CompetitorReportSnapshot = {
  version: 1;
  meta: {
    title: string;
    period: string;
    currency_unit: string;
    company_count: number;
    source_filename: string;
    uploaded_at: string;
    uploaded_by: string;
    parser_version: string;
    data_source?: "fixture" | "upload";
  };
  companies: Array<{ id: string; label: string; short?: string; color?: string }>;
  sections: CompetitorSection[];
  warnings: string[];
};

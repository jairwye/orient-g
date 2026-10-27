export type TableBlock = {
  kind: "table";
  anchor: string;
  headers: string[];
  header_keys?: string[];
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

export type CompetitorEditionKind = "annual" | "interim";

/** GET /api/competitor/editions 单项 */
export type CompetitorEdition = {
  edition_id: string;
  kind: CompetitorEditionKind | string;
  period_label: string;
  has_vertical: boolean;
  is_current?: boolean;
  has_snapshot?: boolean;
  title?: string;
  uploaded_at?: string;
  notes?: string;
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
    edition_id?: string;
    kind?: CompetitorEditionKind | string;
    period_label?: string;
  };
  companies: Array<{ id: string; label: string; short?: string; color?: string }>;
  sections: CompetitorSection[];
  warnings: string[];
};

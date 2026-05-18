// ai-interaction 页面的类型定义（从 page.tsx 提取以减少单文件体积、加速编译）
export type Citation = Record<string, unknown>;

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  deny_reason?: string;
  chart_spec?: Record<string, unknown> | null;
  table_spec?: { columns: string[]; rows: string[][] } | null;
};

export type ComposerAttachment = {
  localId: string;
  name: string;
  size: number;
  phase: "uploading" | "done" | "error";
  progress: number;
  docId?: string;
  error?: string;
  kind?: "kb_doc" | "excel_parse";
  dataParseSessionId?: string;
};

export type ChatSession = {
  id: string;
  title: string;
  updated_at: number;
  messages: ChatMessage[];
  attachments?: Array<Omit<ComposerAttachment, "phase" | "progress"> & { phase: "done" | "error"; progress?: number }>;
  data_parse_session_id?: string | null;
  active_workflow_id?: string | null;
  enabled_skills?: string[];
  enabled_tools?: string[];
  enabled_prompt_ids?: string[];
  start_area_hint?: string | null;
};

export type SkillConfig = {
  id: string;
  label: string;
  description?: string;
  trigger_hint?: string;
  example?: string;
};

export type SkillCatalogDoc = {
  id: string;
  name: string;
  description: string;
  body_markdown: string;
  raw_markdown: string;
};

export type ToolConfig = {
  id: string;
  label: string;
  description?: string;
};

export type WorkflowConfig = {
  id: string;
  label: string;
  description?: string;
  example_prompt?: string;
  start_hint?: string;
  default_enabled_prompt_ids?: string[];
  default_enabled_skill_ids?: string[];
  default_enabled_tool_ids?: string[];
};

export type PromptConfig = {
  id: string;
  label: string;
  description?: string;
  role?: string;
  scope?: string;
  summary?: string;
  body?: string;
};

export type KnowledgeCollection = {
  collection_id: string;
  space_type: string;
  name: string;
  type: "private" | "department" | "public" | "project";
  department_id?: string;
  project_id?: string;
  owner_user_id?: string;
};

export type KnowledgeTable = {
  table_id: string;
  collection_id: string;
  space_type: string;
  name: string;
  row_count: number;
};

export type KnowledgeFolder = {
  folder_id: string;
  name: string;
  collection_ids: string[];
};

export type KnowledgeOptionsResponse = {
  collections: KnowledgeCollection[];
  tables: KnowledgeTable[];
  folders: KnowledgeFolder[];
  default_selected_collection_ids: string[];
  default_selected_table_ids: string[];
  default_selected_folder_ids: string[];
};

export type AskResponse = {
  denied?: boolean;
  deny_reason?: string;
  detail?: string;
  reply?: string;
  citations?: Citation[];
  llm_model?: string;
};

export type ChartSpecLike = {
  xAxis?: { data?: string[] };
  series?: Array<{
    name?: string;
    type?: string;
    data?: number[];
  }>;
};

// ai-interaction 页面的类型定义（从 page.tsx 提取以减少单文件体积、加速编译）
export type Citation = Record<string, unknown>;

/** Agent 页 KB 分流：快速 / 标准 / 深度 */
export type AgentMode = "fast" | "standard" | "deep";

export type AgentTraceStep = {
  at: number;
  kind: "status" | "tool" | "thinking" | "error" | "meta";
  message: string;
  step?: string;
  /** Hermes `hermes.tool.progress` 关联 id */
  toolCallId?: string;
  toolStatus?: "running" | "completed";
  emoji?: string;
  /** Hermes 工具名（如 terminal、orientg_kb_ask） */
  tool?: string;
};

/** SSE `evidence_pack` 精简字段（与后端 pack_summary_for_sse 一致） */
export type EvidencePackSummary = {
  task_type?: string;
  gaps?: string[];
  coverage_score?: number;
  retrieval_queries?: string[];
};

export type HermesStreamStats = {
  thinking_chars?: number;
  delta_chars?: number;
  tool_progress_events?: number;
  tool_call_events?: number;
  orientg_kb_ask_calls?: number;
  /** Orient-G 网关在 Hermes 完成后执行的补检索次数 */
  orientg_kb_supplemental_calls?: number;
};

export type AgentMeta = {
  agent_route?: string;
  /** 0=Tier0 本地综合 | 1=hermes_lite | 2=hermes_full */
  agent_tier?: number;
  evidence_pack?: EvidencePackSummary;
  hermes_used?: boolean;
  kb_fast_path?: boolean;
  hermes_fallback?: boolean;
  /** Hermes 流式 error 后 salvage 过程稿为终稿（非本地 synth） */
  hermes_salvaged?: boolean;
  synthesis?: string;
  llm_model?: string;
  /** Hermes 流式通道：chat_completions | runs */
  hermes_stream_mode?: string;
  hermes_stream_stats?: HermesStreamStats;
  kb_supplemental?: boolean;
  supplemental_adopted?: boolean;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  /** @deprecated 使用 agentTrace；保留读取旧会话 */
  streamStatus?: string[];
  /** Agent 执行过程（流式追加，完成后保留于历史） */
  agentTrace?: AgentTraceStep[];
  /** Hermes / 模型 reasoning 流（同步展示在气泡内） */
  agentReasoning?: string;
  agentMeta?: AgentMeta;
  /** 对话页 RAG：检索摘要（与 Agent pack 同结构） */
  evidence_pack?: EvidencePackSummary;
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
  /** chat=普通对话；agent=Agent（/api/agent/chat） */
  session_mode?: "chat" | "agent";
  /** Agent 多轮时 Hermes 会话 id（仅 session_mode=agent） */
  hermes_session_id?: string | null;
  /** 列表展示顺序（创建时间），切换/激活会话时不应改动 */
  created_at?: number;
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
  doc_count?: number;
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
  doc_count?: number;
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
  read_mode?: string;
  evidence_pack?: EvidencePackSummary;
};

export type ChartSpecLike = {
  xAxis?: { data?: string[] };
  series?: Array<{
    name?: string;
    type?: string;
    data?: number[];
  }>;
};

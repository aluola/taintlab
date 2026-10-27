export type Mode = 'none' | 'input_filter' | 'taint_policy' | 'policy_only';
export type Page = 'chat' | 'attacks' | 'results';
export type JsonObject = Record<string, unknown>;
export interface DocumentInfo {
  doc_id: string; name: string; source_type?: string; integrity?: string;
  sensitivity: string; content_hash?: string; characters?: number;
  warnings?: string[]; label_basis?: string; description?: string;
}
export interface Recipient { recipient_id: string; name?: string; label?: string; sensitivity?: string; max_sensitivity?: string; private?: boolean; }
export interface ExportTarget { path: string; name?: string; label?: string; sensitivity?: string; max_sensitivity?: string; private?: boolean; }
export interface Catalog { documents: DocumentInfo[]; recipients: Recipient[]; exports: ExportTarget[]; }
export interface Bootstrap {
  version: string; csrf_token: string;
  model: { available: boolean; name: string; endpoint: string; config: JsonObject };
  catalog: Catalog; sessions: SessionSummary[]; modes: Mode[];
}
export interface SessionSummary { session_id: string; title: string; created_at: string; updated_at?: string; }
export interface Session extends SessionSummary { runs: Run[]; documents: DocumentInfo[]; last_sequence: number; }
export type RunStatus = 'running' | 'pending' | 'completed' | 'exhausted' | 'timeout' | 'model_error' | 'parse_error' | 'stopping' | 'stopped' | 'interrupted';
export interface AgentEvent {
  step: number; tool?: string; decision: string; reason?: string; reason_text?: string;
  node_id?: string; summary?: string; arguments?: unknown; result_summary?: string;
  source_ids?: string[]; confirmation_actor?: string;
}
export interface SourceNode {
  node_id: string; source_id: string; source_type: string; display_name?: string;
  content_hash?: string; integrity: string; sensitivity: string; parent_ids: string[];
  transformation: string; dependency_kind?: string; label_basis?: string; preview?: string;
}
export interface PendingConfirmation {
  action_hash: string; tool: string; target: string; preview: unknown; expires_at: number | string;
  node_id: string; source_ids: string[]; risk_reason: string;
}
export interface Run {
  run_id: string; session_id: string; version: string; mode: Mode; seed: number;
  task: string; status: RunStatus; phase: string; final: string | null; created_at: string;
  historical: boolean; backend_type?: string; events: AgentEvent[]; sources: SourceNode[];
  grant: JsonObject; pending: PendingConfirmation | null;
  state: { reads: string[]; inbox: { recipient_id: string; body: string }[]; files: { path: string; content: string; download_id?: string }[]; search_queries: string[] };
  canary: { established: boolean; read: boolean; status: string; findings: unknown; limits: unknown; attempts_blocked?: number };
  evaluation: { status: string; details?: unknown }; usage: JsonObject; warnings: string[];
}
export interface RunInput {
  request_id: string; task: string; mode: Mode; seed: number; document_ids: string[];
  recipient_id: string | null; export_path: string | null; private_mode: boolean; preview_id: string | null;
}
export interface StreamUpdate { session_id: string; run_id: string; sequence: number; phase: string; run: Run; }
export type AttackView = 'direct' | 'indirect' | 'encoding' | 'segmented';
export interface AttackTemplate { template_id: string; name: string; view: AttackView; description: string; defaults: Record<string, string>; options: Record<string, (string | { value: string; label: string })[]>; }
export interface PreviewSource { source_id: string; source_type: string; content: string; }
export interface AttackPreview { preview_id: string; case_id: string; task: string; before: PreviewSource[]; after: PreviewSource[]; fragments: { source_id: string; order: number; content: string }[]; metadata: JsonObject; }
export interface Summary { total_runs?: number; modes?: Record<string, Record<string, number>>; manifest?: JsonObject; }
export interface Campaign { id: string; label: string; version: string; historical: boolean; planned_runs: number; completed_runs: number; complete: boolean; summary: Summary; manifest: JsonObject; }
export interface ReplaySummary { record_id: string; case_id: string; mode: Mode; seed: number; status: string; version: string; }

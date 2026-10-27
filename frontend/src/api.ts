import type { AttackPreview, AttackTemplate, Bootstrap, Campaign, DocumentInfo, ReplaySummary, Run, RunInput, Session, SessionSummary } from './types';

let csrf = '';
export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) { super(message); this.code = code; this.status = status; }
}
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!path.startsWith('/api/') || path.startsWith('//')) throw new Error('只允许同源 API 请求。');
  const headers = new Headers(init.headers);
  if (init.method && init.method !== 'GET') headers.set('X-TaintLab-CSRF', csrf);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  let response: Response;
  try { response = await fetch(path, { ...init, headers, credentials: 'same-origin', cache: 'no-store' }); }
  catch { throw new ApiError('network_error', '无法连接本地服务。请确认项目已启动；重试不会重复提交同一次任务。', 0); }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (data as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(error?.code ?? 'request_failed', error?.message ?? `请求未完成（HTTP ${response.status}）。`, response.status);
  }
  return data as T;
}
const id = encodeURIComponent;
const post = <T,>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) });
export const api = {
  async bootstrap() { const data = await request<Bootstrap>('/api/bootstrap'); csrf = data.csrf_token; return data; },
  sessions: () => request<{ sessions: SessionSummary[] }>('/api/sessions'),
  session: (sid: string) => request<Session>(`/api/sessions/${id(sid)}`),
  createSession: (title?: string) => post<Session>('/api/sessions', title ? { title } : {}),
  run: (sid: string, body: RunInput) => post<Run>(`/api/sessions/${id(sid)}/runs`, body),
  getRun: (sid: string, rid: string) => request<Run>(`/api/sessions/${id(sid)}/runs/${id(rid)}`),
  stop: (sid: string, rid: string) => post<Run>(`/api/sessions/${id(sid)}/runs/${id(rid)}/stop`, {}),
  confirm: (sid: string, rid: string, action_hash: string, approve: boolean, request_id: string) => post<Run>(`/api/sessions/${id(sid)}/runs/${id(rid)}/confirm`, { request_id, action_hash, approve }),
  upload(sid: string, file: File) { const body = new FormData(); body.append('file', file); return request<DocumentInfo>(`/api/sessions/${id(sid)}/uploads`, { method: 'POST', body }); },
  templates: () => request<{ templates: AttackTemplate[] }>('/api/templates'),
  preview: (sid: string, options: Record<string, string | number>) => post<AttackPreview>(`/api/sessions/${id(sid)}/previews`, options),
  results: () => request<{ campaigns: Campaign[] }>('/api/results'),
  replays: (campaign: string) => request<{ records: ReplaySummary[] }>(`/api/replays?campaign=${id(campaign)}&limit=2000`),
  replay: (campaign: string, record: string) => request<Run>(`/api/replays/${id(campaign)}/${id(record)}`),
  eventURL: (sid: string, after: number) => `/api/sessions/${id(sid)}/events?after=${after}`,
  exportURL: (run: Run, download: string) => `/api/sessions/${id(run.session_id)}/runs/${id(run.run_id)}/exports/${id(download)}`,
};

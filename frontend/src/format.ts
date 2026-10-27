import type { Mode, RunStatus, Session, Run } from './types';

export const MODES: Record<Mode, { label: string; short: string; description: string }> = {
  taint_policy: { label: '污点追踪 + 权限策略', short: '完整防御', description: '按来源、敏感度与任务授权检查每次执行。' },
  input_filter: { label: '仅输入过滤', short: '输入过滤', description: '仅过滤外部内容，不额外启用权限与信息流阻断。' },
  none: { label: '无应用防御', short: '无防御', description: '用于本地模拟对照，宿主隔离始终保留。' },
  policy_only: { label: '仅权限策略（消融）', short: '仅权限', description: '保留权限检查，关闭污点信息流约束。' },
};
export const STATUS: Record<RunStatus, string> = { running: '运行中', pending: '等待确认', completed: '运行结束', exhausted: '预算耗尽', timeout: '运行超时', model_error: '模型服务异常', parse_error: '动作格式错误', stopping: '正在停止', stopped: '已停止', interrupted: '运行已中断' };
export const TOOLS: Record<string, string> = { read_document: '读取文档', search_info: '查询资料', send_notification: '发送模拟通知', export_file: '导出虚拟文件', final: '最终回复' };
export const isBusy = (status?: string) => !!status && ['running', 'pending', 'stopping'].includes(status);
export const text = (value: unknown) => typeof value === 'string' ? value : value == null ? '—' : JSON.stringify(value, null, 2);
export const date = (value: string | number) => new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
export const deadline = (value: string | number) => typeof value === 'number' ? value < 1e12 ? value * 1000 : value : Date.parse(value);
export const sensitivity = (value: string) => ({ public: '公开', internal: '内部', secret: '敏感' })[value] ?? value;
export const percent = (value?: number) => value == null || !Number.isFinite(value) ? '—' : `${(value * 100).toFixed(2)}%`;
export function mergeRun(session: Session, run: Run, sequence?: number): Session {
  if (run.session_id !== session.session_id) return session;
  if (sequence != null && sequence <= session.last_sequence) return session;
  const index = session.runs.findIndex(item => item.run_id === run.run_id);
  const previous = session.runs[index];
  // HTTP receipts may arrive after a newer SSE snapshot. Preserve visible
  // evidence and terminal states, rather than restarting the same UI run.
  if (sequence == null && previous && (previous.events.length > run.events.length ||
    (!isBusy(previous.status) && isBusy(run.status)) ||
    (previous.status === 'stopping' && ['running', 'pending'].includes(run.status)))) return session;
  const runs = index < 0 ? [...session.runs, run] : session.runs.map(item => item.run_id === run.run_id ? run : item);
  return { ...session, runs, last_sequence: Math.max(session.last_sequence, sequence ?? 0) };
}

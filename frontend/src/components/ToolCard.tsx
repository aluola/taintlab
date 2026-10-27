import type { AgentEvent } from '../types';
import { text, TOOLS } from '../format';
import { Icon } from './Icon';

export function ToolCard({ event, onInspect }: { event: AgentEvent; onInspect?: () => void }) {
  const blocked = ['block', 'deny', 'denied'].includes(event.decision);
  const pending = event.decision === 'pending';
  const allowed = ['allow', 'allowed', 'confirmed'].includes(event.decision);
  const tone = blocked ? 'danger' : pending ? 'warning' : allowed ? 'success' : 'neutral';
  return <details className={`tool-card ${tone}`}>
    <summary><span className="tool-state"><Icon name={blocked ? 'shield' : pending ? 'clock' : allowed ? 'check' : 'source'} size={16} /></span><span className="tool-title">{TOOLS[event.tool ?? ''] ?? event.tool ?? '执行事件'}</span><span className={`tag ${tone}`}>{blocked ? '已阻断' : pending ? '待确认' : allowed ? '已允许' : '已记录'}</span><span className="step">#{event.step}</span><Icon name="chevron" size={14} /></summary>
    <div className="tool-detail">
      {event.summary && <p>{event.summary}</p>}
      {event.reason_text && <p className={blocked ? 'danger-text' : 'muted'}>{event.reason_text}</p>}
      {event.arguments != null && <div><span className="field-label">网关可见参数</span><pre>{text(event.arguments)}</pre></div>}
      {event.result_summary && <div><span className="field-label">实际结果</span><p>{event.result_summary}</p></div>}
      {event.confirmation_actor && <p className="muted small">确认来源：{event.confirmation_actor}</p>}
      <button type="button" className="text-button" onClick={onInspect}><Icon name="shield" size={14} />查看决策与来源</button>
    </div>
  </details>;
}

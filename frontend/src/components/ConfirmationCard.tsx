import { useEffect, useState } from 'react';
import type { Run } from '../types';
import { date, deadline, text, TOOLS } from '../format';
import { Icon } from './Icon';

export function ConfirmationCard({ run, busy, onDecision }: { run: Run; busy: boolean; onDecision: (run: Run, approve: boolean) => void }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const pending = run.pending;
  if (!pending) return null;
  const expired = !Number.isFinite(deadline(pending.expires_at)) || now >= deadline(pending.expires_at);
  const disabled = busy || run.historical || expired || run.status !== 'pending';
  return <section className="confirmation-card" aria-label="操作确认">
    <div className="confirm-heading"><span className="confirm-icon"><Icon name="lock" /></span><div><strong>{run.historical ? '历史确认记录 · 只读' : '这一步需要你确认'}</strong><p>{TOOLS[pending.tool] ?? pending.tool} · 仅授权本次操作</p></div><span className="tag warning">{expired ? '凭据已过期' : '待确认'}</span></div>
    <dl className="confirm-target"><dt>执行目标</dt><dd>{pending.target}</dd></dl>
    <div className="confirm-content"><span className="field-label">待执行内容</span><pre>{text(pending.preview)}</pre></div>
    {pending.risk_reason && <p className="confirm-reason">{pending.risk_reason}</p>}
    <details className="binding"><summary>来源与确认绑定 <Icon name="chevron" size={12} /></summary><dl><dt>来源</dt><dd>{pending.source_ids?.join('、') || '未列出来源'}</dd><dt>运行</dt><dd>{run.run_id}</dd><dt>内容哈希</dt><dd>{pending.action_hash}</dd><dt>有效期</dt><dd>{date(pending.expires_at)}</dd></dl></details>
    <div className="confirm-actions"><button type="button" className="button ghost" disabled={disabled} onClick={() => onDecision(run, false)}>拒绝并继续</button><button type="button" className="button primary" disabled={disabled} onClick={() => onDecision(run, true)}><Icon name="check" size={16} />{busy ? '正在提交确认' : '确认本次执行'}</button></div>
    <p className="small muted">{run.historical ? '真实运行记录回放不能签发新的确认。' : expired ? '确认已过期。服务端将再次校验有效期，不会执行旧凭据。' : '确认绑定当前内容与目标，参数变化后原确认失效。'}</p>
  </section>;
}

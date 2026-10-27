import { useEffect, useRef, useState } from 'react';
import type { Run } from '../types';
import { api } from '../api';
import { MODES, STATUS, text, TOOLS } from '../format';
import { Icon } from './Icon';

import { GrantSummary } from './GrantSummary';
import { SourceExplorer } from './SourceExplorer';

export function SecurityDrawer({ run, onClose, focusedNodeId }: { run: Run | null; onClose: () => void; focusedNodeId?: string }) {
  const [tab, setTab] = useState('decisions');
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const controls = () => [...(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),summary') ?? [])].filter(element => !element.closest('details:not([open])') || element.matches('summary'));
    controls()[0]?.focus();
    const handle = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key !== 'Tab') return;
      const elements = controls(), first = elements[0], last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    window.addEventListener('keydown', handle);
    return () => { window.removeEventListener('keydown', handle); previous?.focus(); };
  }, [onClose]);
  const events = run?.events ?? [];
  return <div className="drawer-backdrop" onClick={onClose}><aside ref={dialog} className="security-drawer" aria-label="安全审计详情" role="dialog" aria-modal="true" onClick={event => event.stopPropagation()}><div className="drawer-header"><span className="drawer-symbol"><Icon name="shield" /></span><div><h2>执行与安全</h2><p>由程序记录的决策与来源</p></div><button type="button" className="icon-button" onClick={onClose} aria-label="关闭安全审计"><Icon name="close" /></button></div>
    {!run ? <div className="drawer-empty"><Icon name="source" size={36} /><h3>执行后在这里查看</h3><p>运行任务后，来源、权限决策和实际交付会出现在这里。</p></div> : <><div className="drawer-run"><span className={`tag ${run.historical ? 'warning' : 'neutral'}`}>{run.historical ? '真实运行记录回放' : STATUS[run.status]}</span><span className="tag neutral">{MODES[run.mode]?.short ?? run.mode}</span><small>{run.version} · {run.run_id}</small></div><div className="drawer-tabs" role="tablist">{[['decisions', '决策'], ['sources', '来源'], ['outputs', '交付'], ['canary', '泄露检测']].map(([value, label]) => <button type="button" key={value} role="tab" aria-selected={tab === value} className={tab === value ? 'selected' : ''} onClick={() => setTab(value)}>{label}</button>)}</div><div className="drawer-content">
      {tab === 'decisions' && <><div className="decision-counts"><div><strong>{events.filter(event => ['allow', 'allowed', 'confirmed'].includes(event.decision)).length}</strong><span>允许</span></div><div><strong>{events.filter(event => ['block', 'deny', 'denied'].includes(event.decision)).length}</strong><span>阻断</span></div><div><strong>{run.pending ? 1 : 0}</strong><span>待确认</span></div></div><GrantSummary run={run} />{events.length === 0 && <p className="muted">尚无工具决策。</p>}{events.map((event, index) => <article className="audit-event" key={`${event.step}-${index}`}><div><span className="event-number">{event.step}</span><strong>{TOOLS[event.tool ?? ''] ?? event.tool ?? '执行事件'}</strong><span className={`tag ${['block', 'deny'].includes(event.decision) ? 'danger' : event.decision === 'pending' ? 'warning' : 'neutral'}`}>{event.decision}</span></div><p>{event.reason_text ?? event.summary ?? event.reason ?? '已记录'}</p>{event.reason && <code>{event.reason}</code>}{event.source_ids?.length ? <small>来源：{event.source_ids.join('、')}</small> : null}</article>)}</>}
      {tab === 'sources' && <SourceExplorer key={run.run_id + (focusedNodeId ?? '')} nodes={run.sources} events={run.events} initialNodeId={focusedNodeId} />}
      {tab === 'outputs' && <><div className="section-heading"><h3>模拟收件箱</h3><span>{run.state.inbox.length} 条</span></div>{run.state.inbox.length === 0 && <p className="empty-inline">尚未发送通知。</p>}{run.state.inbox.map((message, index) => <article className="delivery-card" key={index}><header><Icon name="bell" size={16} /><strong>{message.recipient_id}</strong><span className="tag neutral">模拟</span></header><p>{message.body}</p></article>)}<div className="section-heading"><h3>虚拟导出文件</h3><span>{run.state.files.length} 份</span></div>{run.state.files.length === 0 && <p className="empty-inline">尚未导出文件。</p>}{run.state.files.map((file, index) => <article className="delivery-card" key={index}><header><Icon name="file" size={16} /><strong>{file.path}</strong></header><pre>{file.content}</pre>{file.download_id && !run.historical && <a className="button ghost small" href={api.exportURL(run, file.download_id)}><Icon name="download" size={14} />下载已执行的导出物</a>}</article>)}<p className="small muted">这里显示已写入模拟状态的内容。模型声称“已发送”不会创建通知。</p></>}
      {tab === 'canary' && <><div className="canary-status"><Icon name="shield" size={28} /><h3>{run.canary.status || '检测状态未提供'}</h3><p>Canary 原值默认遮蔽，判定由服务端在遮蔽前完成。</p></div><dl className="canary-facts"><dt>已建立 Canary</dt><dd>{run.canary.established ? '是' : '否'}</dd><dt>敏感资料被读取</dt><dd>{run.canary.read ? '是' : '否'}</dd><dt>被阻断的尝试</dt><dd>{run.canary.attempts_blocked ?? '未记录'}</dd><dt>任务评定</dt><dd>{run.evaluation.status}</dd></dl><details className="audit-detail"><summary>实际检测记录</summary><pre>{text(run.canary.findings)}</pre></details><details className="audit-detail"><summary>检测范围与限制</summary><pre>{text(run.canary.limits)}</pre></details>{run.evaluation.details != null && <details className="audit-detail"><summary>任务评定依据</summary><pre>{text(run.evaluation.details)}</pre></details>}<p className="small muted">没有检测到 Canary 不等于证明不存在泄露；编码覆盖和分段检测均有边界。</p></>}
    </div></>}
  </aside></div>;
}

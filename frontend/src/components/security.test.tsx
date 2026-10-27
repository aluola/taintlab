import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { ToolCard } from './ToolCard';
import { ConfirmationCard } from './ConfirmationCard';
import { Composer } from './Composer';
import type { ComposerProps } from './Composer';
import { ParameterPanel } from './ParameterPanel';
import { SecurityDrawer } from './SecurityDrawer';
import { fixtureCatalog, fixtureRun } from '../testFixtures';
afterEach(cleanup);

describe('external content is text and observable states stay truthful', () => {
  it('does not turn tool text or parameters into HTML', () => {
    const payload = '<img src="https://example.invalid/x" onerror="alert(1)"><script>attack()</script>';
    const { container } = render(<ToolCard event={{ step: 1, tool: 'read_document', decision: 'allow', arguments: { content: payload }, result_summary: payload }} />);
    expect(container.querySelector('img,script,iframe')).toBeNull();
    expect(container.textContent).toContain(payload);
    expect(screen.getByText('已允许')).toBeDefined();
    expect(screen.queryByText('任务成功')).toBeNull();
  });
  it('renders blocked actions without invented output state', () => {
    render(<SecurityDrawer run={fixtureRun({ events: [{ step: 1, tool: 'send_notification', decision: 'block', reason: 'recipient_not_granted' }] })} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('tab', { name: '交付' }));
    expect(screen.getByText('尚未发送通知。')).toBeDefined();
    expect(screen.queryByRole('link')).toBeNull();
  });
  it('builds download routes only from issued IDs, never the model path', () => {
    render(<SecurityDrawer run={fixtureRun({ state: { reads: [], search_queries: [], inbox: [], files: [{ path: 'C:\\sensitive\\file.txt', content: 'simulation', download_id: 'issued id' }] } })} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('tab', { name: '交付' }));
    const href = screen.getByRole('link').getAttribute('href');
    expect(href).toBe('/api/sessions/ui-fixture-session/runs/ui-fixture-run/exports/issued%20id');
    expect(href).not.toContain('sensitive');
  });
});

function pendingRun() { return fixtureRun({ status: 'pending', pending: { action_hash: 'a'.repeat(64), tool: 'send_notification', target: 'team_A', preview: '<b>确认原文</b>', expires_at: Date.now() + 60000, node_id: 'n1', source_ids: ['doc-1'], risk_reason: '内容与目标绑定' } }); }
describe('confirmation remains bound and read only for history', () => {
  it('shows the exact pending payload as text and sends the bound run', () => {
    const run = pendingRun(), decide = vi.fn();
    const { container } = render(<ConfirmationCard run={run} busy={false} onDecision={decide} />);
    expect(screen.getByText('<b>确认原文</b>')).toBeDefined();
    expect(container.querySelector('b')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '确认本次执行' }));
    expect(decide).toHaveBeenCalledExactlyOnceWith(run, true);
  });
  it('does not issue confirmation from a historical projection', () => {
    const decide = vi.fn();
    render(<ConfirmationCard run={{ ...pendingRun(), historical: true }} busy={false} onDecision={decide} />);
    const button = screen.getByRole('button', { name: '确认本次执行' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true); fireEvent.click(button); expect(decide).not.toHaveBeenCalled();
  });
  it('does not issue an expired confirmation or one already submitted', () => {
    const run = pendingRun(); run.pending!.expires_at = Date.now() - 1000;
    const decide = vi.fn(); const { rerender } = render(<ConfirmationCard run={run} busy={false} onDecision={decide} />);
    expect((screen.getByRole('button', { name: '确认本次执行' }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<ConfirmationCard run={pendingRun()} busy={true} onDecision={decide} />);
    expect((screen.getByRole('button', { name: '正在提交确认' }) as HTMLButtonElement).disabled).toBe(true);
  });
  it('keeps refusal a distinct decision rather than editing parameters', () => {
    const run = pendingRun(), decide = vi.fn(); render(<ConfirmationCard run={run} busy={false} onDecision={decide} />);
    fireEvent.click(screen.getByRole('button', { name: '拒绝并继续' })); expect(decide).toHaveBeenCalledExactlyOnceWith(run, false);
  });
});

function composerProps(): ComposerProps { return { value: '请查询会议', onChange: vi.fn(), onSubmit: vi.fn(), mode: 'taint_policy', onMode: vi.fn(), onSettings: vi.fn(), onUpload: vi.fn(), uploading: false, busy: false, stopping: false, submitting: false, onStop: vi.fn(), selectedDocuments: [], onRemoveDocument: vi.fn() }; }
describe('composer has one task path and honors real running states', () => {
  it('does not submit IME composition or Shift+Enter', () => {
    const props = composerProps(); render(<Composer {...props} />); const input = screen.getByRole('textbox');
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true }); fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(props.onSubmit).not.toHaveBeenCalled(); fireEvent.keyDown(input, { key: 'Enter' }); expect(props.onSubmit).toHaveBeenCalledTimes(1);
  });
  it('cannot submit again while running; stopping is a real separate action', () => {
    const props = { ...composerProps(), busy: true }; const { rerender } = render(<Composer {...props} />);
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' }); expect(props.onSubmit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '停止当前任务' })); expect(props.onStop).toHaveBeenCalledTimes(1);
    rerender(<Composer {...props} stopping />); expect((screen.getByRole('button', { name: '正在停止' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('已请求停止，等待当前模型调用返回。')).toBeDefined();
  });
});

describe('private scope requires deliberate consent', () => {
  it('keeps sensitive selections disabled before opt in', () => {
    render(<ParameterPanel catalog={fixtureCatalog} value={{ document_ids: [], recipient_id: '', export_path: '', private_mode: false, seed: 11 }} onChange={vi.fn()} onClose={vi.fn()} busy={false} />);
    expect((screen.getByRole('checkbox', { name: /模拟敏感档案/ }) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole('option', { name: /模拟私有收件箱/ }) as HTMLOptionElement).disabled).toBe(true);
  });
  it('removes private targets and secret sources when opting back out', () => {
    const change = vi.fn(); render(<ParameterPanel catalog={fixtureCatalog} value={{ document_ids: ['meeting', 'vault'], recipient_id: 'private', export_path: '/private/summary.txt', private_mode: true, seed: 11 }} onChange={change} onClose={vi.fn()} busy={false} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /敏感资料私有处理/ }));
    expect(change).toHaveBeenCalledExactlyOnceWith({ document_ids: ['meeting'], recipient_id: '', export_path: '', private_mode: false, seed: 11 });
  });
  it('upload/catalog presence alone does not authorize a read', () => {
    function Harness() { const [value, setValue] = useState({ document_ids: [] as string[], recipient_id: '', export_path: '', private_mode: false, seed: 11 }); return <ParameterPanel catalog={fixtureCatalog} value={value} onChange={setValue} onClose={vi.fn()} busy={false} />; }
    render(<Harness />); const normal = screen.getByRole('checkbox', { name: /模拟会议记录/ }) as HTMLInputElement;
    expect(normal.checked).toBe(false); fireEvent.click(normal); expect(normal.checked).toBe(true);
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';
import { api, ApiError } from './api';
import { fixtureBootstrap, fixtureRun, fixtureSession } from './testFixtures';

class TestEventSource {
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  addEventListener() {}
  close() {}
}
beforeEach(() => {
  vi.stubGlobal('EventSource', TestEventSource);
  vi.spyOn(api, 'bootstrap').mockResolvedValue(fixtureBootstrap);
  vi.spyOn(api, 'sessions').mockResolvedValue({ sessions: [] });
  vi.spyOn(api, 'createSession').mockResolvedValue(fixtureSession());
  vi.spyOn(api, 'run').mockResolvedValue(fixtureRun());
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function ready() { render(<App />); await screen.findByRole('button', { name: 'scripted_ui_fixture' }); }
describe('quick entries share the natural-language task submission path', () => {
  it('only fills input and opens authorization until the user sends', async () => {
    await ready(); fireEvent.click(screen.getByRole('button', { name: /^发送通知/ }));
    expect(screen.getByRole('textbox', { name: '任务输入' }).getAttribute('placeholder')).toContain('输入你的任务');
    expect(screen.getByRole('region', { name: '任务授权参数' })).toBeDefined(); expect(api.run).not.toHaveBeenCalled(); expect(api.createSession).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: /模拟会议记录/ }));
    fireEvent.change(screen.getByLabelText('模拟通知收件人'), { target: { value: 'team_A' } });
    fireEvent.click(screen.getByRole('button', { name: '发送任务' }));
    await waitFor(() => expect(api.run).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.run).mock.calls[0][1]).toMatchObject({ document_ids: ['meeting'], recipient_id: 'team_A', mode: 'taint_policy', private_mode: false, preview_id: null });
    expect(vi.mocked(api.run).mock.calls[0][1]).not.toHaveProperty('grant');
  });
  it('keeps selection validation as UI feedback, not an assistant answer', async () => {
    vi.mocked(api.run).mockRejectedValue(new ApiError('selection_required', '请选择模拟目标', 400)); await ready();
    fireEvent.change(screen.getByRole('textbox', { name: '任务输入' }), { target: { value: '请发送通知' } }); fireEvent.click(screen.getByRole('button', { name: '发送任务' }));
    await screen.findByRole('alert'); expect(screen.getByText('请选择模拟目标')).toBeDefined(); expect(screen.getByRole('region', { name: '任务授权参数' })).toBeDefined();
    expect(document.querySelector('.assistant-message')).toBeNull();
  });
  it('reuses request_id on a manual retry without automatic replay', async () => {
    vi.mocked(api.run).mockRejectedValueOnce(new ApiError('network_error', '本地网络测试中断', 0)).mockResolvedValueOnce(fixtureRun()); await ready();
    fireEvent.change(screen.getByRole('textbox', { name: '任务输入' }), { target: { value: '读取我选择的文档' } }); fireEvent.click(screen.getByRole('button', { name: '发送任务' }));
    await screen.findByText('本地网络测试中断'); expect(api.run).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '发送任务' })); await waitFor(() => expect(api.run).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(api.run).mock.calls; expect(calls[0][1].request_id).toBe(calls[1][1].request_id); expect(api.createSession).toHaveBeenCalledTimes(1);
  });
  it('never labels the scripted UI fixture as a real local model', async () => {
    await ready(); fireEvent.change(screen.getByRole('textbox', { name: '任务输入' }), { target: { value: 'UI fixture only' } }); fireEvent.click(screen.getByRole('button', { name: '发送任务' }));
    await screen.findByText('后端：scripted_ui_fixture'); expect(screen.queryByText('本地模型实测')).toBeNull(); expect(screen.getByText('任务评定：未自动评定')).toBeDefined();
  });
});

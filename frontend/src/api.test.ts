import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from './api';
import { fixtureBootstrap, fixtureRun } from './testFixtures';
afterEach(() => vi.unstubAllGlobals());
describe('same origin transport and confirmation payload', () => {
  it('uses cookie+CSRF and sends only a server pending reference', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(fixtureBootstrap))).mockResolvedValueOnce(new Response(JSON.stringify(fixtureRun())));
    vi.stubGlobal('fetch', fetch); await api.bootstrap(); await api.confirm('sid', 'rid', 'a'.repeat(64), true, 'same-retry-id');
    expect(fetch.mock.calls[1][0]).toBe('/api/sessions/sid/runs/rid/confirm');
    const init = fetch.mock.calls[1][1] as RequestInit;
    expect((init.headers as Headers).get('X-TaintLab-CSRF')).toBe(fixtureBootstrap.csrf_token);
    expect(init.credentials).toBe('same-origin');
    expect(JSON.parse(String(init.body))).toEqual({ request_id: 'same-retry-id', action_hash: 'a'.repeat(64), approve: true });
    expect(api.eventURL('sid', 8)).not.toContain('csrf'); expect(api.eventURL('sid', 8)).toBe('/api/sessions/sid/events?after=8');
  });
  it('reports structured selection failures without inventing assistant content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'selection_required', message: '选择目标' } }), { status: 400 })));
    await expect(api.createSession()).rejects.toMatchObject({ code: 'selection_required', message: '选择目标', status: 400 });
  });
  it('does not automatically retry a failed mutation', async () => {
    const fetch = vi.fn().mockRejectedValue(new Error('offline')); vi.stubGlobal('fetch', fetch);
    await expect(api.stop('sid', 'rid')).rejects.toBeInstanceOf(ApiError); expect(fetch).toHaveBeenCalledTimes(1);
  });
});

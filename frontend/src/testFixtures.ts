// Synthetic UI contract fixtures only. Never used by production rendering or
// represented as local model execution evidence.
import type { Run, Session, Catalog, Bootstrap } from './types';
export function fixtureRun(patch: Partial<Run> = {}): Run {
  return { run_id: 'ui-fixture-run', session_id: 'ui-fixture-session', version: 'ui-test-only', backend_type: 'scripted_ui_fixture', mode: 'taint_policy', seed: 11, task: '这是界面测试任务', status: 'completed', phase: 'complete', final: '这是界面测试文本', created_at: '2026-10-27T00:00:00Z', historical: false,
    events: [], sources: [], grant: {}, pending: null, state: { reads: [], inbox: [], files: [], search_queries: [] }, canary: { established: true, read: false, status: '测试状态', findings: [], limits: {} }, evaluation: { status: '未自动评定' }, usage: {}, warnings: [], ...patch };
}
export function fixtureSession(patch: Partial<Session> = {}): Session {
  return { session_id: 'ui-fixture-session', title: '界面测试会话', created_at: '2026-10-27T00:00:00Z', runs: [], documents: [], last_sequence: 0, ...patch };
}
export const fixtureCatalog: Catalog = {
  documents: [{ doc_id: 'meeting', name: '模拟会议记录', sensitivity: 'public' }, { doc_id: 'vault', name: '模拟敏感档案', sensitivity: 'secret' }],
  recipients: [{ recipient_id: 'team_A', name: '模拟项目组', sensitivity: 'internal' }, { recipient_id: 'private', name: '模拟私有收件箱', sensitivity: 'secret', private: true }],
  exports: [{ path: '/exports/summary.txt', name: '普通虚拟导出', sensitivity: 'internal' }, { path: '/private/summary.txt', name: '私有虚拟导出', sensitivity: 'secret', private: true }],
};
export const fixtureBootstrap: Bootstrap = { version: 'ui-test-only', csrf_token: 'test-csrf-not-a-real-token', model: { available: true, name: 'scripted_ui_fixture', endpoint: 'http://127.0.0.1:8080', config: {} }, catalog: fixtureCatalog, sessions: [], modes: ['none','input_filter','taint_policy','policy_only'] };

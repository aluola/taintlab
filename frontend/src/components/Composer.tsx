import { useRef } from 'react';
import type { Mode, DocumentInfo } from '../types';
import { MODES } from '../format';
import { Icon } from './Icon';

export interface ComposerProps {
  value: string; onChange: (value: string) => void; onSubmit: () => void;
  mode: Mode; onMode: (value: Mode) => void; onSettings: () => void;
  onUpload: (file: File) => void; uploading: boolean; busy: boolean; stopping: boolean;
  submitting: boolean; onStop: () => void; selectedDocuments: DocumentInfo[];
  onRemoveDocument: (id: string) => void; disabled?: boolean;
}
export function Composer(props: ComposerProps) {
  const input = useRef<HTMLInputElement>(null);
  return <div className="composer-area">
    <div className="composer">
      {props.selectedDocuments.length > 0 && <div className="attachment-strip">{props.selectedDocuments.map(document => <span className="attachment" key={document.doc_id}><Icon name="file" size={14} /><span>{document.name}</span><button type="button" aria-label={`移除文档 ${document.name}`} onClick={() => props.onRemoveDocument(document.doc_id)} disabled={props.busy}><Icon name="close" size={12} /></button></span>)}</div>}
      <textarea aria-label="任务输入" placeholder="输入你的任务，或上传一份资料开始…" value={props.value} maxLength={1800} onChange={event => props.onChange(event.target.value)} rows={3} onKeyDown={event => {
        if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!props.busy && !props.submitting && !props.disabled && props.value.trim()) props.onSubmit(); }
      }} />
      <div className="composer-toolbar"><div className="composer-options"><input type="file" ref={input} hidden accept=".txt,.md,.pdf,.docx" onChange={event => { const file = event.target.files?.[0]; if (file) props.onUpload(file); event.target.value = ''; }} /><button type="button" className="icon-button" aria-label="上传资料" title="上传 TXT、Markdown、PDF 或 DOCX（最大 2 MiB）" disabled={props.uploading || props.busy} onClick={() => input.current?.click()}><Icon name="paperclip" /></button><button type="button" className="composer-parameters" onClick={props.onSettings}><Icon name="settings" size={16} />任务参数</button><label className="mode-picker"><Icon name="shield" size={15} /><select aria-label="防御配置" value={props.mode} onChange={event => props.onMode(event.target.value as Mode)} disabled={props.busy}>{Object.entries(MODES).map(([value, item]) => <option value={value} key={value}>{item.short}</option>)}</select></label></div>
      {props.busy ? <button className="send-button stop-button" type="button" disabled={props.stopping} onClick={props.onStop} aria-label={props.stopping ? '正在停止' : '停止当前任务'} title="停止当前任务"><Icon name="stop" size={17} /></button> : <button className="send-button" type="button" onClick={props.onSubmit} disabled={!props.value.trim() || props.submitting || props.uploading || props.disabled} aria-label="发送任务" title="发送任务"><Icon name="send" size={19} /></button>}</div>
    </div>
    <div className="composer-footer"><span>{props.uploading ? '正在解析上传文件…' : props.stopping ? '已请求停止，等待当前模型调用返回。' : props.value.length >= 1500 ? `${props.value.length} / 1800 字符 · Enter 发送` : 'Enter 发送 · Shift + Enter 换行'}</span><span><span className="tiny-dot" />本地推理 · 模拟工具</span></div>
  </div>;
}

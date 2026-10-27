# Web API 2.0（实现约定）

同源127.0.0.1:8501；服务提供frontend/dist和API，日常不启动Vite。所有JSON用UTF-8。错误为HTTP非2xx `{error:{code,message}}`。前端用纯文本渲染，不加载外链资源。

## 身份与事件

`GET /api/bootstrap` 建立HttpOnly/SameSite=Strict浏览器cookie，返回`{version,csrf_token,model:{available,name,endpoint,config},catalog:{documents,recipients,exports},sessions,modes}`。所有POST附`X-TaintLab-CSRF`及同源Origin，fetch默认same-origin。事件源同源cookie，无token查询串。文档仅元数据，没有vault正文/Canary原值。

`POST /api/sessions {title?}` -> Session；`GET /api/sessions` -> `{sessions}`；`GET /api/sessions/{sid}` -> Session。Session为`{session_id,title,created_at,runs:Run[],documents:Document[],last_sequence}`，API核对浏览器会话归属。历史折叠显示。

`GET /api/sessions/{sid}/events?after=0` 为SSE，`id:顺序号`、`event:update`、`data:{session_id,run_id,sequence,phase,run:Run}`；支持Last-Event-ID，心跳为注释。断连不会重跑任务。Run投影已过可见性检查，不含原始token/checkpoint。

## 对话与授权

`POST /api/sessions/{sid}/runs` 输入：
```json
{"request_id":"前端crypto.randomUUID()；同次重试复用","task":"用户自然语言","mode":"taint_policy","seed":11,"document_ids":["meeting"],"recipient_id":null,"export_path":null,"private_mode":false,"preview_id":null}
```
返回Run（202，重复request_id返回既有run不执行）。document_ids是显式文档选择；recipient_id/export_path只能取catalog；空值没有该工具授权。读取/查询为基础工具。选择敏感文档必须显式private_mode，并仅允许对应私有出口。安全模式通知和导出默认需要确认。用户正文或额外字段不能签发grant；配置变更只用于新run。

缺少请求中的通知/导出目标返回400 `selection_required`，前端展示参数面板，不冒充模型回复。快捷按钮填充任务/打开参数选择，仍调用同一runs入口；不直接执行工具。

`POST /api/sessions/{sid}/uploads` multipart字段`file` -> Document。支持txt/md/pdf/docx，2MiB文件/8MiB展开/8秒解析/10000字符上限，截断及警告字段可见。返回`{doc_id,name,source_type,integrity,sensitivity,content_hash,characters,warnings,label_basis}`，不会直接将内容放模型提示；须授权后read_document。

`POST /api/sessions/{sid}/runs/{rid}/stop {}` -> Run。停止状态实际影响下一动作；已发生副作用保留。模型请求未返回时显示stopping，不能宣称已停止推理。

`POST /api/sessions/{sid}/runs/{rid}/confirm {request_id,action_hash,approve:boolean}` -> Run。只接受服务器pending引用，不接受action/grant/checkpoint。并发、过期、重放均服务器处理。

## Run（安全投影）

```text
run_id, session_id, version, mode, seed, task, status,
phase, final, created_at, historical=false,
events:[{step,tool,decision,reason,reason_text,node_id,summary,arguments,result_summary,source_ids,confirmation_actor?}],
sources:[{node_id,source_id,source_type,display_name,content_hash,integrity,sensitivity,parent_ids,transformation,dependency_kind,label_basis,preview?}],
grant:{...实际TaskGrant，policy_version,used_calls,remaining_calls},
pending:null|{action_hash,tool,target,preview,expires_at,node_id,source_ids,risk_reason},
state:{reads,inbox:[{recipient_id,body}],files:[{path,content,download_id}],search_queries},
canary:{established,read,status,findings,limits,attempts_blocked},
evaluation:{status:'未自动评定'|...,details?},usage,warnings
```

状态running/pending/completed/exhausted/timeout/model_error/parse_error/stopping/stopped/interrupted。敏感正文、被拦动作参数、工具返回和节点内容按实际标签/授权投影；默认遮蔽Canary，评测在遮蔽前对raw record完成。来源图的potential_context只表示潜在上下文依赖。

`GET /api/sessions/{sid}/runs/{rid}/exports/{download_id}` 仅下载已经执行且符合该run授权的虚拟导出物；download_id服务器签发，不接受宿主路径，Content-Disposition安全固定名。

## 攻击实验

`GET /api/templates` -> `{templates:[{template_id,name,view,description,defaults:{technique,encoding,entry,goal,workflow},options:{...}}]}`，view=direct/indirect/encoding/segmented。

`POST /api/sessions/{sid}/previews {view,technique,encoding,entry,goal,workflow,seed}` -> `{preview_id,case_id,task,before,after,fragments,metadata}`。参数可用templates.defaults填入，options供选择。metadata含template_id/version/seed/entry/technique/encoding/goal/sample_kind。预览不是运行。

把preview_id传给runs即可运行服务器保存的样本与预置授权；mode/seed按用户选择。预览不能提交自造runtime/grant。生成内容与原文均为模拟、没有Canary实际值。分段fragments每项含source_id/order/content。

## 评测与真实回放

`GET /api/results` -> `{campaigns:[{id,label,version,historical,planned_runs,completed_runs,complete,summary,manifest}...]}`。summary沿用现有summarize格式；主表三模式，policy_only可展开。历史main/ablation明确v1；新v2_baseline/v2_external分别显示。

`GET /api/replays?campaign=...` -> `{records:[{record_id,case_id,mode,seed,status,version}]}`；`GET /api/replays/{campaign}/{record_id}` -> Run（historical=true、清楚真实记录回放）。服务从白名单结果目录读取，路径参数不是文件路径；返回安全投影，不能通过回放确认历史pending。

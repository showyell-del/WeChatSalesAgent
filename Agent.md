# Project Agent Notes

## 产品边界

- 产品是 macOS Apple Silicon 原生 AppKit 桌面 App，不是网页、Codex Skill 或脚本集。
- 当前只保留三条完整主链：微信私聊同步、DeepSeek 线索分析、客户工作台与 Excel 导出。
- 应用不得向微信发送文本、图片、视频或文件；不得保留发送按钮、批次状态库、发送 CLI、守护进程、NativeWorker、Frida 发送脚本或微信 profile。
- 不得用剪贴板、键鼠模拟、系统分享、Hermes 或其他通道代替微信发送。
- 会话候选仅表示进入 DeepSeek 筛选的双向私聊，模型分析前不得称为客户或线索。

## 当前目录真相

- `app/Phase0App/main.m`：唯一桌面 UI，负责首次连接、按需 DeepSeek Agent 查询、客户表和 Excel 导出。
- `agent_core/`：同步、证据语料、AI 分析和工作台读模型；不包含发送运行时。
- `chatlog/chatlog-darwin-arm64`：App 内置的 Chatlog Alpha Apple Silicon 依赖；许可证保留在 `chatlog/LICENSE`。
- `dist/WeChatSalesAgent-MVP-macOS-arm64.dmg`：唯一对外交付物；验证后必须删除中间 `.app`。
- 本机业务数据库默认位于 `~/Library/Application Support/WeChatSalesAgent/agent_state.sqlite3`，不属于项目源码。

## 数据与 DeepSeek 链路

- 项目内 Chatlog 默认路径统一为 `chatlog/chatlog-darwin-arm64`。修改目录时同时检查 `agent_core/sync_cli.py`、`scripts/build_phase0_app.sh` 和 `scripts/phase0_chatlog_smoke.sh`。
- App 通过 Chatlog `action start-http` 启动本机服务，通过 `/api/v1/db`、`/api/v1/sessions` 和分方向 `/api/v1/history` 取得完整数据。
- 证据 ID 绑定账号、数据代、对话、本地消息 ID、方向、发件人、时间和内容 SHA-256；确定性联系方式只从客户方证据提取。
- 用户发送 Agent 指令后，DeepSeek 先生成包含时间范围和概念组的检索计划；本机按时间条件全量召回候选，再分批完成第一轮语义判断和不携带首轮结论的独立覆盖审计。所有模型请求必须使用 OpenAI-compatible `/chat/completions` 的 JSON Output。
- 空内容、非 JSON、无效关键词、未知客户 ID 或证据越界均终止失败，不修复、不重试、不换模型。
- API Key 保存在 macOS Keychain。没有“业务设置”、传输批准、成本估算或批量分析前置流程；用户发送本次问题即是本次按需分析的唯一触发点。
- 客户 Agent 默认模型为 `deepseek-v4-flash`。模型选择保存在本机 `agent_settings`，点击“模型连接”保存 Key 后必须调用 DeepSeek `GET /models` 刷新该账号完整可用模型列表；不可把模型写死为旧版 `deepseek-chat` 或 `deepseek-reasoner`。

## 已禁止的原生发送路径

- 2026-08-01 微信 `4.1.12.29/269341` 实机证明：调用内部 `StartTask` 并注入 Frida 构造的伪 C++ 对象/vtable 会在 `mars::stn` 线程触发 `EXC_BAD_ACCESS`，崩溃报告明确为 `possible pointer authentication failure`。
- 这是 Apple arm64e 指针认证边界，不是可通过更换 offset、延长超时或增加清理分支修复的普通 profile 问题。
- 崩溃证据：`~/Library/Logs/DiagnosticReports/WeChat-2026-08-01-165733.ips`。
- 验证结论是彻底删除原生发送，不得恢复旧 sender/profile，不得再对微信做发送 attach 实验。
- Frida 16.7.19 仅作为 Chatlog 密钥提取的内置运行时依赖；本 App 自身不 attach 微信。

## 构建与验证飞轮

- 系统 Python 是 `3.9.6`，Frida 锁定 `16.7.19`，Pydantic 锁定 `2.12.5`，Node 锁定 `24.14.0`，`@oai/artifact-tool` 锁定 `2.8.36`。
- `scripts/build_phase0_app.sh` 内置 Python、Chatlog、Frida、Pydantic、Node 和 artifact-tool；不创建或复制 `NativeWorker`。
- Chatlog 密钥提取会查找 `python3` 并导入 `frida`。App 必须把内置 `PythonRuntime/bin` 放在 `PATH` 首位，并传入完整 `PYTHONHOME`/`PYTHONPATH`。
- 必跑门禁：
  - `python3 -m unittest discover -s Tests -p 'test_*.py'`
  - `python3 -m compileall -q agent_core`
  - `node --check scripts/build_lead_workbook.mjs`
  - `bash -n scripts/*.sh`
  - `clang -fsyntax-only -fobjc-arc app/Phase0App/main.m`
  - `scripts/phase0_validate.sh --quick`
  - `scripts/phase0_validate.sh --no-fallback-scan`
  - `scripts/phase4_validate.sh`
  - `git diff --check`
- 回归测试必须断言发送模块、NativeWorker、profiles、Phase 6 和发送 UI 均不存在。
- 发布 DMG 必须只读挂载验证签名、内置依赖、Chatlog 许可证和构建清单；成功后删除中间 `.app`。

## 当前验证结果

- 2026-08-03：商品 UI 左侧固定为三个独立原生栏目：“仪表盘”、“客户表”和“消息检索”。仪表盘在 AppKit 中原生显示完整聊天分析结构；客户表独立承载 Phase 4 原生 DeepSeek 筛选工作区；消息检索复用 Chatlog `/api/v1/sessions` 和 `/api/v1/history` 的本机查询能力。不得使用 `WKWebView`、不得打开 `127.0.0.1:5030` 网页、不得暴露参考工具的其他栏目。仪表盘统计与消息检索是确定性本地查询；只有用户点击“生成 DeepSeek 摘要”时才调用 LLM，且必须复用客户表的同一 DeepSeek Base URL、Model、Keychain Key 和外部传输批准，不得引入 GLM 或第二套 AI 配置。未发布 DeepSeek 分析时四项客户 KPI 必须为 0，`eligible_conversations` 只能在未就绪说明中显示。
- 2026-08-02：实机证明微信已登录、SIP 已关闭且 Chatlog 最终健康时，App 仍可因固定次数的启动等待过早显示“未就绪”。已验证的唯一连接路径是：App 启动并持有 Chatlog `start-http` 进程，后台同时核验该进程监听 `127.0.0.1:5030` 与 `/health` 返回 `status=ok`，真正就绪后自动继续账号、解密、同步和语料构建；不得恢复固定等待次数或把此错误归因于微信重新登录。
- 2026-08-03：仪表盘实机压力验证发现，脱离 App 的旧 Chatlog 进程可独占 5030，使当前 App 启动的新进程无法监听，请求却命中卡死旧服务。实际清理已确认的旧进程后，唯一当前 Chatlog 服务在约 17 秒内完成整页真实聚合。仪表盘客户端等待上限为 180 秒，不得缓存、伪造或降级统计结果；服务必须继续遵循“当前 App 持有进程 + 该 PID 监听 + 健康检查”的唯一路径。
- 2026-08-09：仪表盘群聊统计改为调用 Chatlog `/api/v1/sessions` 的分页全量读取（每页 500 条）并逐一统计全部真实群聊，不再保留前 12/500 个群的产品截断；仅使用 Chatlog 已确认支持的 `last-1d`、`last-30d` 和 `all` 时间范围，`today` 映射为 `last-1d`。完整统计在后台任务执行，主界面不被群聊数量阻塞；逐群卡片和群聊对比表同时显示消息类型结构。
- 2026-09-09：本机正在运行的微信为 `4.1.13/269627`，SIP 已关闭。对该版本实测 Chatlog `start-http` 健康检查、`decompress-data`、15 个主数据库的只读验证、隔离状态库中的 `sync --limit 5000`（发布 1,419 个会话）和完整 183 天语料构建（270 个双向私聊、41,029 条本地证据）均通过；交付 DMG 内的 Chatlog、`dashboard_data.py` 与 `chatlog_client.py` 和源码一致，DMG 校验与签名验证通过。为避免重启用户微信，本次未强制执行无既有密钥状态下的 `restart-and-get-key`。
- 2026-09-10：当前 Chatlog 实机服务仍忽略 `/api/v1/sessions` 的 `offset`。已验证的全量读取方式是仅使用有效 `limit` 并按 500、1,000、2,000…递增；每轮必须包含上一轮所有会话 ID，直到返回数量小于当前 `limit`。这既避免重复页静默截断，也会在服务数据变动时明确失败。微信 4.1.13 实测得到全部 1,420 个会话，仪表盘已完成 23 个活跃群、30 天趋势、24 小时分布和发言排行的真实聚合。
- 2026-09-10：消息检索界面读取完整会话集，原生可输入选择框加载上限为 5,000；实测加载全部 1,420 个会话。不得恢复 500 条 UI 截断，也不得使用失效的 `offset` 分页。
- 2026-09-10：Chatlog 的 `/health` 会早于实际数据接口返回成功；不得仅凭健康检查打开仪表盘或消息检索。应用必须同时确认会话接口已有结果且 `/api/v1/db` 已返回消息数据库，再发起读取。已在 `/Applications/WeChatSalesAgent.app` 冷启动实测，仪表盘由“正在启动”进入完整统计，无 `CHATLOG_SERVICE_UNAVAILABLE` 或空会话错误。
- 2026-09-10：客户表为 DeepSeek 客户 Agent 对话工作台。不会在同步后预先识别业务或给对话批量打标签；只有用户发送问题才启动本次检索。Agent 从问题生成时间范围、概念组及其同义表达，在真实时间窗口内扫描全部已发布双向私聊；候选不再有固定 24 条上限。每个候选使用命中证据和相邻上下文进行首轮判断，再由不读取首轮结论的第二轮独立审计找回漏判并移除误报。任一批次缺少客户、出现重复或未知 `customer_id`、证据越界时整项任务必须失败。对话筛选结果成为当前客户表和 Excel 导出的唯一数据集；Keychain API Key 缺失时必须明确失败，不得降级为虚构答复。
- 2026-09-10：已实测重建并替换 `/Applications/WeChatSalesAgent.app`。客户表 Agent 操作区只保留“连接”和对话执行；应用内已无“业务设置”、传输批准、成本估算、批量运行或刷新结果按钮。全套 77 个测试、Objective-C 语法检查、DMG 校验、签名校验和安装包内 Agent 与 Excel 导出源文件一致性均通过。
- 2026-09-10：客户表重构为 Codex 式单一任务工作台：顶部只保留任务状态和 Excel 导出，主体是连续任务记录，底部固定多行编辑器、模型选择、连接和执行按钮；侧栏顺序固定为“仪表盘、消息检索、客户表”。模型选择位于编辑器下方；空白态文案由单独的、不命中鼠标事件的原生标签承载并随输入切换，不能恢复 `NSTextView` 自绘占位路径。界面只保留“理解任务、证据召回、语义复核、覆盖审计”四行真实过程并原位更新完成批次；完成后显示前 12 位摘要和完整总数，其余结果进入 Excel。默认模型为 `deepseek-v4-flash`，该 Key 的官方 `/models` 返回 `deepseek-v4-flash`、`deepseek-v4-pro`、`deepseek-v4-flash-vision-exp` 三项。
- 2026-09-10：安装版真实执行“找出近半年和我有创业讨论的人”成功：时间条件为 183 天，扫描 271 个双向私聊，召回 231 个候选；首轮确认 64 位，独立覆盖审计找回 6 位、移除 10 位，最终确认 60 位。检索规划使用 DeepSeek 官方思考模式；批量判断使用确定性 JSON 输出，避免隐藏推理耗尽输出预算。界面展示的是可验证的执行轨迹与覆盖数字，不展示模型私有思维链。
- 2026-09-10：按需 Agent 的导出输入必须为 `agent.query.v1`，不能要求旧批量分析的 `workspace.v2` 发布快照。`exportWorkbook:` 必须从当前 Agent 结果构造该任务的指标、模型、问题和线索数据后调用 `Export/build_lead_workbook.mjs`。导出器同时支持 `workspace.v2` 与 `agent.query.v1`，在完成内部公式检查和保存后删除运行库生成的 `.inspect.ndjson` 诊断旁文件，只保留 `.xlsx`。安装版已实测真实结果导出到 `~/Desktop/DeepSeek客户查询结果-验证.xlsx`：包含“分析概览”和“客户激活表”、60 条数据、无公式错误且 ZIP 结构完整；概览大数字行高必须保持 34，避免渲染裁切。
- 2026-08-02：首次同步后重建工作台时，必须先创建并显示新窗口再隐藏旧窗口，否则 `applicationShouldTerminateAfterLastWindowClosed` 会在同步已成功后退出 App。首次同步数据库在尚未运行 DeepSeek 时可合法不存在 `analysis_runs` 和 `lead_results`，工作台就绪读模型必须返回真实账号与待筛选会话数，DeepSeek 发布数与线索数为 0，不得将缺少 AI 表误报为数据库损坏或未连接。
- 2026-08-02：最终安装版实机重新同步成功，1,206 个微信会话中排除 407 个无双向文字、332 个公众号、214 个群聊、5 个系统会话和 1 个服务会话，剩余 247 个已同步双向私聊。当时本机 `business_profiles=0`、`ai_settings=0`且 DeepSeek Keychain 项不存在，所以 247 未经过任何关键词或 DeepSeek 筛选。
- Phase 0 quick、无兜底扫描、Phase 4 AppKit 界面、真实 XLSX 导出全部通过。
- 只读挂载最终 DMG 后确认不存在 `NativeWorker`、`send_cli.py`、`send_daemon.py`、`send_store.py` 或原生 sender。
- 当前 DMG：`dist/WeChatSalesAgent-MVP-macOS-arm64.dmg`，SHA-256 `48d6f5f48d05fb857670edbabea22cab7f29581170406ffadb9900d2f5c4cf30`，132,250,354 bytes，生成于 2026-09-10 15:48:14 CST；已重新生成并由构建脚本只读挂载验证签名、内置依赖、Chatlog 许可证和构建清单，随后替换 `/Applications/WeChatSalesAgent.app` 并再次验证签名。安装版主程序 SHA-256 为 `67beff3ab03945dcbf686f5ec44d50a5600bf91714febfc9a6244733b5dc5ff6`，生成于 2026-09-10 15:48:27 CST。该版本包含递增 limit 的完整会话读取、全量逐群对比卡、群聊对比表、消息类型结构、24 小时活跃度、直接消息库聚合的 30 天趋势、热点摘要、全范围按需 DeepSeek 客户 Agent 和当前可查询数据库。

## 交付限制

- Chatlog 密钥提取要求 macOS 关闭 SIP；不得宣称默认 Mac 开箱即用，不得用重签名微信等更高风险路径伪装解决。
- App 左侧必须实时显示 SIP 状态，提供 Apple Silicon 恢复模式指引和重新检测；SIP 未关闭时在启动 Chatlog 前终止连接。
- 当前机器没有 Developer ID 签名身份，构建物为 ad-hoc 签名、未公证；不得宣称已完成 Apple 正式签名/公证。
- 每次重建后只保留当前 DMG 的 SHA-256 和字节数，不叠加旧值。

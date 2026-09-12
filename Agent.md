# Project Agent Notes

## 产品边界

- 产品是 macOS Apple Silicon 原生 AppKit 桌面 App，不是网页、Codex Skill 或脚本集。
- 当前只保留三条完整主链：微信私聊同步、DeepSeek 智能分析、分析工作台与动态 Excel 导出。
- 应用不得向微信发送文本、图片、视频或文件；不得保留发送按钮、批次状态库、发送 CLI、守护进程、NativeWorker、Frida 发送脚本或微信 profile。
- 不得用剪贴板、键鼠模拟、系统分享、Hermes 或其他通道代替微信发送。
- 会话候选仅表示进入 DeepSeek 筛选的双向私聊，模型分析前不得称为客户或线索。

## 当前目录真相

- `app/Phase0App/main.m`：唯一桌面 UI，负责首次连接、按需 DeepSeek Agent 查询、智能分析结果和 Excel 导出。
- `app/Phase0App/WeChatCustomerAnalysisArtwork.png`：保留的原始图标画稿；`scripts/prepare_app_icon.m` 只移除连通外白底并把主体缩放到 macOS 安全区，生成 1024×1024 RGBA `WeChatCustomerAnalysisIcon.png`，再生成 `WeChatCustomerAnalysis.icns`。构建时必须把 ICNS 打包到 `Contents/Resources` 并由 Info.plist 指定。
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
- 对外应用名称统一为“微信客户分析 Agent”；应用图标、Info.plist、窗口标题、侧栏品牌、README 和 DMG 卷标必须同步，缺一不得还原“微信客户激活 Agent”或“WeChat Sales Agent”对外文案。

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
- 2026-09-10：客户机首次安装时没有 `~/.chatlog/chatlog.json`，直接执行 `action start-http` 已复现为 `data dir is empty` 并立即退出。连接顺序必须是：`list-accounts` 明确选号、`prepare-runtime` 为当前账号取密钥并解密数据库、再由 App 持有 `start-http` 进程，最后校验该 PID 监听与读接口就绪。不得恢复“先启动 HTTP、后准备账号”的仅开发机有效路径。
- 2026-09-11：多账号连接必须把用户第一次选择的 `account_id` 作为整次事务的唯一参数，贯穿 `prepare-runtime`、`start-http --history`、`/api/v1/db` 路径校验、同步、语料与界面；不得在服务就绪后重新枚举选号，也不得复用绑定另一账号的旧 HTTP 进程。历史账号只能复用已保存密钥，缺钥必须明确失败，禁止调用 `restart-and-get-key` 终止当前微信。选择器标注“当前登录/历史账号”，客户工作台显示绑定 wxid。仪表盘私聊列表必须复用 `static_exclusion`，排除 `brandsessionholder`、公众号和服务通知等非私聊会话。已在真实双账号机器完成全量闭环：当前测试号 `wxid_7gmgmchei4wc12_4b06` 被标记为“当前登录”，原账号 `wxid_3prysbeqgvci22_9f8d` 保持为历史账号；首次取密钥的受控重启成功，随后在 App 内再次“连接此账号”时微信 PID 保持不变。最终 HTTP 进程明确带 `--history wxid_7gmgmchei4wc12_4b06`，20 条数据库路径全部属于该测试号，已同步 2 个会话、排除 1 个系统占位会话、得到 1 个真实双向私聊；消息检索实测返回 2 条原始消息，仪表盘显示该私聊共 2 条消息（我发送 1 条、对方发送 1 条）、群聊为 0，所有数据库路径均绑定当前测试号，原账号已发布的 1,420 个会话未混入。本轮多账号 mock 在内的 85 项 Python 测试、Python `compileall`、Node/Shell/Objective-C 语法检查、`git diff --check`、无兜底扫描、Phase 0 quick 及 Phase 4 原生端到端验证均通过。
- 2026-09-11：卸载重装后 5030 不可用已在隔离首装环境复现。Chatlog 的 `list-accounts` 依赖 `lsof`；Finder/LaunchServices 启动环境若没有 `/usr/sbin`，真实微信会被错误识别为 `未登录微信_<PID>`。`agentEnvironment` 必须固定为内置 Python 后接 `/usr/bin:/bin:/usr/sbin:/sbin`，不得依赖继承的 PATH。首次 `decompress-data` 还可能在 `~/.chatlog/wcdb_cache` 留下非 SQLite 的加密缓存，`prepare-runtime` 必须在 HTTP 启动前按 SQLite 文件头删除这类无效 `.db` 及其 `-shm`/`-wal`；当前账号即使同时出现在 history 也必须按 current 处理，且 HTTP 启动后不得重复解密。隔离环境实测移除 1 个无效缓存后 `/api/v1/db` 与 sessions 正常；最终安装版由 App PID `17878` 持有 Chatlog PID `17955`，服务绑定 `wxid_3prysbeqgvci22_9f8d`，14 个 message DB、1,424 个会话均通过，界面发布 276 个双向私聊。
- 2026-09-11：应用图标原图是 1254×1254 RGB，不透明白底且主体顶满画布。修正后的主 PNG 为 1024×1024 RGBA，四角 alpha=0，主体可见边界约 830×829（约占画布 81%）；ICNS 由该主图生成。Finder `/Applications` 图标视图实测无白边，视觉尺寸与相邻正常 App 一致。发布脚本必须逐字节比对 DMG 内 ICNS 与项目主 ICNS。
- 2026-09-10：客户表为 DeepSeek 客户 Agent 对话工作台。不会在同步后预先识别业务或给对话批量打标签；只有用户发送问题才启动本次检索。Agent 从问题生成时间范围、概念组及其同义表达，在真实时间窗口内扫描全部已发布双向私聊；候选不再有固定 24 条上限。每个候选使用命中证据和相邻上下文进行首轮判断，再由不读取首轮结论的第二轮独立审计找回漏判并移除误报。任一批次缺少客户、出现重复或未知 `customer_id`、证据越界时整项任务必须失败。对话筛选结果成为当前客户表和 Excel 导出的唯一数据集；Keychain API Key 缺失时必须明确失败，不得降级为虚构答复。
- 2026-09-10：已实测重建并替换 `/Applications/WeChatSalesAgent.app`。客户表 Agent 操作区只保留“连接”和对话执行；应用内已无“业务设置”、传输批准、成本估算、批量运行或刷新结果按钮。全套 77 个测试、Objective-C 语法检查、DMG 校验、签名校验和安装包内 Agent 与 Excel 导出源文件一致性均通过。
- 2026-09-10：客户表重构为 Codex 式单一任务工作台：顶部只保留任务状态和 Excel 导出，主体是连续任务记录，底部固定多行编辑器、模型选择、连接和执行按钮；侧栏顺序固定为“仪表盘、消息检索、客户表”。模型选择位于编辑器下方；空白态文案由单独的、不命中鼠标事件的原生标签承载并随输入切换，不能恢复 `NSTextView` 自绘占位路径。界面只保留“理解任务、证据召回、语义复核、覆盖审计”四行真实过程并原位更新完成批次；完成后显示前 12 位摘要和完整总数，其余结果进入 Excel。默认模型为 `deepseek-v4-flash`，该 Key 的官方 `/models` 返回 `deepseek-v4-flash`、`deepseek-v4-pro`、`deepseek-v4-flash-vision-exp` 三项。
- 2026-09-11：客户表主区不得重复侧栏中的“微信客户分析 Agent”标题；顶部仅保留任务状态与 Excel 导出。正文和编辑器的 `NSScrollView` 必须关闭水平、垂直滚动条并移除编辑器默认边框，保留滚轮滚动但不绘制右侧槽线。任务开始后四阶段时间线必须始终可见：已完成阶段显示绿色勾选，当前阶段显示蓝色圆点及真实对话数、候选数和批次进度，未开始阶段显示灰色空心圆；完成页继续展示 `analysis_trace` 的实际覆盖数字，不得展示或伪造模型私有思维链。`--render-agent-preview` 用确定性示例渲染该状态，供发布前视觉核验。
- 2026-09-11：客户表空白态中央不得显示“准备就绪”或账号说明；账号、同步数量和“可以开始提问”统一使用绿色状态文案，放在右上角与“导出 Excel”垂直居中。编辑器按回车直接发送，`Shift+回车`插入换行，中文输入法存在 marked text 时不得误发送。发送按钮必须相对整个 composer 上下居中；Agent 任务从开始到成功或失败之间必须持续运行原生 `NSProgressIndicator` 动画，结束后停止并隐藏。
- 2026-09-12：侧栏第三项对外名称固定为“智能分析”。“连接并同步微信”“关闭 SIP 指引”和 SIP 实时状态必须组成独立工具区，以 `sidebar.bottomAnchor` 固定在左侧底部，不能再跟随第三个导航按钮向上排列。原生过程态截图已确认窗口缩放后工具区仍保持底部位置。
- 2026-09-12：按需 Agent 输出协议升级为 `agent.query.v2`。规划必须先识别 `customer_search`、`person_profile`、`relationship_insight`、`topic_analysis`、`timeline` 或 `general_search`，同时生成指定联系人、分析维度和结果标题。人物与关系任务必须按联系人显示名锁定本人会话，只分析对方本人发言与互动事实；联系人不存在时返回无证据，禁止把第三方提及者当作分析对象。每条结构化洞察和最终答案分节都必须引用本次候选中的真实 evidence ID；最终结果提供 2 至 4 个可继续执行的分析问题。
- 2026-09-12：动态 Excel 必须随任务改变工作表与字段。`agent.query.v2` 固定包含“分析结果”和“证据明细”，中间任务表分别为“客户清单”“人物画像”“关系洞察”“话题分析”“事件时间线”或“相关结果”；人物任务不得出现意向等级、建议话术或 AI 成本等客户模板字段。导出后必须删除 `.inspect.ndjson` 旁文件，并对每张表执行内容检查、公式错误扫描和渲染核验。
- 2026-09-12：真实执行“杨凯说的最多的话是什么，他是一个什么样的人”已通过：扫描 276 个双向私聊，只召回并确认杨凯本人 1 位；基于 1,524 条消息统计，返回高频用语、性格、沟通风格、情绪、价值观、兴趣、行为模式和他人互动印象 8 个有证据维度，引用 38 条真实证据并给出 4 个后续分析问题。不得恢复按内容命中“杨凯”后把其他联系人作为客户结果的旧行为。
- 2026-09-12：Agent 会话以账号隔离的 `agent_sessions`/`agent_turns` 持久化，最近 6 轮问题、任务类型、分析对象、答案与后续建议用于解析指代和追问。真实同一会话执行“杨凯最常说什么”后追问“那他在压力下有什么变化”已确认继续锁定杨凯本人，不会重置为无对象新查询。
- 2026-09-12：精确互动统计必须由本地全量消息确定性计算，包含双方消息数、活跃天数、首末联系、重复句、双方发起次数、回复中位分钟、活跃小时和近 12 月活跃度；模型不得估算这些数字。每个分节同时输出置信度、支持证据和反例，证据链包含前 2 条、当前消息和后 2 条上下文，原生 UI 链接点击后展示原文。
- 2026-09-12：任务工具箱固定支持客户筛选、成交机会、重新激活、客户风险、承诺待办、人物画像、关系洞察、多人比较、话题分析、事件时间线和通用检索。承诺与时间线必须输出带日期、状态、对象和证据的结构化条目；人物与关系任务不使用客户意向模板。
- 2026-09-12：已保存分析的增量起点必须是“保存时已发布语料的最新消息时间”，不是上次结论最后引用的证据时间；否则会把未引用的旧消息误判为新消息。真实数据已复验保存后立即刷新为 `unchanged`、`new_evidence_count=0`且答案不变。
- 2026-09-12：“导出报告”必须在导出前选择 Excel/PDF/文本与证据、统计、后续问题、可编辑图表内容。Excel 根据任务实际生成工作表和字段；PDF 由 App 原生生成、自包含且支持多页排版。能力验证 Excel 的 ZIP 结构、全表内容、公式错误扫描与四页渲染均通过；PDF 为单页 A4，核心回答、分节置信度、时间线、统计、证据、边界和后续问题均已渲染核对。
- 2026-09-12：智能分析默认必须使用当前账号的全部可用历史：App 构建语料固定传入 `--all-history`，Agent 未指定时间时使用全历史窗口，进度和边界说明必须来自语料的实际首末证据时间。不得回退为 183 天或把配置天数当成实际覆盖天数。
- 2026-09-12：当前账号不存在时智能分析必须明确失败，禁止回退到最近同步账号。`prepare-runtime` 只能清理当前所选账号数据目录中与真实 DB 路径匹配的无效 Chatlog 缓存，且使用中文件必须终止而不是删除；不得跨账号扫描缓存。
- 2026-09-12：已保存分析的选择只加载本机结果，“检查更新”才允许分析新证据；无新消息时必须在读取 Keychain 和请求模型前返回。过往会话轮次只保留指代所需的紧凑上下文，完整结果只在已保存分析中保留一份；每账号最多保留 100 个未保存会话。
- 2026-09-12：新语料发布成功后必须在同一账号内删除已被取代的语料、证据、AI 运行与数据代，再执行 SQLite 紧缩；当前已发布数据、其他账号及正在构建的数据不得受影响。该整理只允许在新语料完整发布后执行。
- 2026-09-12：分析任务的评分语义必须和场景一致：客户筛选使用“成交意向”，机会分析使用“机会强度”，重新激活使用“激活优先级”，客户风险使用“风险严重度”。智能 Excel 已用 5 类真实 XLSX 生成、公式扫描和图片渲染验证；“最近联系”必须显示为 `yyyy-mm-dd hh:mm`，分析结论表必须明示置信度、支持证据和反例证据列。导出 JSON 必须经标准输入直接传给内置 Node，禁止在临时目录写入明文微信证据。
- 2026-09-12：连接、同步、语料构建、分析保存/读取/更新/删除、Excel/PDF/文本导出均必须在后台队列执行，只在主队列更新 AppKit 控件。PDF 分页优先使用段落边界，不得在普通情况下把标题与内容拆到两页。
- 2026-09-12：Chatlog `/api/v1/history` 的 `total_count` 会在刚完成解密后继续增长，按固定总数和 `offset` 分页会丢失后续消息。已验证的完整历史读取方式与 sessions 一致：从 offset 0 开始按递增 `limit` 读取，每轮必须完整包含上一轮全部消息标识，直到返回数量小于 limit，最终数量必须等于本轮 `total_count`；发现重复、倒退或非包含变化必须明确失败。真实异常联系人最终完整取回 21,116 条消息（对方 10,575、我方 10,541）。
- 2026-09-12：已在当前账号 `wxid_3prysbeqgvci22_9f8d` 完成全历史实机闭环，App 持有的 Chatlog 进程、5030 监听 PID 与 `/api/v1/db` 账号路径一致；发布语料包含 168,753 条证据、659 个双向私聊，实际覆盖 2019-09-30 10:22 至 2026-09-12 21:12。原先约半年语料只有 41,314 条证据，证明本轮不是继续复用旧时间窗。
- 2026-09-12：语料留存清理必须为 `extracted_facts.evidence_id` 与 `corpus_evidence.evidence_id` 建索引；否则 SQLite 开启外键后批量删除每条证据都会反复全表扫描。真实库旧路径运行超过 17 分钟仍未结束，补索引后建索引、清理和紧缩合计 13.993 秒，数据库由 402,173,952 bytes 降至 146,780,160 bytes；仅删除当前账号 8 份旧语料，另一账号的 4 份旧语料和 1 份已发布语料均保留。
- 2026-09-12：全历史安装前实机执行“杨凯说得最多的话是什么，他是一个什么样的人”已通过。界面以持续动画和四阶段真实进度运行，回车可直接发送；最终只确认杨凯本人 1 位，基于 1,926 条消息与 95 个活跃日输出高频话语、八维人物画像、置信度、38 条证据、时间线、边界说明和 4 个后续问题。真实自适应 Excel 包含“分析结果”“人物画像”“证据明细”“互动统计”4 张工作表，ZIP、导入和内容检查通过，不含旧客户通用模板字段。
- 2026-09-10：安装版真实执行“找出近半年和我有创业讨论的人”成功：时间条件为 183 天，扫描 271 个双向私聊，召回 231 个候选；首轮确认 64 位，独立覆盖审计找回 6 位、移除 10 位，最终确认 60 位。检索规划使用 DeepSeek 官方思考模式；批量判断使用确定性 JSON 输出，避免隐藏推理耗尽输出预算。界面展示的是可验证的执行轨迹与覆盖数字，不展示模型私有思维链。
- 2026-09-10：按需 Agent 的导出输入必须为 `agent.query.v1`，不能要求旧批量分析的 `workspace.v2` 发布快照。`exportWorkbook:` 必须从当前 Agent 结果构造该任务的指标、模型、问题和线索数据后调用 `Export/build_lead_workbook.mjs`。导出器同时支持 `workspace.v2` 与 `agent.query.v1`，在完成内部公式检查和保存后删除运行库生成的 `.inspect.ndjson` 诊断旁文件，只保留 `.xlsx`。安装版已实测真实结果导出到 `~/Desktop/DeepSeek客户查询结果-验证.xlsx`：包含“分析概览”和“客户激活表”、60 条数据、无公式错误且 ZIP 结构完整；概览大数字行高必须保持 34，避免渲染裁切。
- 2026-08-02：首次同步后重建工作台时，必须先创建并显示新窗口再隐藏旧窗口，否则 `applicationShouldTerminateAfterLastWindowClosed` 会在同步已成功后退出 App。首次同步数据库在尚未运行 DeepSeek 时可合法不存在 `analysis_runs` 和 `lead_results`，工作台就绪读模型必须返回真实账号与待筛选会话数，DeepSeek 发布数与线索数为 0，不得将缺少 AI 表误报为数据库损坏或未连接。
- 2026-08-02：最终安装版实机重新同步成功，1,206 个微信会话中排除 407 个无双向文字、332 个公众号、214 个群聊、5 个系统会话和 1 个服务会话，剩余 247 个已同步双向私聊。当时本机 `business_profiles=0`、`ai_settings=0`且 DeepSeek Keychain 项不存在，所以 247 未经过任何关键词或 DeepSeek 筛选。
- Phase 0 quick、无兜底扫描、Phase 4 AppKit 界面、真实 XLSX 导出全部通过。
- 只读挂载最终 DMG 后确认不存在 `NativeWorker`、`send_cli.py`、`send_daemon.py`、`send_store.py` 或原生 sender。
- 当前 DMG：`dist/WeChatSalesAgent-MVP-macOS-arm64.dmg`，SHA-256 `b46bebce3d8c2257a391841230a735e07ee2f1125aa3e88756ac8a61e5bee246`，133,151,815 bytes，生成于 2026-09-11 21:26:03 CST；91 项测试、编译检查、锁定依赖、无降级扫描、Phase 0、Phase 4、空白态及 Agent 动画过程态原生截图、只读挂载、签名、Chatlog 许可证、构建清单和 ICNS 一致性均通过，`hdiutil verify` 有效。安装版主程序 SHA-256 为 `2c20744d8698261379d5cab65e009dcaaf0f2b8d62fab49afb516af971ad8be7`、376,624 bytes；安装版 ICNS SHA-256 为 `f2069437380dfd97849817ed2e93648524e4f45ff25e9fd33ffaa5762d46f563`，与项目一致。

## 交付限制

- Chatlog 密钥提取要求 macOS 关闭 SIP；不得宣称默认 Mac 开箱即用，不得用重签名微信等更高风险路径伪装解决。
- App 左侧必须实时显示 SIP 状态，提供 Apple Silicon 恢复模式指引和重新检测；SIP 未关闭时在启动 Chatlog 前终止连接。
- 当前机器没有 Developer ID 签名身份，构建物为 ad-hoc 签名、未公证；不得宣称已完成 Apple 正式签名/公证。
- 每次重建后只保留当前 DMG 的 SHA-256 和字节数，不叠加旧值。

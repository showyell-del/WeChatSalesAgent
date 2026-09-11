---
status: resolved
trigger: "用户反馈：其他设备导入聊天记录后会话数量不完整或只能看到数量却查不到内容，仪表盘偶发报错；切换微信账号后应用仍显示初始账号；连接另一个账号可能导致微信闪退。"
created: 2026-09-10
updated: 2026-09-11
---

# Symptoms

- expected: 导入后的全部真实会话和具体消息应一致可读，仪表盘应稳定完成；应用应明确显示当前登录微信账号；切换账号连接不应导致微信退出。
- actual: 会话总数与精确消息查询不一致，仪表盘偶发失败；账号切换后仍显示初始账号；连接第二个账号时微信可能闪退。
- errors: 用户未提供具体错误码，截图显示 963 个会话但查询结果为空，客户表仅同步 12 个对话，仪表盘私聊账号显示 brandsessionholder 且消息为 0。
- timeline: 在其他设备导入聊天记录、切换微信账号后出现。
- reproduction: 导入聊天记录或切换账号后连接微信，进入消息检索、仪表盘和客户表观察账号、会话数及消息内容。

# Current Focus

- hypothesis: 已确认并修复：账号未贯穿连接事务、HTTP 服务隐式复用旧账号、历史账号自动重启取钥，以及仪表盘未排除系统会话。
- test: 多账号、安全取钥、HTTP 账号绑定、仪表盘系统会话排除的回归测试，加完整项目门禁。
- expecting: 修复后所有已执行门禁通过。
- next_action: 在真实双账号客户机按相同显式账号链路做最终现场确认。
- reasoning_checkpoint:
    hypothesis: 一次连接中账号选择未被持久绑定，导致解密准备、HTTP 数据源、同步与 UI 可能属于不同账号；历史账号缺钥路径还会执行明确会重启微信的动作。
    confirming_evidence:
      - connectWeChatData 选择账号并 prepare 后，finishWeChatSync 再次执行 accounts/selectedAccountIDFromLines，首个选择没有传递。
      - Chatlog start-http 支持 --history，但 App 三处启动均未传；运行中的 self.chatlogServiceTask 在外部切号后仍被复用。
      - chatlogReadAPIIsReady 只检查会话非空和任意 message DB，不检查路径中的账号；prepare-runtime 对非当前账号缺钥也调用 restart-and-get-key。
      - 账号与 --history 服务对齐时，本机 stats 2664 条与 history 1301+1363 条完全一致，另有独立实机验证 1420 会话及具体 history 均可读。
    falsification_test: 若初始账号已贯穿 finish/start-http/readiness，或显式对齐后 history 仍系统性为空，则该根因被否定；源码与实机计数均显示相反结果。
    fix_rationale: 将选中账号作为单一连接参数传到服务启动、读就绪、同步和 UI，替换不同账号的旧服务，并禁止历史账号自动重启取钥，可从根源消除跨账号/跨数据代读写和误重启，而非掩盖空结果。
    blind_spots: 当前机器只有一个账号，无法实机执行双账号切换；以 mock 多账号测试和显式账号路径校验覆盖该条件，最终仍需用户在真实双账号机器确认。
- tdd_checkpoint:

# Evidence

- timestamp: 2026-09-10T00:00:02+08:00
  checked: 项目 Agent.md 与历史验证记录
  found: 已验证连接顺序必须是 list-accounts 明确选号、prepare-runtime 为当前账号取密钥并解密、App 持有 start-http；/health 早于数据就绪，且 sessions offset 无效，需递增 limit 全量读取。
  implication: 当前故障最先应检查实现是否真正把显式账号从 UI 贯穿到 prepare-runtime、Chatlog 配置和所有读接口，不能恢复旧的先 start-http、仅 health 就绪或 offset 分页路径。
- timestamp: 2026-09-10T00:00:03+08:00
  checked: app/Phase0App/main.m 账号连接调用链
  found: connectWeChatData 先枚举并选择 selectedAccountID、调用 prepare-runtime；服务就绪后 finishWeChatSync 又重新执行 accounts 和 selectedAccountIDFromLines，再把第二次结果传给 sync。首个选择没有保存或传入 finishWeChatSync。
  implication: 一次连接存在两个独立账号决策点；若 current 标记或用户选择发生差异，解密准备、HTTP 服务与同步可绑定不同账号，足以解释账号显示、会话数量与消息内容不一致。
- timestamp: 2026-09-10T00:00:03+08:00
  checked: agent_core/sync_cli.py command_prepare_runtime
  found: 对非 current 账号使用历史账号参数调用 status；若 data_key 无效则直接调用 restart-and-get-key，再解密所选账号。
  implication: 历史/第二账号缺密钥时存在会重启取钥的路径，需验证其是否就是微信闪退机制，并决定安全的当前账号绑定方式。
- timestamp: 2026-09-10T00:00:04+08:00
  checked: Chatlog 4.1.13 实机 list-accounts/status/config（密钥已脱敏）
  found: list-accounts 同一账号同时返回 process/current=true 与 history/current=false 两条；配置单独保存 last_account。status 返回的 work_dir 属于历史解密目录。当前机器只存在一个账号，无法直接复现多账号，但证明 current 进程记录与 history 配置记录是两种来源。
  implication: 不能把 current 标记、历史解密配置和 HTTP 当前数据源当作同一事实；必须以显式账号贯穿连接事务并验证 HTTP 数据库路径。
- timestamp: 2026-09-10T00:00:04+08:00
  checked: Chatlog action CLI 帮助
  found: start-http、status、switch-account、restart-and-get-key、decompress-data 均支持 --history；restart-and-get-key 的官方动作说明为“重启微信并获取数据库密钥”。现有 App 所有 start-http 调用均未传 --history。
  implication: HTTP 服务当前依赖隐式 last_account；restart-and-get-key 可直接解释用户看到的微信退出，且显式 --history 可用于把 HTTP 数据源锁定到用户选择账号。
- timestamp: 2026-09-10T00:00:05+08:00
  checked: App 服务生命周期与账号可见性
  found: 仪表盘、消息检索和连接流程都复用仍在运行的 self.chatlogServiceTask；外部切换微信账号不会使旧服务失效。客户工作台 startupDetailText 只显示已同步会话数，不显示 snapshot.account_id。
  implication: 旧服务可继续提供初始账号数据，且用户没有界面证据辨认当前本地数据绑定；修复需要在账号切换时替换为显式账号服务，并展示绑定账号。
- timestamp: 2026-09-10T00:00:06+08:00
  checked: Chatlog 官方公开仓库与本地自描述接口
  found: 公开上游未包含本项目 bundled action 扩展；本地 list-accounts 的可验证字段只有 account、current、status、data_dir/work_dir 等，没有昵称字段。
  implication: UI 只能可靠显示 wxid 与当前/历史状态及路径摘要，不能杜撰微信昵称；账号身份仍应由显式 wxid 贯穿。
- timestamp: 2026-09-10T00:00:07+08:00
  checked: 显式当前账号服务的 stats 与 /api/v1/history 计数
  found: 同一私聊 stats.total=2664，is_self=false total_count=1301，is_self=true total_count=1363，方向合计与统计完全一致；独立检查也确认 1420 会话与具体 history 在账号对齐时可读。
  implication: message_search 的方向查询不是空内容主因；错误来自服务/数据库账号未对齐。
- timestamp: 2026-09-10T00:00:08+08:00
  checked: 新增多账号与安全取钥回归测试（修复前）
  found: 显式账号贯穿、历史密钥优先、历史账号禁止重启等测试按预期失败；进一步测试发现 prepare_account 在同步验证阶段仍调用 obtain_key(wxid_history)。
  implication: 自动重启路径有两个入口，必须同时收口；否则 prepare-runtime 安全后，sync 仍可终止微信。
- timestamp: 2026-09-10T00:00:10+08:00
  checked: 截图 brandsessionholder 与 dashboard_data 私聊选择逻辑
  found: dashboard_data 将所有 is_group=false 会话视为私聊并默认选择第一条；corpus_builder.static_exclusion 已明确把 brandsessionholder 判定为 SYSTEM_SESSION。
  implication: 仪表盘未复用统一会话分类，必然可能显示系统占位会话和 0 条统计；这是截图可直接复现的根因。
- timestamp: 2026-09-11
  checked: 修复后完整回归与静态门禁
  found: 85 项 Python 测试、Python compileall、Node 语法、Shell 语法、Objective-C 语法、git diff --check、无兜底扫描与 Phase 4 Python 测试全部通过。
  implication: 账号绑定、安全切换、统一会话分类和现有主流程的回归门禁均已满足。

# Eliminated

- hypothesis: message_search 的 is_self/offset 查询构造导致所有精确检索结果为空。
  evidence: 显式账号服务上 stats 与两方向 history 计数严格一致，且具体 history 可读取。
  timestamp: 2026-09-10T00:00:07+08:00

# Resolution

- root_cause: App 将账号选择、Chatlog 历史配置和 HTTP 服务当作隐式全局状态：连接前后两次独立选号，start-http 不绑定账号且复用旧进程，读就绪不验证数据库路径账号；历史账号缺钥还会调用 restart-and-get-key。因此切号后可继续读取初始账号或混合数据代，并可能重启微信。另有仪表盘未应用统一会话排除规则，导致 brandsessionholder 等系统会话被显示为私聊并产生 0 条假象。
- fix: 将首次 selectedAccountID 直接传到 finish；集中以 start-http --history accountID 启动服务，账号变化先停止旧服务；readiness 校验所有主数据库路径属于所选账号；sync 遇服务账号不匹配直接失败且验证阶段不再取钥；prepare-runtime 优先复用历史密钥并禁止历史账号自动重启；账号选择器标注当前/历史，工作台显示绑定 wxid；仪表盘复用 static_exclusion 排除 brandsessionholder 等系统会话。
- verification: 85 项 Python 测试全部通过；Python compileall、Node/Shell/Objective-C 语法检查、git diff --check、无兜底扫描与 Phase 4 Python 测试均通过。
- files_changed: [agent_core/sync_cli.py, agent_core/dashboard_data.py, app/Phase0App/main.m, Tests/test_phase1_sync.py, Tests/test_code_review_regressions.py, Tests/test_dashboard_data.py, Agent.md]

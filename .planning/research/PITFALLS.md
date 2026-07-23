# 微信客户成交 Agent：项目级失败模式

**领域：** macOS Apple Silicon 微信私聊线索分析与原生批量触达  
**研究日期：** 2026-07-23  
**总体置信度：** HIGH（项目实测、上游源码结论及官方文档交叉验证）

## 风险处理原则

- 失败关闭：版本、哈希、账号、数据库、证据、模型输出、Ack 或清理任一不确定，当前任务即失败。
- 不做兜底：不得切换旧快照、其他模型、其他供应商、模糊证据、系统自动化、剪贴板、键鼠模拟或附件类型替代。
- 不自动重发：发送结果不确定不等于失败；必须阻断该队列并人工核对，避免重复触达。
- 不保留失效路径：已被 Spike 001 否定的 `uploadappattach -> sendappmsg` 简单文件路径应从生产代码与可见能力中移除。
- 所有关键产物必须可绑定：`账号 + 数据快照 + 联系人 + 消息证据 + 模型/提示版本 + 发送清单 + native profile`。

## Critical Pitfalls

### 1. 微信版本、运行进程与 dylib 哈希漂移

**What goes wrong：** 只检查界面版本号，或只检查磁盘上的 WeChat.app，却向另一路径启动的进程注入。偏移仍能落到“可执行地址”，但语义已经变化，最终造成取错钥、微信崩溃或把任务发给错误对象。  
**Why it happens：** 微信自动更新、同时存在多个应用副本、运行进程未重启、build 相同但二进制不同、只校验完整文件而未校验实际加载的 arm64 slice。Spike 001 已证明旧版 `MMStartTask` 偏移在 4.1.11.55 会落进另一函数。  
**Early signals：** 进程 bundle 路径和预期路径不同；build、完整 SHA-256、arm64 slice SHA-256 任一不符；模块基址/大小异常；关键偏移的指令指纹不符；微信刚更新但 profile 没变。  
**Consequences：** 进程崩溃、错误 native 对象、脏卸载、错发；最坏情况下聊天数据和业务账号状态被破坏。  
**Prevention：** 每次取钥和每次发送前，从目标进程实际加载模块解析 build、架构、完整 dylib 哈希、arm64 slice 哈希和关键指令指纹；只接受已验证的 `4.1.11.55 / 269111 / c2a479… / da5362…` profile。门禁结果绑定到本次任务，进程重启或 PID 改变后重新验证。禁用自动选择“最接近 profile”。  
**Detection：** 在附加前生成不可变 preflight 记录；CI 对任何偏移/profile 修改强制跑静态指令校验和真实机测试。  
**解决阶段：** 阶段 0「商业可交付门禁」完成设计；阶段 5「原生适配器」以真实进程验证；阶段 7「百人验收」持续复验。  
**置信度：** HIGH（Spike 001 实测）。

### 2. 取钥成功但账号、密钥、数据库与 WAL 不属于同一一致快照

**What goes wrong：** 某个库能解密就把整个账号标记为已连接；实际不同数据库使用的密钥或生成期不同，或主库与 `-wal`/`-shm` 在复制期间变化。分析因此漏消息、混入旧消息，甚至把历史账号 A 的客户用于当前账号 B 发信。  
**Why it happens：** 把“拿到一个 key”当作账号级成功；复制活跃 SQLite 文件时未建立一致读视图；增量游标只记时间而未绑定账号、库身份和快照代次；多账号目录名称相似。  
**Early signals：** 逐库解密通过率不是 100%；WAL 帧持续增长但同步水位不变；同一联系人最近消息时间倒退；账号切换后客户数无合理变化；API 读数与微信可见最近消息不一致。  
**Consequences：** 线索证据陈旧、评分错误、跨账号错发；REQ-DATA-005 被旧快照静默违反。  
**Prevention：** 自动发现后先建立稳定账号 ID；密钥按数据库逐一验证，不允许“主库成功即全成功”；解密产物记录源路径、源文件身份、key 指纹、WAL 水位和同步完成时间。分析任务只读取一个冻结的已完成快照；账号切换使旧分析/发送清单立即失效。首次与增量同步均做消息数、最大时间戳、关键表可读性和逐库一致性校验。  
**Detection：** UI 明示每库状态和数据新鲜时间；使用真实账号制造同步中写入、微信重启和账号切换测试；对抽样会话与微信 UI 双向核对。  
**解决阶段：** 阶段 1「账号、取钥与一致同步」，不得推迟到分析阶段。  
**置信度：** HIGH（项目约束明确；一致性边界需实现验证）。

### 3. 把 Chatlog API 的一次返回当成完整、最新、稳定的数据集

**What goes wrong：** `/sessions` 的 `limit=5000` 或 `/history` 的单页返回被当作全集；时间范围边界、offset 分页和同步期间新增消息造成漏读/重复；仅凭 `is_group=false` 仍混入公众号、服务通知和机器人；媒体/撤回/引用消息被错误当作普通文本证据。  
**Why it happens：** 已验证“接口可读”被误解为“业务语义已验证”；API 只是 Chatlog 的通用数据接口，不提供本产品所需的一致快照和真人会话保证。  
**Early signals：** 返回数量恰好等于 limit；分页间首尾消息重复或时间倒序；同一分析重复运行客户数变化；候选用户名具有公众号/系统模式；未知 message type 被拼成空文本。  
**Consequences：** 漏掉高价值客户、系统会话进入 DeepSeek、证据错位、成本估算失真。  
**Prevention：** 将 Chatlog 封装为内部只读适配器，不把 HTTP 响应直接交给 UI/模型。冻结同步快照后遍历全部分页，使用稳定消息主键去重，并保存查询时间边界与完整性计数。真人私聊筛选采用明确 allow/exclude 规则并建立真实账号回归语料；未知类型使该会话分析失败，不转为空文本。对 API schema、排序、分页和日期边界做契约测试。  
**Detection：** 记录每会话页数、原始数、去重数、排除原因和未知类型数；任何 `count == limit` 必须继续分页而不是结束。  
**解决阶段：** 阶段 2「确定性私聊语料与证据索引」。  
**置信度：** HIGH（API 可读已实测；完整性风险是接口契约必然边界）。

### 4. DeepSeek 返回合法 JSON，但任务仍然是失败的

**What goes wrong：** JSON 可解析却缺字段、类型错误、内容截断、证据 ID 虚构、文案违背禁用承诺，或偶发返回空内容。程序若“修 JSON”、补默认字段或换模型重试，会把失败伪装成有效分析。  
**Why it happens：** JSON mode 只保证 JSON 字符串格式，不保证业务 schema 和事实正确；DeepSeek 官方明确提示 JSON Output 偶尔可能返回空内容，`max_tokens` 不合理还会截断 JSON。  
**Early signals：** `content` 为空；finish reason 表明长度限制；schema validation 失败；输出引用了输入中不存在的 evidence ID；模型生成了价格、优惠、库存或承诺字段；同一输入在模型/提示变更后明显漂移。  
**Consequences：** 线索误判、虚假承诺、错配证据进入客户表并被批量发送。  
**Prevention：** 显式锁定 `deepseek-v4-flash` 非思考模式、模型标识和提示版本；设置 `response_format={"type":"json_object"}`，提示中包含 JSON schema 示例并给足输出上限。响应先做严格 JSON Schema，再做 evidence ID、枚举、范围、禁用承诺和必填字段验证；任一失败将该客户标为分析失败，不修补、不补默认值、不切模型或供应商。提示/模型升级必须重跑金标语料。  
**Detection：** 保存原始响应哈希、模型标识、finish reason、usage 和验证错误；空内容率、schema 失败率、证据失败率作为发布门禁。  
**解决阶段：** 阶段 3「结构化分析与金标评测」。  
**置信度：** HIGH（DeepSeek 官方 JSON Output 文档）。

### 5. Token 成本、缓存收益和隐私暴露被静态估算掩盖

**What goes wrong：** UI 用字符数或固定单价显示“预计费用”，实际没有区分 cache hit/miss 与输出 token；价格更新后继续显示旧金额。为了提高缓存命中，把客户聊天放进稳定公共前缀，导致更多个人数据进入服务端磁盘缓存并扩大重复上传。  
**Why it happens：** DeepSeek 缓存默认开启，只有完整匹配已持久化前缀才命中；官方价格区分 hit、miss 和 output，且明确保留调价权。缓存优化与数据最小化目标容易冲突。  
**Early signals：** `prompt_cache_hit_tokens + prompt_cache_miss_tokens` 与输入 usage 不一致；估算和实扣长期偏差；公共前缀出现姓名、微信号、电话或聊天内容；模型价格版本无更新时间。  
**Consequences：** 用户对费用失去信任；不必要的聊天数据外传与缓存；1000 客户任务成本不可控。  
**Prevention：** 稳定前缀只能放无个人信息的系统规则与 schema，客户证据置于其后；本地规则先压缩并只调用最终候选。估算使用当前可配置价格快照并明确“预计”，完成后按响应 `usage` 的 hit/miss/output 计算实际费用；每次模型/价格变化要求显式更新和验收。不要用上传更多聊天换缓存命中。  
**Detection：** 对请求 payload 做 PII 字段审计；同时展示估算、实际 token、cache hit/miss、实际费用和累计费用；建立估算偏差阈值。  
**解决阶段：** 阶段 3「结构化分析」与阶段 4「桌面仪表盘」联合完成。  
**置信度：** HIGH（DeepSeek 官方缓存与价格文档）。

### 6. 证据属于真实聊天，却不支持当前客户的当前结论

**What goes wrong：** 相似文本、分页重排或模型复述使证据与联系人、时间、说话人或字段错配。例如店主说出的价格被当成客户预算，另一个客户的手机号被拼入当前客户，旧需求被当成近期购买意向。  
**Why it happens：** 以文本片段作为证据主键；允许模型直接复制/改写证据；把确定性字段抽取与生成式判断混在一次调用中；未区分 `sender`。  
**Early signals：** 相同 quote 出现在多个客户；证据找不到唯一原消息；手机号来自店主一侧；结论时间晚于证据快照；引用内容与原文不完全相等。  
**Consequences：** 客户表看似“可审计”但实际不可追溯，个性化文案冒犯客户或泄露他人信息。  
**Prevention：** 本地为每条消息生成不可变 evidence ID，绑定账号、快照、chat username、消息 ID、sender、timestamp、type 和原文哈希。联系方式及明确字段只走确定性提取；模型只能返回 evidence ID，不允许返回自由文本作为证据。服务端验证每个结论引用的证据存在、属于当前客户/快照、说话人正确且字段规则成立；任何错配使该客户整个分析失败。  
**Detection：** 详情页从结论直达原消息；自动做唯一性、归属、说话人和哈希校验；发布前人工抽样电话号码、预算、时间和阻碍四类字段。  
**解决阶段：** 阶段 2「证据索引」建立主键；阶段 3「结构化分析」强制引用验证。  
**置信度：** HIGH（产品可审计目标的核心不变量）。

### 7. “成交意向分”制造未经校准的确定感

**What goes wrong：** 0–100 分被用户理解为成交概率；模型表达流畅导致高分客户实际只是礼貌咨询，或低分客户被永久排除。不同课程、价格带、季节和店铺配置下阈值不可迁移。  
**Why it happens：** 没有真实成交标签仍使用精细数字；把 prompt 评分当统计模型；只看整体准确率，不看高分段精确率、漏判和业务分群。  
**Early signals：** UI 或导出出现“80% 成交率”；同一证据在重复分析中跨档；高分段真实成交率不升反降；排除档出现后续成交；业务配置变化但阈值不变。  
**Consequences：** 老板浪费触达额度、错过真实客户、过度信任系统，无法解释 ROI。  
**Prevention：** 首版只称“成交意向分”，用固定可解释 rubric 约束每一档，并同时展示证据、阻碍、最近联系和建议动作。建立带真实成交/未成交/未跟进状态的评测集；校准前不显示概率，不自动删除低分客户。上线前以高意向 precision、待激活 recall、证据有效率及分群稳定性验收。  
**Detection：** 每版保存评分分布和金标混淆矩阵；监控人工改档、排除后成交、高分无回应；界面文案测试禁止“概率/预测成交率”。  
**解决阶段：** 阶段 3「评分 rubric 与金标评测」；真实业务校准延续到阶段 7。  
**置信度：** HIGH（项目已明确不得称统计概率）。

### 8. 原生异步对象提前释放，或错误 Ack 被当作本任务成功

**What goes wrong：** Frida JS 构造的对象在 `MMStartTask` 返回后被 GC/卸载，而微信仍异步持有；也可能捕获到其他微信任务的 `Buf2Resp`，或只看到 `MMStartTask(return=1)` 就宣布成功。超时后热卸载还可能卡住并留下 helper。  
**Why it happens：** Frida 官方说明 `Memory.alloc()` 在 JS 引用消失后释放；微信异步 native 生命周期超出 JS 调用栈。Spike 001 已观察到普通 Frida heap 导致坏 `x1` 和脏卸载，并证明任务进入 `MMStartTask` 但从未进入 `Req2Buf/Buf2Resp`。  
**Early signals：** `MMStartTask` 可见而 `Req2Buf`/serializer/Ack 不出现；任务返回后寄存器/对象内容变化；Ack 的 task ID、recipient 或消息类型无法唯一对应；`script.unload()`/`session.detach()` 超时；Frida helper 残留或微信 CPU 持续升高。  
**Consequences：** 微信崩溃、假成功、重复发送、内存泄漏、后续任务污染。  
**Prevention：** 微信可能异步持有的对象使用 `calloc`/`mmap` 持久 native 内存，并由单一 session owner 保存显式 ownership registry；只有匹配 `generation + command ID + task ID + recipient + message type` 的协议响应才是 Ack。每个对象只在终态 Ack/明确失败且微信不再引用后释放。超时进入阻断清理状态，不继续下一条；执行脚本卸载、session detach、helper 精确清理和微信健康检查，全部完成才关闭任务。  
**Detection：** 记录 Req2Buf、serializer、Buf2Resp 全链路事件和对象分配/释放计数；测试 late Ack、错 task Ack、取消、超时和连续 100 条；任务结束扫描残留 helper 和微信健康状态。  
**解决阶段：** 阶段 5「原生媒体适配器」先建立对象与 Ack 契约；阶段 6「串行发送生命周期」完成压力验证。  
**置信度：** HIGH（Spike 001 + Frida 官方内存生命周期）。

### 9. 把图片链路或已否定的 appmsg 链路包装成视频/文件功能

**What goes wrong：** 修改 message type 复用图片对象，或继续给 `uploadappattach -> sendappmsg` 打补丁。发送端可能显示已调用，但接收端拿不到可播放视频/可下载文件，文件名、大小、封面、时长或 CDN metadata 错误。  
**Why it happens：** 只验证任务创建或本机气泡，不验证接收端内容与 Ack；低估上传回调、CDN metadata、protobuf/task payload 和 serializer 的类型差异。  
**Early signals：** 文件任务不进入 Req2Buf/Buf2Resp；视频只能作为普通文件打开；接收端下载失败；源/接收 SHA-256、大小或文件名不符；超时后必须重启微信才能清理。  
**Consequences：** 产品承诺虚假，批量任务产生不可恢复的坏消息，微信被污染。  
**Prevention：** 文件和视频各自建立独立 adapter、上传入口、回调、payload、metadata、serializer 和 Ack 契约；从 Chatlog 已验证的 `StartC2CUpload`/CDN callback 生命周期研究，不再投入已否定的简单文件路径。类型在完成真实接收端验收前不出现在可发送列表。文件验收必须匹配文件名、字节数、SHA-256 和可下载；视频验收必须匹配可播放性、时长/尺寸及内容。  
**Detection：** 为 0B/小/大文件、中文与特殊字符文件名、常见 MP4 编码、取消与超时建立真实双端矩阵；每次 profile 变化重跑。  
**解决阶段：** 阶段 5「文件与视频独立 Spike/适配器」；未通过不得进入阶段 6 UI。  
**置信度：** HIGH（Spike 001 已否定简单文件路径；视频仍待 Spike 002）。

### 10. 批量发送发生跨账号、跨客户、重复或确认后内容漂移

**What goes wrong：** 用户预览的是 A 文案，实际发送时配置、模型结果、附件或联系人映射已变化；双击开始、崩溃恢复或错误 Ack 导致重复发送；取消与队列并发使下一位客户收到上一位附件。  
**Why it happens：** UI 状态和 native 队列共享可变对象；多个 worker/窗口拥有发送权；用 display name 而非唯一 username 定位；把“超时”自动重排为重试；确认与发送之间没有不可变清单。  
**Early signals：** 同一 command ID 出现两次 running；队列有多个 session/PID；发送时 payload hash 与预览 hash 不同；Ack recipient 与清单不符；应用重启后不确定任务自动回到 queued。  
**Consequences：** 错发私人内容、骚扰客户、商业信誉与隐私事故；这是首版最严重的用户伤害。  
**Prevention：** 只有一个进程内 session owner 可写 native 状态。确认时冻结不可变 manifest：账号、快照、精确 username、显示名、最终文本 bytes、附件绝对身份/大小/SHA-256、adapter/profile、目标顺序及整体 hash；发送前逐项复核。每个 command 有唯一 ID 和单向状态机；任何 unknown/timeout 阻断整个队列且绝不自动重发。崩溃恢复只展示“结果待人工核对”，不能重新入队。下一 command 必须等待上一 command Ack 与 cleanup 均终态。  
**Detection：** 模拟双击、窗口重开、崩溃、取消、late Ack、附件被替换、联系人重命名；100 人真实串行测试要求零错发、零重复、零残留。  
**解决阶段：** 阶段 6「不可变发送清单与单 owner 状态机」；阶段 7「真实百人验收」。  
**置信度：** HIGH（需求明确，且 native 协议天然不提供业务幂等保证）。

### 11. 关闭 SIP、动态注入与签名公证边界到最后才暴露

**What goes wrong：** 开发机可运行，但商业用户不愿或不能关闭 SIP；Developer ID + Hardened Runtime 后 helper/Frida 行为改变；包能构建却无法公证、Gatekeeper 拦截，或安装后无法附加微信。  
**Why it happens：** 当前取钥要求关闭 SIP，而 Apple 将 SIP 定义为默认开启、用于防止进程内存篡改等攻击的重要保护；Apple 的外部分发公证又要求所有可执行文件有效签名并启用 Hardened Runtime。开发环境的 ad-hoc/未签名组合不能代表正式包。  
**Early signals：** 安装说明要求进入恢复模式；企业受管 Mac 禁止修改安全策略；`spctl`/`codesign --verify --deep --strict` 失败；notary log 报 unsigned nested executable、缺 hardened runtime 或 entitlement；正式签名包无法 attach。  
**Consequences：** 产品根本无法交付给目标商家；安全承诺与安装要求矛盾；后期被迫重写取钥和 native 集成。  
**Prevention：** 将“正式签名、公证、staple 后的完整包在目标 Mac 上完成取钥+读取+发送”设为阶段 0 生死门禁，不接受开发裸运行替代。明确记录必须关闭的具体安全项、可恢复步骤和用户可理解的风险；若目标用户无法接受，则在继续完整产品前停止项目并重新决策技术边界，而不是增加另一条隐蔽路径。所有嵌套 helper、Python/Frida 资源和可执行文件纳入签名清单，按最小 Hardened Runtime entitlement 验证。  
**Detection：** 使用未安装开发工具的干净 Apple Silicon Mac 做安装、首启、重启、Gatekeeper、取钥和发送验收；保存 notary log 与签名清单。  
**解决阶段：** 阶段 0「商业可交付门禁」，必须早于 UI 和模型投入；阶段 7 复验安装包。  
**置信度：** HIGH（当前项目实测要求 + Apple 官方安全/公证文档）。

### 12. 本地优先叙事被 API、日志、临时文件和 Excel 导出破坏

**What goes wrong：** 原始聊天、数据库密钥、API Key、手机号或附件路径进入普通日志、崩溃报告、临时目录或导出文件；本地 Chatlog HTTP 端口被其他本机进程访问；候选证据上传范围超过 UI 所示。  
**Why it happens：** “绑定 127.0.0.1”被误当作授权；调试期保留 payload 日志；Excel 是可复制明文；DeepSeek 上下文缓存默认开启但用户不知情；清理只覆盖正常完成路径。  
**Early signals：** 日志可搜索到手机号/聊天原文/API key；临时媒体在任务结束后存在；本地 API 无逐请求认证；导出默认落到公共目录；网络 payload 与 UI 证据预览不一致。  
**Consequences：** 客户隐私泄露、密钥滥用、商家不再信任“本地处理”。  
**Prevention：** 产品进程直接调用内部数据服务，删除通用 Web UI/调试 API；若进程间通信不可避免，使用仅当前用户可访问的 Unix socket 或每次启动的强认证通道。数据库 key 与 DeepSeek key 存 Keychain；日志只记录 ID、计数、哈希和错误码，不记录原文/token/完整路径。发网前生成可见证据清单并对实际 payload 做相同 hash；临时媒体使用受限权限目录并在成功、失败、取消、崩溃恢复时统一清理。Excel 导出必须由用户显式选路径并显示其包含敏感信息；不在 app 内保留隐藏副本。  
**Detection：** 对日志、缓存、临时目录、崩溃报告、网络 payload 和导出残留做隐私扫描；在另一本机用户/进程下尝试访问数据服务；断网验证除 DeepSeek 分析外无外联。  
**解决阶段：** 阶段 1 建立密钥/数据边界；阶段 3 建立出网最小化；阶段 4 处理导出；阶段 7 做安装包隐私审计。  
**置信度：** HIGH（项目隐私要求 + DeepSeek 官方默认磁盘缓存行为）。

## Moderate Pitfalls

### 1. 确定性提取器在中文业务语境中产生“看似正确”的字段

**What goes wrong：** 手机号与订单号混淆，“下周三晚上”没有参考时区/消息时间，“预算不超过 1000”被抽成 1000 元确定预算，否定句中的地址/课程被当需求。  
**Prevention：** 每个字段保存原证据、解析规则、置信状态和标准化值；时间解析绑定 Asia/Shanghai 与消息时间；歧义字段保持未确认，不让模型补齐。使用真实街舞店语料覆盖否定、引用、语音转写缺失和口语表达。  
**早期信号：** 字段值存在但无唯一 evidence ID；人工改错集中在同一正则/规则。  
**解决阶段：** 阶段 2。

### 2. 店铺配置变化后旧分析和旧文案仍被复用

**What goes wrong：** 价格、地址、营业时间、优惠和禁用承诺更新，但旧客户表继续展示或发送过期内容。  
**Prevention：** 业务配置版本及 hash 绑定分析结果和发送 manifest；配置变化使相关文案进入 stale 状态，必须重新分析并重新人工确认，不能静默沿用。  
**早期信号：** 发送 manifest 的 config hash 与当前配置不同。  
**解决阶段：** 阶段 3/4。

### 3. 清理逻辑只在成功路径完整

**What goes wrong：** 取消、API 失败、微信退出、应用崩溃后残留 native 内存、hook、helper、临时文件或 running 状态。  
**Prevention：** 所有资源进入统一 ownership registry 和显式终态状态机；启动时先审计上次未终态 generation，完成可证明的针对性清理后才能新建 session。禁止广泛杀进程。  
**早期信号：** 新任务启动时发现旧 generation、旧 helper 或 running command。  
**解决阶段：** 阶段 6。

### 4. UI 为追求“顺畅”隐藏了失败的具体边界

**What goes wrong：** 把逐库失败、证据失败、Ack unknown 或 cleanup incomplete 合并成“操作失败”，用户无法安全判断能否继续；或者进度条结束但后台仍在清理。  
**Prevention：** 客户可见状态必须映射真实状态机，显示失败数据库/客户/步骤、可操作诊断与是否允许开始下一任务。成功只在业务终态成立时显示。  
**早期信号：** UI completed 数量与状态日志终态数不一致。  
**解决阶段：** 阶段 4/6。

## Minor Pitfalls

### 1. Excel 导出把数字、时间和微信号格式化坏

**What goes wrong：** 长号码科学计数、前导零丢失、日期时区漂移、换行公式注入。  
**Prevention：** 联系方式/微信号按文本写入；日期带明确时区；以 `= + - @` 开头的用户文本做安全文本编码；打开导出文件做格式和筛选验收。  
**解决阶段：** 阶段 4。

### 2. 显示名被当作联系人唯一标识

**What goes wrong：** 同名客户或改备注后证据、表格和发送目标串联错误。  
**Prevention：** 全链路只用账号内稳定 username/contact ID；显示名仅展示。  
**解决阶段：** 阶段 1/2。

## Phase-Specific Warnings

| 建议阶段 | 必须先消除的风险 | 硬性出口标准 |
|---|---|---|
| 阶段 0：商业可交付门禁 | SIP 接受度、正式签名/公证、精确 profile | 干净目标 Mac 上，正式签名并 stapled 的包完成真实取钥、读数据和最小发送；否则停止路线，不建兜底 |
| 阶段 1：账号与一致同步 | 账号/密钥/逐库/WAL 错配、密钥泄露 | 全库验证、冻结快照、增量水位、账号切换失效与 Keychain 存储通过真实机测试 |
| 阶段 2：确定性语料与证据 | Chatlog 分页漏读、系统会话混入、证据错配 | 半年私聊完整遍历；未知类型显式失败；字段与 evidence ID 人工抽样通过 |
| 阶段 3：DeepSeek 分析 | 空 JSON、schema 假成功、证据幻觉、成本/缓存误导、分数伪概率 | 严格 schema + 证据归属 + 禁用承诺验证；金标评测；真实 usage/费用；失败不修补 |
| 阶段 4：桌面 UI 与导出 | UI 隐藏真实状态、旧配置复用、导出泄露 | 每个可见状态对应真实终态；敏感导出显式确认；格式/公式注入验收 |
| 阶段 5：原生类型适配器 | offset 漂移、异步内存、假 Ack、伪视频/文件 | 四种类型分别真实接收端 Ack/内容/metadata/清理验证；未验证类型不展示 |
| 阶段 6：串行批量生命周期 | 并发 native 状态、重复/跨客户发送、取消脏状态 | 单 owner、不可变 manifest、unknown 阻断、崩溃不自动重发、连续压力测试 |
| 阶段 7：业务与发行验收 | 评分误导、隐私残留、安装环境差异 | 真实半年数据闭环、100 目标零错发/零重复/零残留、正式包隐私与健康检查 |

## 需要阶段内继续研究的旗标

- **阶段 0（最高优先级）：** 正式公证包能否在用户可接受的 macOS 安全策略下稳定附加微信。当前“必须关闭 SIP”是商业可交付硬阻塞，不是安装文案问题。
- **阶段 1：** Chatlog 对活跃 SQLite/WAL 的具体快照实现必须通过源码与写入竞态测试确认，不能仅凭 API 结果推断一致性。
- **阶段 5：** Spike 002 视频路径、文件 `StartC2CUpload`/CDN callback 路径和实际尺寸边界尚未验证；不得提前进入产品范围。
- **阶段 6：** `Buf2Resp` 中可稳定关联 recipient/type/generation 的字段需要真实协议观测；缺少唯一关联就不能宣称 Ack。
- **隐私：** DeepSeek 官方缓存文档确认默认磁盘缓存，但本次未从官方 API 文档确认候选证据的保存期限、删除机制和数据处理地域；发布前必须完成供应商条款专项审查并在产品内准确披露。

## Sources

### 项目级一手证据（HIGH）

- `.planning/PROJECT.md` — 产品边界、版本门禁、隐私与并发约束。
- `.planning/REQUIREMENTS.md` — 需求、完成标准与禁止替代路径。
- `.planning/notes/chatlog-infrastructure-decisions.md` — Chatlog 复用/删除范围与 sender 源码边界。
- `Agent.md` — 已验证 Chatlog API、Frida 版本、profile、offset 和发送约束。
- `.planning/spikes/MANIFEST.md` — native 适配器与 Ack 验收定义。
- `.planning/spikes/001-native-file-send/README.md` — 崩溃、持久内存、简单文件路径失效与清理超时的真实观测。

### 官方资料（HIGH）

- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/) — JSON mode 配置、截断风险及偶发空内容。
- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) — 当前模型、token 分类、价格与调价声明。
- [DeepSeek Context Caching](https://api-docs.deepseek.com/guides/kv_cache/) — 默认磁盘缓存、完整前缀命中规则和 usage 字段。
- [DeepSeek Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/) — 格式、鉴权、余额、限流和服务端错误的区分；本产品不得按其建议切换供应商。
- [Frida JavaScript API](https://frida.re/docs/javascript-api/) — `Memory.alloc()` 生命周期、脚本 pin/unpin 与显式 native 资源边界。
- [Apple Platform Security: System Integrity Protection](https://support.apple.com/guide/security/system-integrity-protection-secb7ea06b49/web) — SIP 默认开启及其进程/系统完整性保护角色。
- [Apple: Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) — Developer ID、公证、签名和 Hardened Runtime 要求。
- [Apple: Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime) — 动态代码、进程内存篡改与最小例外 entitlement 边界。

## What Might Be Missing

- 微信 4.1.11.55 私有协议没有官方稳定性承诺；所有 native 结论只对当前精确 profile 成立。
- 尚无真实街舞店成交标签，评分阈值与预期商业价值不能被当成已校准结论。
- 尚未获得文件/视频真实 Ack 与双端内容一致性数据，不能估计量产可靠性或支持的附件上限。
- 尚未用正式发行证书和干净商用 Mac 完成全链路；开发机成功不能降低阶段 0 风险。

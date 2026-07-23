# Spike Manifest

## Idea

为 macOS Apple Silicon 上的微信客户成交 Agent 建立真正的微信原生视频与文件发送能力，并把它们接入单一串行发送会话。所有能力必须在精确微信版本和 dylib 哈希下真实送达、获得可识别响应并完整清理；不提供兼容兜底或降级发送路径。

## Requirements

- 首个验证 profile 锁定 WeChat `4.1.11.55`、build `269111`、arm64。
- profile 必须同时校验完整 `wechat.dylib` SHA-256 和 arm64 slice SHA-256，不得只比较版本号。
- 视频和文件必须作为两种独立原生适配器实现，不能把图片对象改类型复用。
- 文件必须以接收端可下载、文件名/大小/内容一致的文件消息送达。
- 视频必须以接收端可播放的视频消息送达，不能作为普通文件替代。
- 只允许一个串行 native session owner；成功以对应 `Buf2Resp`/协议响应为准，不以“已调用 MMStartTask”为准。
- 不使用 Hermes、系统分享、剪贴板或键鼠模拟作为发送路径。
- profile 不匹配、响应不可识别或清理不完整时必须拒绝发送。

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | native-file-send | standard | Given a validated 4.1.11.55 profile and a local file, when sent to filehelper through native uploadappattach and sendappmsg, then the receiver obtains an identical file and the task reaches a verifiable response and cleanup endpoint | INVALIDATED_FOR_SIMPLE_UPLOADAPPATTACH | wechat, frida, file, appmsg |
| 002 | native-video-send | standard | Given a validated 4.1.11.55 profile and a local MP4, when uploaded and sent through the native video path, then filehelper receives a playable video with matching metadata and the task reaches a verifiable response and cleanup endpoint | PENDING | wechat, frida, video, cdn |
| 003 | serialized-send-lifecycle | standard | Given text, image, video and file commands, when executed sequentially by one native session owner with cancellation, then every command has one terminal result and no Frida helper or native generation remains | PENDING | queue, lifecycle, cleanup |

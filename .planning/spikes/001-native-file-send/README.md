---
spike: 001
name: native-file-send
type: standard
validates: "Given a validated 4.1.11.55 profile and a local file, when sent to filehelper through native uploadappattach and sendappmsg, then the receiver obtains an identical file and the task reaches a verifiable response and cleanup endpoint"
verdict: INVALIDATED_FOR_SIMPLE_UPLOADAPPATTACH
related: [002, 003]
tags: [wechat, frida, file, appmsg]
---

# Spike 001: Native File Send

## What This Validates

Given the exact local WeChat 4.1.11.55 build and a small deterministic test file, when the Spike uses WeChat's native `uploadappattach` followed by `sendappmsg` with appmsg type 6, then `filehelper` receives a downloadable file whose name, byte length and SHA-256 match the source. The task must expose a real protocol response and release every Frida/native resource.

## Research

Upstream sources checked on 2026-07-22:

- `teest114514/chatlog_alpha` commit `0ae63779ed8b50dff04f2483bb8c9d306953fc8a` still accepts only text and image and only declares WeChat 4.1.11.54.
- `yincongcyincong/wechat_chatter` commit `49114827bc83f8381eb638e8a56f3f0305fc1a1c` contains a native file path: 50,000-byte `uploadappattach` chunks, response parsing for `attachId`, then `sendappmsg` with appmsg type 6.
- The local app is WeChat 4.1.11.55, build 269111. Its dylib does not match the 4.1.11.54 profile, so no old sender hook may be loaded before a new profile is discovered and verified.

| Approach | Source | Pros | Cons | Status |
|---|---|---|---|---|
| Port native `uploadappattach` + `sendappmsg` | `wechat_chatter/onebot/upload_app_builder.go`, `worker.go`, `script.js` | Existing native protocol, chunk response and file appmsg implementation | Needs an exact 4.1.11.55 profile and stricter lifecycle | Chosen |
| Re-label Chatlog image objects | Chatlog image sender | Small initial diff | Wrong upload/message objects and unsafe callback assumptions | Rejected |
| Hermes or UI automation | External bridge / macOS UI | Easy demo | Not the native product path | Rejected |

## How to Run

Profile discovery is read-only and does not send a message:

```bash
/usr/bin/python3 profile_probe.py
```

The actual file-send command will be added only after the discovered profile passes instruction and live observation checks.

## What to Expect

- A `profile-4.1.11.55.json` containing one unambiguous offset per required hook.
- A JSONL forensic log with attach, scan match, validation and detach events.
- No outgoing message during profile discovery.

## Observability

`profile_probe.py` writes `.planning/spikes/001-native-file-send/events.jsonl`. Each record has an ISO timestamp, category, event name and structured fields. The final summary includes duration, match counts, exact hashes, errors and cleanup state.

## Investigation Trail

1. Confirmed the running process reports patch version 55 and the installed app reports `WeChatBundleVersion=4.1.11.55`, not the previously tested 4.1.11.54.
2. Confirmed the current Chatlog upstream still has no native video/file adapter.
3. Found the referenced `wechat_chatter` upstream already implements native video and file protocols. This changes the task from protocol invention to version-profile migration plus production hardening.
4. Static disassembly showed the old 4.1.11.54 `Req2Buf` entry remains instruction-compatible at `0x3e5930c`, while the old `MMStartTask` function offset now lands inside another function and must not be reused.

5. Verified a complete 4.1.11.55 profile with exact hash gates:
   - full dylib SHA-256 `c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9`
   - arm64 slice SHA-256 `da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7`
   - `MMStartTask=0x5121478`, default manager wrapper `0x51173d0`, `Req2Buf=0x3e5930c`, `Buf2Resp=0x3e7eaf0`.
6. First live attempt wrote a synthetic object into the wrong lifecycle shape and WeChat crashed in `mars::stn` at `wechat.dylib+0x3e5ac04`. The crash report is `/Users/gongshaoyou/Library/Logs/DiagnosticReports/WeChat-2026-07-23-003122.ips`.
7. Replacing Frida heap allocations with native `calloc`/`mmap` fixed the bad `MMStartTask` argument observation: `starttask_seen` then reported the expected task id and writable payload memory.
8. Even with native persistent allocations and correct default manager dispatch, both `uploadappattach` and direct `sendappmsg` file tasks reached `MMStartTask(return=1)` but never reached `Req2Buf`, serializer hook, or `Buf2Resp`.
9. The simple iPad-style file path from `wechat_chatter` is therefore invalidated for this local WeChat 4.1.11.55 build. The next file/video Spike must reuse Chatlog's validated media-upload task shell (`StartC2CUpload`/CDN callback lifecycle) instead of continuing to patch `uploadappattach`.
10. Text-send lifecycle investigation moved beyond the simple file path: cloning a real 0x1a0 `MMStartTask` payload and rebasing its internal pointers lets a synthetic `newsendmsg` task enter `Req2Buf`; `AutoBufferWrite` must be called at `0x3e7ff0c`, not `0x3e7ff18`.
11. Runtime instruction-window probes verified that 4.1.11.55 creates a valid 0x30 tree node itself when a task id is absent: allocation starts at `0x3e594a8`, and `node+0x28` is read at `0x3e597b0`. Replacing the root slot at `x19/x24+0x60` with a synthetic node is the wrong lifecycle and can crash in `__tree_remove`.
12. The current `file_send_agent.js` therefore patches only the real WeChat node's `node+0x28` message pointer at `0x3e597b0`, keeps WeChat responsible for remove/delete/rebalance, and skips fake-message post-callback cleanup explicitly at `preCallback=0x3e5ac58`.
13. Latest live verification is blocked by login state, not profile discovery: the visible WeChat process is sitting at login/QR/transfer-only UI, so no real `StartTask` manager context is emitted. Re-run `CHATLOG_SPIKE_TEXT=1 python3 file_send_spike.py` only after the business account is inside the normal chat workspace.

## Results

INVALIDATED_FOR_SIMPLE_UPLOADAPPATTACH. The 4.1.11.55 profile is usable, and native persistent allocation is required, but the simple `uploadappattach -> sendappmsg` file implementation does not dispatch into Mars on this build. Next implementation should start from the validated Chatlog text/image sender lifecycle and add a real file/video media-upload adapter.

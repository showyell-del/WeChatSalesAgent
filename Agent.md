# Project Agent Notes

## Chatlog Alpha

- The project contains the macOS Apple Silicon Chatlog Alpha app at `chatlog_2f54920_darwin_arm64/`; it is an application, not a Codex skill.
- Verified commands: `./chatlog_2f54920_darwin_arm64/chatlog-darwin-arm64 --help`, `key --help`, `http --help`, and `action --help` all run successfully.
- Normal local flow: run `start-chatlog.command` (or the binary), use the TUI to select the account, obtain database keys, decrypt data, then start the HTTP service. Browse locally at `http://127.0.0.1:5030/`.
- On macOS its database-key extraction requires `frida-tools` in the current user's Python environment and requires SIP to be disabled; do not run Chatlog, Python/Frida, or WeChat with `sudo`.
- The system `python3` is 3.9.6. The current Frida 17.x package is incompatible because it imports `typing.NotRequired`, which Python 3.9 does not provide. Use `frida==16.7.19` for this interpreter.
- Verified after installation: `python3` imports Frida 16.7.19 and can attach to and detach from the running WeChat main process. The next `chatlog key` run will restart WeChat to capture and validate the database key.
- Verified Chatlog data API: `GET /api/v1/sessions?format=json&limit=5000` returns the full session list; filter `is_group=false` and exclude official/service usernames for human private-chat candidates.
- Verified private history API: `GET /api/v1/history?chat=<username>&time=<date-range>&limit=<n>&offset=<n>&format=json` returns message sender, timestamp, content, type, and media fields. Use this API for batch lead analysis rather than raw database search.
- For sales-lead screening, preserve evidence excerpts for every score, extract contact details deterministically, and output only actionable private-chat leads. Do not treat a score as a statistical purchase probability unless it has been calibrated against real conversion labels.

## Native sender extraction

- The upstream native sender at commit `2f54920d` supports only `text` and `image`; its request normalization rejects other message types.
- Reusable sender components are `internal/wechat/send/model.go`, `runner_darwin.go`, `assets/native_send_once.py`, `assets/native_send_image_once.py`, `assets/native/single_send_agent.js`, and `assets/native/image_send_agent.js`. Reuse the serialized job/command/release semantics from `internal/chatlog/http/send_debug.go`, not its debug HTTP UI.
- Video and arbitrary-file sending do not have a native WeChat implementation. The Hermes bridge methods are an external adapter and are not a replacement. Each new native type requires its own upload entry and callbacks, protobuf/task payload, CDN metadata mapping, serializer compatibility, ack-safe cleanup, and live verification.
- Production sending must fail closed on an exact WeChat version and dylib hash, own one serialized native session, reject unsupported types explicitly, and verify cleanup without retry or compatibility fallbacks.
- Local WeChat 4.1.11.55 verified profile facts: build `269111`; full `wechat.dylib` SHA-256 `c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9`; arm64 slice SHA-256 `da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7`.
- Verified 4.1.11.55 send offsets: `MMStartTask=0x5121478`, default manager wrapper `0x51173d0`, `Req2Buf=0x3e5930c`, serializer hook `0x3e5938c`, post-serializer `0x3e59394`, `AutoBufferWrite=0x3e7ff18`, `Buf2Resp=0x3e7eaf0`.
- Native sender objects that WeChat may hold asynchronously must be allocated from native memory (`calloc`/`mmap`), not ordinary Frida heap. Frida heap objects allowed `MMStartTask` to return but produced bad `x1` state and dirty unload behavior.
- The `wechat_chatter` simple file path (`uploadappattach` chunks then `sendappmsg` appmsg type 6) is not a valid 4.1.11.55 first implementation path in this environment: both `uploadappattach` and direct `sendappmsg` file tasks reached `MMStartTask` with the correct task id but never reached `Req2Buf` or `Buf2Resp`.
- After a native send attempt times out, `script.unload()` and `session.detach()` can also time out; the clean recovery path is controlled WeChat restart plus targeted cleanup of only the current Frida helper. Do not leave a hot-unload-only lifecycle for file/video send experiments.

## Phase 0 local delivery facts

- Verified local toolchain on 2026-07-23: Swift 6.0.3 targets `arm64-apple-macosx15.0`; `python3` is 3.9.6; `python3` imports Frida 16.7.19.
- `codesign`, `notarytool`, and `stapler` are available through Command Line Tools, but `security find-identity -v -p codesigning` reports `0 valid identities found`; Developer ID signing/notarization must fail closed until a valid identity and credentials are installed.
- `go` is not currently available on PATH and was not found at `/opt/homebrew/bin/go` or `/usr/local/go/bin/go`; Phase 0 plans must not require a Go build step.
- Latest process probe did not show a running WeChat main process; Phase 0 profile checks must report `WECHAT_NOT_RUNNING` distinctly from profile mismatch and worker failures.
- Source reference snapshots are still available at `/tmp/chatlog-alpha-spike.WWc9fK/repo` commit `2f54920d4aa78e1812819f77bb59a5e380c6f0ec` and `/tmp/wechat-chatter-spike` commit `49114827bc83f8381eb638e8a56f3f0305fc1a1c`.

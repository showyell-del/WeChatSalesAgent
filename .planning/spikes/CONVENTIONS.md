# Spike Conventions

- Gate every native WeChat spike on exact app version, full `wechat.dylib` SHA-256, and arm64 slice SHA-256 before loading a send hook.
- Treat `MMStartTask` return value as insufficient. A send path is not validated until it reaches the expected `Req2Buf`/serializer/`Buf2Resp` or media upload callback lifecycle.
- Allocate every object that WeChat may retain asynchronously with native memory (`calloc`/`mmap`). Do not use ordinary Frida heap for send objects, message objects, vtables, task payloads, or callback tables.
- After any native send/upload timeout, prefer controlled WeChat restart plus targeted cleanup of the current Frida helper. Do not rely on hot `script.unload()` as the only cleanup path for media send experiments.
- Do not continue the simple `uploadappattach -> sendappmsg` file path for WeChat 4.1.11.55. It reached `MMStartTask` with a correct task id but did not dispatch into Mars.
- Build the next file/video send spikes from Chatlog's validated text/image native sender lifecycle and `StartC2CUpload` media callback model.

#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

"$PROJECT_DIR/scripts/build_phase0_app.sh"

APP_DIR="$PROJECT_DIR/dist/WeChatSalesAgent.app"
DMG_PATH="$PROJECT_DIR/dist/WeChatSalesAgent-MVP-macOS-arm64.dmg"
DMG_CANDIDATE="$PROJECT_DIR/dist/.WeChatSalesAgent-MVP-macOS-arm64.$$.dmg"
STAGE_DIR="$(mktemp -d /tmp/wechat-sales-agent-dmg.XXXXXX)"
MOUNT_DIR="$(mktemp -d /tmp/wechat-sales-agent-mount.XXXXXX)"
MOUNTED=0

cleanup() {
  if [[ "$MOUNTED" -eq 1 ]]; then
    /usr/bin/hdiutil detach "$MOUNT_DIR" -quiet || true
  fi
  rm -rf "$STAGE_DIR" "$MOUNT_DIR"
  rm -f "$DMG_CANDIDATE"
}
trap cleanup EXIT

/usr/bin/ditto --noqtn "$APP_DIR" "$STAGE_DIR/WeChatSalesAgent.app"
ln -s /Applications "$STAGE_DIR/Applications"
/usr/bin/hdiutil create \
  -volname "微信客户分析 Agent" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDZO \
  "$DMG_CANDIDATE"

/usr/bin/hdiutil attach "$DMG_CANDIDATE" -nobrowse -readonly -mountpoint "$MOUNT_DIR" -quiet
MOUNTED=1
test -d "$MOUNT_DIR/WeChatSalesAgent.app"
test -L "$MOUNT_DIR/Applications"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$MOUNT_DIR/WeChatSalesAgent.app"
"$MOUNT_DIR/WeChatSalesAgent.app/Contents/Resources/PythonRuntime/bin/python3" -c 'import frida,pydantic,pydantic_core; assert frida.__version__=="16.7.19"; assert pydantic.VERSION=="2.12.5"; assert pydantic_core.__version__=="2.41.5"'
test -f "$MOUNT_DIR/WeChatSalesAgent.app/Contents/Resources/Chatlog/LICENSE"
cmp config/build_inputs.json "$MOUNT_DIR/WeChatSalesAgent.app/Contents/Resources/build_inputs.json"
"$MOUNT_DIR/WeChatSalesAgent.app/Contents/MacOS/WeChatSalesAgent" --smoke
/usr/bin/hdiutil detach "$MOUNT_DIR" -quiet
MOUNTED=0

mv -f "$DMG_CANDIDATE" "$DMG_PATH"
SHA256="$(/usr/bin/shasum -a 256 "$DMG_PATH" | /usr/bin/awk '{print $1}')"
BYTES="$(/usr/bin/stat -f %z "$DMG_PATH")"
rm -rf "$APP_DIR"
printf '{"step":"dmg","status":"passed","code":"MVP_DMG_LOCAL_VERIFIED","message":"Ad-hoc signed DMG mounted and standalone app verification passed locally.","evidence":{"path":"%s","sha256":"%s","bytes":"%s"}}\n' "$DMG_PATH" "$SHA256" "$BYTES"

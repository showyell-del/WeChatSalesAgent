#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

APP_DIR="$PROJECT_DIR/dist/WeChatSalesAgent.app"
MACOS_DIR="$APP_DIR/Contents/MacOS"
RESOURCES_DIR="$APP_DIR/Contents/Resources"
PYTHON_SOURCE="${WECHAT_AGENT_PYTHON_SOURCE:-/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9}"
PYTHON_PACKAGES="${WECHAT_AGENT_PYTHON_PACKAGES:?WECHAT_AGENT_PYTHON_PACKAGES must point to the locked package directory}"
FRIDA_SOURCE="${WECHAT_AGENT_FRIDA_SOURCE:?WECHAT_AGENT_FRIDA_SOURCE must point to the locked frida package directory}"
NODE_SOURCE="${WECHAT_AGENT_NODE_SOURCE:?WECHAT_AGENT_NODE_SOURCE must point to the locked Node dependency root}"
ARTIFACT_TOOL_SOURCE="$NODE_SOURCE/node_modules/@oai/artifact-tool"
BUILD_INPUT_MANIFEST="$PROJECT_DIR/config/build_inputs.json"
CHATLOG_BINARY="$PROJECT_DIR/chatlog/chatlog-darwin-arm64"
CHATLOG_SHA256="bdafee95f7ceeecbcad2249f724df05865fb6b348ffb99b0694ebe735d4aef06"

for required in \
  "$PYTHON_SOURCE/bin/python3.9" \
  "$PYTHON_SOURCE/Python3" \
  "$PYTHON_SOURCE/Resources/Python.app/Contents/MacOS/Python" \
  "$FRIDA_SOURCE/_frida.abi3.so" \
  "$NODE_SOURCE/bin/node" \
  "$ARTIFACT_TOOL_SOURCE/package.json" \
  "$CHATLOG_BINARY"; do
  if [[ ! -e "$required" ]]; then
    printf 'BUILD_INPUT_MISSING: %s\n' "$required" >&2
    exit 1
  fi
done

/usr/bin/python3 scripts/verify_build_inputs.py --manifest "$BUILD_INPUT_MANIFEST" --node-root "$NODE_SOURCE" --python-packages "$PYTHON_PACKAGES" --frida-source "$FRIDA_SOURCE" --python-source "$PYTHON_SOURCE"

actual_chatlog_sha256="$(/usr/bin/shasum -a 256 "$CHATLOG_BINARY" | /usr/bin/awk '{print $1}')"
if [[ "$actual_chatlog_sha256" != "$CHATLOG_SHA256" ]]; then
  printf 'BUILD_INPUT_HASH_MISMATCH: %s\n' "$CHATLOG_BINARY" >&2
  exit 1
fi
if ! /usr/bin/file "$CHATLOG_BINARY" | /usr/bin/grep -q 'Mach-O 64-bit executable arm64'; then
  printf 'BUILD_INPUT_ARCH_MISMATCH: %s\n' "$CHATLOG_BINARY" >&2
  exit 1
fi

rm -rf "$APP_DIR"
mkdir -p \
  "$MACOS_DIR" \
  "$RESOURCES_DIR/Python" \
  "$RESOURCES_DIR/Chatlog" \
  "$RESOURCES_DIR/PythonRuntime/bin" \
  "$RESOURCES_DIR/PythonRuntime/lib/python3.9/site-packages" \
  "$RESOURCES_DIR/Node" \
  "$RESOURCES_DIR/Export/node_modules/@oai" \
  "$RESOURCES_DIR/Integrations"

cp app/Phase0App/Info.plist "$APP_DIR/Contents/Info.plist"
/usr/bin/ditto --noqtn app/Phase0App/WeChatCustomerAnalysis.icns "$RESOURCES_DIR/WeChatCustomerAnalysis.icns"
/usr/bin/ditto --noqtn agent_core "$RESOURCES_DIR/Python/agent_core"
/usr/bin/ditto --noqtn integrations/workbuddy "$RESOURCES_DIR/Integrations/WorkBuddy"
find "$RESOURCES_DIR/Python" -type d -name __pycache__ -prune -exec rm -rf {} +

cp "$CHATLOG_BINARY" "$RESOURCES_DIR/Chatlog/chatlog-darwin-arm64"
cp chatlog/LICENSE "$RESOURCES_DIR/Chatlog/LICENSE"
cp "$BUILD_INPUT_MANIFEST" "$RESOURCES_DIR/build_inputs.json"
chmod 755 "$RESOURCES_DIR/Chatlog/chatlog-darwin-arm64"

cp "$PYTHON_SOURCE/bin/python3.9" "$RESOURCES_DIR/PythonRuntime/bin/python3.9"
ln -s python3.9 "$RESOURCES_DIR/PythonRuntime/bin/python3"
cp "$PYTHON_SOURCE/Python3" "$RESOURCES_DIR/PythonRuntime/Python3"
/usr/bin/ditto --noqtn "$PYTHON_SOURCE/Resources" "$RESOURCES_DIR/PythonRuntime/Resources"
/usr/bin/rsync -a \
  --exclude site-packages \
  --exclude __pycache__ \
  --exclude test \
  --exclude tests \
  "$PYTHON_SOURCE/lib/python3.9/" "$RESOURCES_DIR/PythonRuntime/lib/python3.9/"

for package in pydantic pydantic_core annotated_types typing_inspection; do
  /usr/bin/ditto --noqtn "$PYTHON_PACKAGES/$package" "$RESOURCES_DIR/PythonRuntime/lib/python3.9/site-packages/$package"
done
cp "$PYTHON_PACKAGES/typing_extensions.py" "$RESOURCES_DIR/PythonRuntime/lib/python3.9/site-packages/typing_extensions.py"
/usr/bin/ditto --noqtn "$FRIDA_SOURCE" "$RESOURCES_DIR/PythonRuntime/lib/python3.9/site-packages/frida"
find "$RESOURCES_DIR/PythonRuntime" -type d -name __pycache__ -prune -exec rm -rf {} +

cp "$NODE_SOURCE/bin/node" "$RESOURCES_DIR/Node/node"
chmod 755 "$RESOURCES_DIR/Node/node"
cp scripts/build_lead_workbook.mjs "$RESOURCES_DIR/Export/build_lead_workbook.mjs"
/usr/bin/ditto --noqtn "$ARTIFACT_TOOL_SOURCE" "$RESOURCES_DIR/Export/node_modules/@oai/artifact-tool"

/usr/bin/clang -fobjc-arc -framework Cocoa -framework Foundation -framework CoreText app/Phase0App/main.m -o "$MACOS_DIR/WeChatSalesAgent"

"$RESOURCES_DIR/PythonRuntime/bin/python3" - <<'PY'
import frida
import pydantic
import pydantic_core
assert frida.__version__ == "16.7.19"
assert pydantic.VERSION == "2.12.5"
assert pydantic_core.__version__ == "2.41.5"
PY
PATH="$RESOURCES_DIR/PythonRuntime/bin:/usr/bin:/bin" \
PYTHONHOME="$RESOURCES_DIR/PythonRuntime" \
PYTHONPATH="$RESOURCES_DIR/Python" \
/usr/bin/env python3 - <<'PY'
import frida
assert frida.__version__ == "16.7.19"
PY
(
  cd "$RESOURCES_DIR/Export"
  "$RESOURCES_DIR/Node/node" --input-type=module --preserve-symlinks-main \
    -e "import('@oai/artifact-tool').then(() => process.stdout.write('artifact-tool-ok\\n'))"
)

/usr/bin/find "$APP_DIR" -name .DS_Store -delete
/usr/bin/codesign --force --sign - --deep "$APP_DIR"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP_DIR"

printf '{"step":"package","status":"passed","code":"MVP_APP_BUILT","message":"Standalone AppKit MVP app built and verified.","evidence":{"app":"%s"}}\n' "$APP_DIR"

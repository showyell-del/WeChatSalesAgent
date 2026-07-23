#!/usr/bin/env bash
set -euo pipefail

json_event() {
  local step="$1"
  local status="$2"
  local code="$3"
  local message="$4"
  printf '{"step":"%s","status":"%s","code":"%s","message":"%s","evidence":{}}\n' "$step" "$status" "$code" "$message"
}

APP_DIR="dist/phase0/WeChatSalesAgent.app"
MACOS_DIR="$APP_DIR/Contents/MacOS"
mkdir -p "$MACOS_DIR"
cp app/Phase0App/Info.plist "$APP_DIR/Contents/Info.plist"
/usr/bin/clang -fobjc-arc -framework Cocoa -framework Foundation app/Phase0App/main.m -o "$MACOS_DIR/WeChatSalesAgent"
/usr/bin/codesign -s - --force --deep "$APP_DIR"
json_event "package" "passed" "AD_HOC_SIGNED_LOCAL_ONLY" "Local ad-hoc signed artifact was produced for development verification only."

IDENTITIES="$(/usr/bin/security find-identity -v -p codesigning 2>&1 || true)"
if [[ "$IDENTITIES" != *"Developer ID Application"* ]]; then
  json_event "package_identity" "blocked" "DEVELOPER_ID_IDENTITY_MISSING" "Developer ID Application identity is required for notarization."
  exit 0
fi

if [[ -n "${PHASE0_NOTARY_PROFILE:-}" ]]; then
  xcrun notarytool submit "$APP_DIR" --keychain-profile "$PHASE0_NOTARY_PROFILE" --wait
elif [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" ]]; then
  xcrun notarytool submit "$APP_DIR" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_APP_SPECIFIC_PASSWORD" --wait
else
  json_event "notarization" "blocked" "NOTARY_CREDENTIALS_MISSING" "Notary credentials are required after Developer ID identity is available."
fi

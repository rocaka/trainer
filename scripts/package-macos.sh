#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/Trainer"
APP_DIR="$ROOT_DIR/dist/Trainer.app"
BUILD_VERSION="$(date +%s)"
RELEASE_VERSION="${TRAINER_VERSION:-0.1.1}"
GITHUB_CLIENT_ID="${TRAINER_GITHUB_CLIENT_ID:-}"
if [[ -n "$GITHUB_CLIENT_ID" && ! "$GITHUB_CLIENT_ID" =~ '^[A-Za-z0-9_-]{8,128}$' ]]; then
  echo "TRAINER_GITHUB_CLIENT_ID 格式无效" >&2
  exit 2
fi

cd "$PACKAGE_DIR"
swift build -c release

mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$PACKAGE_DIR/.build/release/Trainer" "$APP_DIR/Contents/MacOS/Trainer"
# Prefer the frozen, self-contained Gateway in release builds. The source
# bundle remains as a development fallback and for transparent inspection.
FROZEN_GATEWAY="$ROOT_DIR/dist/mac-gateway/trainer-gateway"
if [[ -x "$FROZEN_GATEWAY/trainer-gateway" ]]; then
  rm -rf "$APP_DIR/Contents/Resources/gateway-runtime"
  cp -R "$FROZEN_GATEWAY" "$APP_DIR/Contents/Resources/gateway-runtime"
fi
# Preserve runtime SQLite data while replacing code.
mkdir -p "$APP_DIR/Contents/Resources/gateway"
cp "$ROOT_DIR/gateway/server.py" "$ROOT_DIR/gateway/validator.py" "$ROOT_DIR/gateway/repository.py" "$ROOT_DIR/gateway/learning_store.py" "$ROOT_DIR/gateway/jobs.py" "$ROOT_DIR/gateway/lab_runner.py" "$ROOT_DIR/gateway/project_context.py" "$ROOT_DIR/gateway/project_import.py" "$ROOT_DIR/gateway/pending_store.py" "$ROOT_DIR/gateway/optimization_authorization.py" "$ROOT_DIR/gateway/version_store.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/teaching_plan.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/course_task_lookup.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/submission_provider.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/course_submission_http.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/course_submission.py" "$ROOT_DIR/gateway/submission_runtime.py" "$ROOT_DIR/gateway/submission_binding.py" "$ROOT_DIR/gateway/submission_plan.py" "$ROOT_DIR/gateway/submission_materials.py" "$ROOT_DIR/gateway/submission_storage.py" "$ROOT_DIR/gateway/submission_queue.py" "$ROOT_DIR/gateway/submission_consent.py" "$ROOT_DIR/gateway/submission_dispatcher.py" "$ROOT_DIR/gateway/submission_worker.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/plan_library.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/model_transport.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/rule_provenance.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/source_grants.py" "$ROOT_DIR/gateway/submission_snapshot.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/learning_loop.py" "$ROOT_DIR/gateway/learning_loop_service.py" "$ROOT_DIR/gateway/loop_http.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/extension_pairing.py" "$ROOT_DIR/gateway/pairing_service.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/workspace_grants.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/teaching_review.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/course_quality.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/integrations.py" "$ROOT_DIR/gateway/sync_contract.py" "$ROOT_DIR/gateway/github_insights.py" "$ROOT_DIR/gateway/account_store.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/assessments.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/storage.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/backup.py" "$APP_DIR/Contents/Resources/gateway/"
cp "$ROOT_DIR/gateway/cloud_client.py" "$ROOT_DIR/gateway/cloud_schema.py" "$APP_DIR/Contents/Resources/gateway/"
rm -rf "$APP_DIR/Contents/Resources/gateway/__pycache__"
mkdir -p "$APP_DIR/Contents/Resources/skills"
# Seed missing assets only; approved/generated assets belong to the user.
rsync -a --ignore-existing "$ROOT_DIR/skills/" "$APP_DIR/Contents/Resources/skills/"
rm -rf "$APP_DIR/Contents/Resources/docs"
cp -R "$ROOT_DIR/docs" "$APP_DIR/Contents/Resources/docs"

ICON_SOURCE="$ROOT_DIR/assets/TrainerAppIcon.png"
if [[ -f "$ICON_SOURCE" ]]; then
  ICONSET="$ROOT_DIR/dist/Trainer.iconset"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  for spec in "16 icon_16x16.png" "32 icon_16x16@2x.png" "32 icon_32x32.png" "64 icon_32x32@2x.png" "128 icon_128x128.png" "256 icon_128x128@2x.png" "256 icon_256x256.png" "512 icon_256x256@2x.png" "512 icon_512x512.png" "1024 icon_512x512@2x.png"; do
    size="${spec%% *}"
    name="${spec#* }"
    sips -z "$size" "$size" "$ICON_SOURCE" --out "$ICONSET/$name" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/Trainer.icns"
fi

cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>Trainer</string>
  <key>CFBundleIdentifier</key><string>com.trainer.learning</string>
  <key>CFBundleName</key><string>Trainer</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$RELEASE_VERSION</string>
  <key>CFBundleVersion</key><string>$BUILD_VERSION</string>
  <key>CFBundleIconFile</key><string>Trainer</string>
  <key>TrainerGitHubClientID</key><string>$GITHUB_CLIENT_ID</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

codesign --force --deep --sign - "$APP_DIR"
echo "Created ad-hoc signed development app: $APP_DIR"

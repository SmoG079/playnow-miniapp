#!/bin/bash
# 微信小程序自动上传脚本
# 用法: ./scripts/upload-miniprogram.sh [版本号] [描述]

set -e

# Node 18 路径（避免 nvm 在 bash 中不生效的问题）
NODE18="/Users/zhli22/.nvm/versions/node/v18.20.8/bin/node"

# 项目配置
PROJECT_PATH="/Users/zhli22/project/playnow-miniapp/miniprogram"
PRIVATE_KEY_PATH="/Users/zhli22/project/playnow-miniapp/private.wx5eccb727f753a62e.key"
APPID="wx5eccb727f753a62e"
VERSION=${1:-"1.0.0"}
DESC=${2:-"自动上传版本"}

echo "🚀 开始上传微信小程序..."
echo "版本: $VERSION"
echo "描述: $DESC"

# 使用 Node 18 运行项目本地安装的 miniprogram-ci
MINIPROGRAM_CI="/Users/zhli22/project/playnow-miniapp/node_modules/miniprogram-ci/bin/miniprogram-ci.js"

"$NODE18" "$MINIPROGRAM_CI" upload \
  --pp "$PROJECT_PATH" \
  --private-key-path "$PRIVATE_KEY_PATH" \
  --appid "$APPID" \
  --uv "$VERSION" \
  -r 1 \
  --enable-es6 true \
  --desc "$DESC"

echo "✅ 上传完成！"

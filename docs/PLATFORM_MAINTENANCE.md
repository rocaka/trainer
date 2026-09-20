# Mac 与 Windows 维护方式

使用同一个仓库，不拆分两套业务逻辑。

| 目录 | 职责 |
| --- | --- |
| `Trainer/` | macOS SwiftUI 界面和系统适配 |
| `desktop/` | Windows Tauri + Svelte 界面和系统适配 |
| `gateway/` | 两端共享的课程、评判、账户与同步业务 |
| `vscode-trainer-extension/` | 两端共用 VS Code 插件 |
| `scripts/` | 各平台构建和验证脚本 |

稳定功能合并到 `main`；跨平台初版在 `codex/windows-preview` 验证。
后续按功能开短期分支，不长期维持 `mac-main` / `windows-main` 两套主线。
修改共享 Gateway 时必须验证两个平台；平台权限适配放独立模块，不复制业务规则。
Mac 和 Windows 分别打包、分别签名，版本与同一次源码提交对应。
学习数据通过账户同步，不把数据库、工作区路径、API 密钥或本机配对令牌提交到 Git。

Windows 测试包未签名，代码提交和配对在安全文件访问完成前禁用；课程生成、账户同步界面尚未齐全。
测试安装包仅用于验证已有界面、独立启动、课程读取和 AI 配置，不属于与 Mac 功能对等的正式版本。

# Trainer Learning Bridge for VS Code

Version 0.2.0 provides local pairing. The old unauthenticated selection sender is disabled until workspace authorization is implemented.

It never reads a workspace in the background, applies edits, runs terminals, or transmits API keys. Install it locally with VS Code's “Install from VSIX” workflow after packaging the extension.
# 配对入口（0.2.0，待 Extension Host 实机验收）

1. 在可信本地工作区执行 `Trainer: 连接本地教学应用`。
2. 在新版 Trainer 的学习档案中打开 `VS Code 连接`，刷新并输入 VS Code 显示的六位码。
3. 返回 VS Code 点击“已在 Trainer 确认”，领取独立令牌。
4. 执行 `Trainer: 撤销连接` 可撤销服务端令牌并清除本地安全存储。

令牌使用 `context.secrets`，不写 settings.json 或工作区。配对不授予源码读取、AI 请求或评分写入权限；多文件绑定尚未实现。仅支持本地可信工作区，SSH、WSL、容器暂不支持。

旧“解释选区”命令现在只显示停用说明，不再发送代码或触发生成；Gateway 对旧写入接口要求原生会话。新多文件通道仍待实现。

测试：`node --test tests/pairing.test.js`。当前只有单元测试和 Gateway 回环测试，不能替代 VS Code Extension Host 验收。

官方参考：[SecretStorage 与扩展 API](https://code.visualstudio.com/api/references/vscode-api#SecretStorage)。

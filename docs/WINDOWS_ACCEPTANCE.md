# Windows 预览验收

本清单用于验证 Windows 原生行为，不代表已经验收通过。Mac 上的构建、模拟平台测试和浏览器预览，均不能代替 Windows 实机结果。

当前 Windows 代码提交保持禁用。系统凭据读写适配不等于源码读取安全适配：提交快照仍需要 Windows ACL、reparse point/目录句柄、文件替换竞争和私有存储验证。不得修改能力开关或跳过校验来获得“通过”。

## 自动检查与产物边界

仓库包含 `.github/workflows/windows-preview.yml`，仅支持手动 `workflow_dispatch`，不会因 push 或 PR 自动运行。配置文件已经准备好不等于工作流已经执行；执行记录、Windows 日志及产物必须另行验收。

手动运行前，把待验证代码作为明确的提交纳入仓库，再由有权限的维护者在 Actions 选择 **Windows preview checks → Run workflow**。本说明不自动上传代码或触发远程工作流。

工作流在干净的 `windows-latest` x64 环境执行：

1. 使用前端锁文件安装依赖，运行 Svelte/TypeScript 检查及前端构建。
2. 使用基础 Tauri 配置运行 `cargo check --locked`，不是安装包构建。
3. 安装 `scripts/requirements-build.txt` 中固定版本的构建工具。
4. 运行平台路径、安全能力及凭据分派测试；不运行尚依赖 POSIX 的全部测试集。
5. 运行 `scripts/test-windows-credentials.py`，仅创建随机名称的假凭据，覆盖缺失、保存、读取、更新、删除并清理。
6. 运行 `scripts/test-gateway-preview.py`，验证隔离后端的空档案、会话检查、Windows 禁用提交以及关闭父管道后的回收。
7. 验证教学资源清单，执行 `scripts/package-gateway.ps1`，上传完整后端目录，保留 7 天。

产物 `trainer-windows-x64-backend-preview-<run_id>` **仅是后端预览，不是可安装的 Trainer 桌面版**，不包含签名、更新或回滚验收。必须保留整个目录，不能只复制 exe。CI 不提供或使用真实 AI Key、GitHub Token、学习数据库和项目源码；凭据测试使用的假数据也不进入上传目录。上传范围仅为编译后的后端及仓库跟踪的教学资源，不上传 AppData、测试日志或整个工作目录。

Actions 固定为官方发布提交，来源分别为 [checkout](https://github.com/actions/checkout/releases/tag/v7.0.1)、[setup-node](https://github.com/actions/setup-node/releases/tag/v7.0.0)、[setup-python](https://github.com/actions/setup-python/releases/tag/v7.0.0) 和 [upload-artifact](https://github.com/actions/upload-artifact/releases/tag/v7.0.1)。更新时应重新审核完整提交标识及官方说明。

## 干净用户的手工烟雾测试

使用 Windows 10/11 x64 的独立普通测试用户或可恢复虚拟机，不以管理员启动 Trainer。不导入真实用户数据，不复制 Mac 数据库，不登录真实账户，不配置真实服务密钥。

记录：Windows 版本与架构、WebView2 版本、代码提交、构建运行编号、测试模式、结果、失败截图。日志和截图不得包含密钥、会话令牌或私人文件内容。

### 1. 环境与隔离模式

- 开发机准备 Tauri 对应的 Windows 构建依赖；运行前检查 18787 端口没有其他服务。
- 在 `desktop` 执行 `npm ci`，设置当前 PowerShell 会话 `$env:TRAINER_DESKTOP_ISOLATED = '1'`，然后执行 `npm run tauri dev`。
- 确认桌面显示隔离后端状态，档案没有真实学习记录，设置页不允许保存真实密钥；预览数据只存在于本次临时目录。
- 课程和档案为空时应显示真实空状态，不伪造课程、分数或同步成功。
- 连续切换页面、刷新和调整窗口宽度；检查加载、失败、重试以及“减少动态效果”状态，没有无限转圈、遮挡或重复后端。

### 2. 能力与会话

必须先通过桌面的受控启动入口启动后端，再检查健康状态。独立后端 `trainer-gateway.exe` 需要父进程通过标准输入交付 `{"session":"64 位小写十六进制随机值"}` 并保持管道；双击 exe 或直接发起健康请求不会代替启动握手。不要把真实会话令牌写进命令参数、日志或截图。

Windows `/health` 的预期关键值：

| 字段 | 预期 | 含义 |
| --- | --- | --- |
| `ok` | `true` | 后端已启动，不表示所有功能都可用 |
| `configured` | 隔离模式为 `false` | 不继承宿主服务密钥 |
| `secureSubmissionSupported` | `false` | 原生安全快照适配未完成 |
| `submissionReady` | `false` | 不启动不安全的提交链路 |

`capabilities` 中的通用功能名称不是 Windows 提交就绪证明。受保护的 `/v1/desktop/runtime` 无会话或错误会话应拒绝；来自网页 `Origin` 的请求也应拒绝。隔离会话中 `owned=true`、`isolated=true`、`settingsWritable=false`。所有接口仅绑定本机，不因测试开放防火墙或局域网访问。

### 3. 原生凭据与退出

- 在该测试用户下执行 `python scripts/test-windows-credentials.py`，应打印假凭据生命周期通过、测试条目已删除。它不需要真实密钥，不会读取或改动真实 Trainer 服务凭据。
- 正常关闭桌面后，确认其自有后端退出、临时预览目录删除；其他应用或其他端口的服务不被结束。
- 重新启动后是新的隔离档案。占用 18787 后再启动，应用应明确报错，不连接或终止占用者。
- 后续独立桌面预览打包完成后，另行验证其启动、持久化、父进程异常退出和卸载行为；隔离模式通过不代表持久化模式通过。

### 4. 后端构建产物

- 解压到包含空格及中文的路径，检查整个后端目录齐全，不存在课程数据库、生成内容、项目源码或密钥文件。
- 在不安装 Python 的干净用户环境，通过受控桌面启动入口运行冻结后端；确认没有依赖开发者机器的绝对路径。
- 构建产物必须与对应提交和运行编号匹配。后端构建成功但尚未完成桌面资源捆绑时，此项标记“待验证”，不能把后端目录当作安装包分发给普通用户。

## 发布前仍需通过的门槛

- Windows 原生安全提交存储、ACL、链接/重解析点和文件竞争防护；使用专门的测试工作区验证，不扫描真实项目。
- 课程任务与提交来源一致、保存检查、去重、AI 评判失败重试及结果回流。
- 同一测试账户的 Mac/Windows 课程和进度同步、离线恢复、冲突处理；本机路径、授权和密钥不跟随同步。
- Windows 持久化模式凭据设置、启动失败恢复、重复启动与退出回收。
- 桌面安装、卸载不误删数据、签名、更新、回滚和无 Python 环境验收。

所有项目都需记录真实 Windows 测试结果。现阶段应标记为“开发预览”，不得标记为“Windows 版已完成”。

# 跨平台客户端进度

架构：Tauri 2 + Svelte 5 + TypeScript，复用 Python Gateway 与 SQLite。
保留 SwiftUI Mac 客户端；不自动迁移或覆盖现有数据。

## Mac 界面同构重构（2026-09-20）

- Windows 主窗口改为与 Mac 一致的三栏工作台：左侧项目教学与学习路线、中栏课程讲解/代码/观察练习、右栏课程代码任务与 AI 教练。
- 个人档案恢复为独立同层页面，包含全屏封面、指标、活动热力图、语言雷达、GitHub 信号、语言档案和最近凭据；设置恢复为分栏弹窗。
- 内置 JavaScript 基础六课与 Mac 基础路线一致；本机已保存课程复用同一课程文件与 Gateway 数据。
- AI 教练、文字评判、学习凭据、课程代码任务、候选课程生成、人工审批、任务中心、账户同步状态均通过固定动作桥接访问同一 Gateway；WebView 不能指定任意 URL。
- 项目导入通过原生目录选择器建立授权边界，再由 Gateway 执行安全摘要；网页层不能直接传入任意目录。
- Windows 安全代码快照仍保持禁用，直至 ACL、reparse point 和文件竞争测试完成；界面显示真实不可用原因，不把文字回答或教练题冒充课程代码提交。

## 里程碑（不是工时百分比）

- [x] 新建独立 desktop 客户端、响应式布局、加载/失败状态、减少动态效果。
- [x] 本地档案只读桥接，限制固定本机端点、超时、禁止重定向。
- [ ] Windows Gateway 独立打包、生命周期、会话认证、系统凭据适配。
  - [x] 平台数据目录统一：Windows LOCALAPPDATA、macOS 保持原路径；云课程恢复复用同一目录。
  - [x] 隔离开发启动器：独立端口、临时数据、独立配对目录、随机会话令牌、退出回收进程。
  - [x] 隔离开发模式桌面自动启动、进程状态、重试入口；关闭父进程管道触发后端退出与临时目录清理。
  - [ ] Windows ACL、安全提交与正式签名发布仍待完成；原生系统密钥及预览后端已实现。
  - [x] Windows Credential Manager 读写删除适配；AI / GitHub 读取路径已接入，Mac 保留钥匙串。7 项平台分派与输入校验测试通过。
  - [x] 凭据设置 UI 与原生会话接口已集成：显式授权、域名隔离、只回传有无密钥、不自动调用模型；隔离/只读模式隐藏密钥输入。
  - [x] Windows CI 已通过原生假凭据读写、更新和删除；设置界面手工验收仍待完成。
  - [x] PyInstaller 后台、NSIS 安装包构建通过，资源清单和冻结后台启动/退出测试通过。
  - [x] 不支持安全目录句柄的平台明确禁用提交，健康接口报告平台支持和运行就绪状态；不降级为不安全读取。
- [ ] 课程阅读与生成任务、工作区关联、提交评判端到端接入。
  - [x] 只读课程库、课时导航、三种讲解、代码、观察练习与课程代码任务分区；不执行 HTML、不修改课程文件。
  - [ ] 课程生成/进度写回、工作区关联和提交界面仍未接入。
- [ ] 账户登录与跨设备同步、冲突和离线处理。
- [ ] Windows 实机验收、签名安装包、更新与回滚。

当前为开发预览，不是 Windows 可发布版本。浏览器只展示界面并明确提示未连接，不伪造数据；桌面设置写入仅允许自有 Windows 后端，Mac 旁路连接保持只读。开发进度可从客户端导航查看。

## 本轮验证

- Svelte / TypeScript 检查：0 errors、0 warnings；生产前端构建通过。
- 浏览器预览：确认未连接状态和开发进度导航正常，已检查进度页视觉布局。
- macOS `cargo check`：通过。仅为原生编译检查，尚未完成桌面桥接运行验收。
- Windows CI 已验证独立 Gateway 运行；实体电脑体验和跨设备同步尚未验收。
- 独立 Windows 冻结后端、stdin 会话握手、父进程退出监听、NSIS 资源捆绑已通过构建。脚本入口为 `scripts/package-desktop.ps1`。
- 已按用户授权推送 `codex/windows-preview`；工作流在此分支推送或手动触发，上传测试安装包。首次成功构建：[35495290296](https://github.com/rocaka/trainer/actions/runs/35495290296)。安装后窗口和生命周期另有自动检查，不能以构建通过替代。
- 执行权限恢复后已重新运行最新 macOS 原生编译，检查通过；Windows 原生编译也已通过。
- 最终测试包提交 `a408da77e87fec8e75fdda84b4d130b9afdebddd`，Windows 构建 [35495536630](https://github.com/rocaka/trainer/actions/runs/35495536630) 全部通过：包含 NSIS 实际安装、桌面窗口创建、捆绑后台健康和正常关闭后后台回收。仍未完成真实用户课程、AI 请求、跨设备同步或完整视觉验收。
- 2026-09-20 最新定向回归：desktop 24、平台 7、凭据 8、云同步 5、模型传输 14、课程库 7、提交 provider 2、队列 9、存储 6、快照 7，共 89 项通过；不是完整测试集。模型传输测试有 2 条 HTTPError 清理 ResourceWarning，不影响测试结果但仍待清理。
- 新课程/设置/进度页面在浏览器预览中检查通过；浏览器状态明确标为未连接，未使用伪造数据。含真实课程的原生阅读、Windows 设置写入和最新后端端到端测试仍待运行。
- 第二阶段：平台路径单测 5/5、原生编译检查通过；隔离 Gateway 启动及 `/v1/me` 读取通过，确认零学习凭据，退出回收完成。
- 已定位并修复隔离存储失败：macOS 临时目录含系统符号链接，启动器规范化新建临时目录后通过原有安全检查，不改变项目文件的防链接策略。
- `python3 scripts/test-gateway-preview.py` 通过：真实后端启动、零凭据档案、私有提交数据库初始化、父管道关闭后退出及临时目录删除。
- 提交存储仍依赖 POSIX 权限、用户归属和目录描述符操作，Windows 必须补平台适配和安全测试，不能通过关闭校验解决。尚未完成 Windows 提交验收。

## 开发

在 desktop 下执行 `npm ci`、`npm run build`、`npm run tauri dev`。
桌面开发需要 Rust 和对应平台的 Tauri 构建工具链。
Mac 开发客户端默认只读连接原版 Gateway；设置隔离模式后由桌面自动启动临时后端。Windows 独立预览尝试启动安装资源内的后端。
不得要求用户复制 Mac 数据库到 Windows；后续通过账户服务同步逻辑记录。

独立测试启动器可在仓库根目录执行 `python3 scripts/gateway-preview.py`，仅用于手工后端测试。
桌面开发时设置 `TRAINER_DESKTOP_ISOLATED=1` 后执行 `npm run tauri dev`，会自行启动并拥有 18787 临时后端，不要同时手工启动。会话通过 stdin 交付，不进入网页、参数或日志。
Mac 不设置时只读连接现有 8787 后端。浏览器预览不直接读取本机后端。隔离模式清除环境 API key 且禁止系统凭据读取。

## Windows 后端构建

1. 在独立 Python 构建环境安装 `scripts/requirements-build.txt`。
2. 在 PowerShell 执行 `./scripts/package-gateway.ps1`。
3. 输出为 `dist/windows-gateway/trainer-gateway`，必须分发整个目录，不能只复制 exe。
4. 这个目录只是后端；完整安装包使用下面的桌面构建入口。当前不能开放 Windows 代码提交，原生 ACL、reparse point/目录句柄保护仍待完成。

完整桌面预览构建入口：`./scripts/package-desktop.ps1`。使用 NSIS 覆盖配置捆绑整个后端目录，输出为未签名预览安装包；Windows CI 构建已通过。不得对外称正式 Windows 版完成。

打包仅包含 Git 跟踪的 core/verified 教学资源和文档，不包含 generated、学习记录、课程缓存及凭据。
PyInstaller 产物与构建系统相关，必须在 Windows 上构建 Windows 产物，不能用 Mac 构建通过替代 Windows 验收。

Windows 凭据验收：执行 `python scripts/test-windows-credentials.py`，只创建随机名称的假密钥，测试后删除；不读取或修改真实配置。
凭据命名固定为 `Trainer/<service>/<account>`，通用凭据 UTF-8 内容、本机当前用户持久化；不进入数据库、日志、命令参数或云同步。

凭据适配回归：云课程恢复改为使用统一的平台目录解析器。Windows 原生系统 API 假凭据自测已通过；真实设置界面和跨设备业务仍需独立验收。

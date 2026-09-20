# 跨平台客户端进度

架构：Tauri 2 + Svelte 5 + TypeScript，复用 Python Gateway 与 SQLite。
保留 SwiftUI Mac 客户端；不自动迁移或覆盖现有数据。

## 里程碑（不是工时百分比）

- [x] 新建独立 desktop 客户端、响应式布局、加载/失败状态、减少动态效果。
- [x] 本地档案只读桥接，限制固定本机端点、超时、禁止重定向。
- [ ] Windows Gateway 独立打包、生命周期、会话认证、系统凭据适配。
  - [x] 平台数据目录统一：Windows LOCALAPPDATA、macOS 保持原路径；云课程恢复复用同一目录。
  - [x] 隔离开发启动器：独立端口、临时数据、独立配对目录、随机会话令牌、退出回收进程。
  - [x] 隔离开发模式桌面自动启动、进程状态、重试入口；关闭父进程管道触发后端退出与临时目录清理。
  - [ ] Windows ACL/系统密钥、正式版后端打包与生命周期仍待完成。
  - [x] Windows Credential Manager 读写删除适配；AI / GitHub 读取路径已接入，Mac 保留钥匙串。7 项平台分派与输入校验测试通过。
  - [x] 凭据设置 UI 与原生会话接口已集成：显式授权、域名隔离、只回传有无密钥、不自动调用模型；隔离/只读模式隐藏密钥输入。
  - [ ] Windows 原生凭据读写和设置保存实机验收未完成。
  - [x] 添加 PyInstaller 目录式打包配置及 Windows PowerShell 构建入口；资源清单测试通过。尚未产出 Windows 安装包。
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
- Windows 实机、独立 Gateway 运行和跨设备同步尚未验证。
- 已新增独立 Windows 冻结后端入口、原生 stdin 会话握手、父进程退出监听、NSIS 资源捆绑覆盖配置与 `scripts/package-desktop.ps1`。这些是实现，尚未产出/运行 Windows 安装包。
- `.github/workflows/windows-preview.yml` 仅手动触发：Windows 前端/原生检查、凭据假数据自测、后端打包；未推送、未触发、未上传产物。验收清单见 `docs/WINDOWS_ACCEPTANCE.md`。
- 最新原生集成版本的编译被执行审批服务额度限制阻止，不能沿用较早 `cargo check` 结果当作本版验证。Rust 格式/语法检查及前端构建通过；原生编译需审批恢复后重跑。
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

## Windows 后端构建（待 Windows 实机执行）

1. 在独立 Python 构建环境安装 `scripts/requirements-build.txt`。
2. 在 PowerShell 执行 `./scripts/package-gateway.ps1`。
3. 输出为 `dist/windows-gateway/trainer-gateway`，必须分发整个目录，不能只复制 exe。
4. 这只是后端预览产物，不是 Trainer 安装包；当前不能开放 Windows 代码提交。原生 ACL、reparse point/目录句柄保护、系统密钥存储和桌面捆绑仍待完成。

完整桌面预览构建入口：`./scripts/package-desktop.ps1`。使用 NSIS 覆盖配置捆绑整个后端目录，输出为未签名预览安装包，**目前未实机执行过此构建**。不得对外称正式 Windows 版完成。

打包仅包含 Git 跟踪的 core/verified 教学资源和文档，不包含 generated、学习记录、课程缓存及凭据。
PyInstaller 产物与构建系统相关，必须在 Windows 上构建 Windows 产物，不能用 Mac 构建通过替代 Windows 验收。

Windows 凭据验收：执行 `python scripts/test-windows-credentials.py`，只创建随机名称的假密钥，测试后删除；不读取或修改真实配置。
凭据命名固定为 `Trainer/<service>/<account>`，通用凭据 UTF-8 内容、本机当前用户持久化；不进入数据库、日志、命令参数或云同步。

凭据适配回归：发现并修复云课程恢复缓存旧目录的问题，改为调用统一的平台目录解析器并尊重当前显式目录配置。Windows 原生自测脚本已加入，但尚未在 Windows 执行；单元测试不能替代系统 API 验收。

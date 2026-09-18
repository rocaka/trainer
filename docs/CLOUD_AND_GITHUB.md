# Trainer 云同步与 GitHub 接入合同

## 当前交付边界

Trainer 继续采用 local-first：未配置 `TRAINER_CLOUD_ENDPOINT` 时不发起云请求。
GitHub 原生入口使用 Device Flow。OAuth App Client ID 是产品级公共配置，在打包时由
`TRAINER_GITHUB_CLIENT_ID` 写入应用；普通用户只需授权自己的 GitHub 账户。
`GET /v1/integrations/status` 只返回配置能力，不返回密钥。

## 云同步 v1

- 传输只允许 HTTPS；访问令牌必须存系统钥匙串，不进入 SQLite、日志或备份。
- `evidence` 与 `course-completion` 是追加且不可覆盖的事实；冲突时保留不同 ID，禁止最后写入覆盖。
- `profile` 与 `preference` 使用服务端版本号优先、时间戳次优的确定性合并。
- 每台设备维护服务端游标；上传/下载均分页、幂等，删除使用墓碑而非物理覆盖。
- 服务端主库存 PostgreSQL。Elasticsearch 只可作为可重建的搜索/分析投影，不能作为学习记录事实源。

建议服务端核心表：`accounts`、`devices`、`sync_changes`、`evidence`、`course_completions`、
`oauth_connections`。所有业务表必须包含 `account_id`，并启用行级租户隔离、审计日志与静态加密。

## GitHub v1

- 默认 scope 仅 `read:user`；仓库习惯分析由用户另行授权 `repo`，二者不得捆绑。
- 当前实现读取近一年贡献日历、提交贡献、PR、议题数量，以及最多 100 个本人公开仓库的语言字节聚合；不读取源码、仓库名、文件路径或提交消息。个人主页将活动日历与项目语言信号分开显示，项目语言不会改写课堂 AI 评估或学习 XP。
- GitHub 刷新由用户从设置页或个人主页主动触发。个人主页显示连接状态、最近同步状态和快速同步入口；没有同步缓存时明确显示“未连接”或“已连接 · 尚未同步”，不显示空白数据为成功。
- 当前不做编程时段、提交内容、代码质量或私有仓库分析；这些能力需要单独的最小权限授权和产品隐私评审，不能由 `read:user` 静默升级得到。
- 原生客户端使用 GitHub Device Flow，不需要回调服务器或 Client Secret。遵循轮询间隔、slow_down、拒绝、过期和取消状态。
- 用户令牌仅存系统钥匙串。断开操作删除本机令牌；GitHub 端撤销通过“管理 GitHub 授权”入口完成。
- 贡献统计只在连接后或手动刷新时请求，页面关闭取消进行中的请求；活动数量不代表能力评分。
- 参考：https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps

## 上线前仍需提供

1. 云服务正式 HTTPS 域名、账号登录方式、隐私政策和数据删除 SLA。
2. GitHub OAuth App 的真实账户验收：使用已打包的 Client ID 完成 Device Flow，并从个人主页手动同步一次，核对贡献日历和语言聚合。
3. PostgreSQL 托管实例、备份/恢复演练、速率限制和跨设备冲突集成测试环境。

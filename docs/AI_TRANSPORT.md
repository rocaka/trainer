# Trainer AI 接入层

## 请求路径

SwiftUI → 本地 Gateway → `model_transport.build_request` → 服务商。
课程、核验补齐、教练、评估和诊断共用请求构造；不在界面中调用云端或暴露密钥。

## OpenCode Go

- Luna：`gpt-5.6-luna`，`https://opencode.ai/zen/go/v1/responses`。
- Kimi 预设：`kimi-k2.7-code`，`https://opencode.ai/zen/go/v1/chat/completions`，需单独测试账号可用性。
- 使用真实 `User-Agent: Trainer/0.1.1`，不冒充其他客户端。
- `x-opencode-session` 按后台任务/课程会话稳定生成；重试沿用任务 ID。只发送散列标识，不发送本地路径。
- Chat Completions 的 Go 请求使用 `temperature: 1`；Responses 不附加此参数。
- 官方参考：https://opencode.ai/docs/go/

## macOS 网络兼容

macOS 使用系统 `/usr/bin/curl`，其他平台仍使用 Python urllib。
不忽略 TLS 校验、不改变代理、不自动重试、不跟随重定向。
curl 使用 `-q` 忽略用户 curlrc，防止配置意外开启不安全选项。
密钥与请求体只通过子进程标准输入传递，不进入命令行参数、临时文件或日志。
响应上限 16 MiB，连接超时最多 15 秒，总超时由业务指定。

这参考了 AI-INTEGRATION.md 的“桌面侧代理请求、普通回复测试、原生网络栈”思路，
但保留 Trainer 所需的结构化工具输出，不把纯聊天成功当作课程能力通过。

## 连接测试与错误

测试顺序：固定普通回复 → 固定结构化工具调用，每步最多 25 秒。
失败时显示阶段、HTTP 状态和 JSON/非 JSON 类型；不展示未经筛选的上游错误正文。
401/403 不自动解释为密钥缺失，也不自动重发收费请求。

## 配置和密钥

非敏感配置：`~/Library/Application Support/Trainer/ai-service.json`。
密钥：macOS 钥匙串，按 scheme/host/port 隔离；不复制参考项目的配置或密钥。
切换服务不会自动重建课程，已有学习计划继续保存。

配置归属：AI 端点、模型和 API Key 都属于当前 macOS 用户。正式产品不内置任何用户 API Key；每位用户在自己的 Trainer 设置中配置后，只影响自己的本机学习、生成和评判请求。

## 服务商与兼容范围

- DeepSeek：使用 `https://api.deepseek.com/v1` 与 Chat Completions 预设。
- OpenAI / GPT：使用 `https://api.openai.com/v1` 与 Responses 预设；模型 ID 以用户账户可用列表为准。
- OpenCode Go：提供 Luna 和 Kimi 的已知端点预设。
- 其他服务：只要兼容 OpenAI Responses 或 Chat Completions，并支持普通文本与函数调用，即可填写 Base URL、协议、模型和该服务的 API Key 接入。

保存前的连接测试会检查普通回复与函数调用。仅支持纯聊天、不能返回结构化工具结果的模型不能用于课程生成或代码评判。

## 验证（2026-09-08）

- Luna 的普通回复与结构化工具调用实测通过，两步约 8 秒；并非长期延迟保证。
- Python 回归测试 60 项通过。
- 未因连接测试发起完整课程重新生成。

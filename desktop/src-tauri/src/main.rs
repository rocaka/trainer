#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::io::Write;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::Manager;

#[derive(Default)]
struct PreviewGateway(Mutex<Option<OwnedGateway>>);

struct OwnedGateway {
    child: Child,
    token: String,
}

impl PreviewGateway {
    fn stop(&self) {
        if let Ok(mut state) = self.0.lock() {
            if let Some(mut owned) = state.take() {
                // Close ownership pipe: launcher terminates its own backend and
                // removes only its own temporary folder. Never kill by port/name.
                drop(owned.child.stdin.take());
                let deadline = Instant::now() + Duration::from_secs(10);
                while owned.child.try_wait().ok().flatten().is_none() && Instant::now() < deadline {
                    std::thread::sleep(Duration::from_millis(50));
                }
                if owned.child.try_wait().ok().flatten().is_none() {
                    let _ = owned.child.kill();
                }
                let _ = owned.child.wait();
            }
        }
    }
}

#[tauri::command]
fn start_preview(
    app: tauri::AppHandle,
    state: tauri::State<'_, PreviewGateway>,
) -> Result<(), String> {
    let isolated =
        cfg!(debug_assertions) && std::env::var("TRAINER_DESKTOP_ISOLATED").as_deref() == Ok("1");
    if !isolated && !cfg!(windows) {
        return Err("仅隔离开发模式允许启动测试后端，现有 Mac 服务不会被操作。".into());
    }
    let mut slot = state.0.lock().map_err(|_| "无法读取后端状态")?;
    if let Some(owned) = slot.as_mut() {
        if owned
            .child
            .try_wait()
            .map_err(|_| "无法检查后端进程")?
            .is_none()
        {
            return Ok(());
        }
    }
    let mut command = if isolated {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../scripts/gateway-preview.py");
        let mut cmd = Command::new(if cfg!(windows) { "python" } else { "python3" });
        cmd.arg(root).arg("--managed");
        cmd
    } else {
        let executable = app
            .path()
            .resource_dir()
            .map_err(|_| "无法找到应用资源")?
            .join("gateway/trainer-gateway.exe");
        if !executable.is_file() {
            return Err("安装包缺少本地后端，请重新安装完整 Windows 预览包".into());
        }
        Command::new(executable)
    };
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW; no secret on command line.
    }
    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "无法启动开发后端，请检查 Python 环境。")?;
    let token = format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    );
    let message = format!("{}\n", serde_json::json!({"session": token}));
    if child
        .stdin
        .as_mut()
        .ok_or("后端管道未建立")?
        .write_all(message.as_bytes())
        .is_err()
    {
        let _ = child.kill();
        let _ = child.wait();
        return Err("无法建立后端会话".into());
    }
    *slot = Some(OwnedGateway { child, token });
    Ok(())
}

#[tauri::command]
fn preview_status(state: tauri::State<'_, PreviewGateway>) -> Result<String, String> {
    let mut slot = state.0.lock().map_err(|_| "无法读取后端状态")?;
    match slot.as_mut() {
        Some(owned) => match owned.child.try_wait().map_err(|_| "无法检查后端状态")? {
            None => Ok("本地后端进程运行中".into()),
            Some(_) => Ok("本地后端已退出，请检查端口或重试启动".into()),
        },
        None => Ok("未启动隔离后端；默认读取现有本地服务".into()),
    }
}

fn session(state: &PreviewGateway) -> Result<String, String> {
    let mut slot = state.0.lock().map_err(|_| "无法读取会话")?;
    let owned = slot
        .as_mut()
        .ok_or("当前为只读连接；请使用隔离桌面模式或独立客户端")?;
    if owned
        .child
        .try_wait()
        .map_err(|_| "无法检查进程")?
        .is_some()
    {
        return Err("后端已退出，请重新启动".into());
    }
    Ok(owned.token.clone())
}

fn has_owned(state: &PreviewGateway) -> Result<bool, String> {
    Ok(state.0.lock().map_err(|_| "无法读取会话")?.is_some())
}

async fn decode_response(mut response: reqwest::Response) -> Result<serde_json::Value, String> {
    let status = response.status();
    const LIMIT: usize = 16 * 1024 * 1024;
    if response
        .content_length()
        .is_some_and(|length| length > LIMIT as u64)
    {
        return Err("本地响应超出读取上限".into());
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "本地响应未完整收到")? {
        if chunk.len() > LIMIT.saturating_sub(bytes.len()) {
            return Err("本地响应超出读取上限".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    let value: serde_json::Value =
        serde_json::from_slice(&bytes).map_err(|_| "后端返回格式不兼容")?;
    if !status.is_success() {
        return Err(value
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("本地请求失败")
            .to_string());
    }
    Ok(value)
}

async fn owned_request(
    state: tauri::State<'_, PreviewGateway>,
    path: &str,
    payload: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let token = session(&state)?;
    let client = local_client()?;
    let url = format!("http://127.0.0.1:18787{path}");
    let request = if let Some(body) = payload {
        client.post(url).json(&body)
    } else {
        client.get(url)
    };
    let response = request
        .header("X-Trainer-Session", token)
        .send()
        .await
        .map_err(|_| "本地后端尚未就绪，请稍后重试")?;
    decode_response(response).await
}

/// Fixed native capability bridge. The webview selects a named Trainer action,
/// never a URL, filesystem path or executable. This keeps the Windows UI on the
/// same Gateway workflows as the Mac client without exposing an open proxy.
#[tauri::command]
async fn trainer_action(
    state: tauri::State<'_, PreviewGateway>,
    action: String,
    payload: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let body = payload.unwrap_or_else(|| serde_json::json!({}));
    if serde_json::to_vec(&body).map_err(|_| "请求格式无效")?.len() > 64 * 1024 {
        return Err("请求内容超过本地接口上限".into());
    }
    let text = |key: &str| -> Result<String, String> {
        body.get(key)
            .and_then(|value| value.as_str())
            .filter(|value| !value.is_empty() && value.len() <= 200)
            .map(str::to_owned)
            .ok_or_else(|| "操作标识无效".into())
    };
    let segment = |key: &str| -> Result<String, String> {
        let value = text(key)?;
        if !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
        {
            return Err("操作标识包含不支持的字符".into());
        }
        Ok(value)
    };
    let (method, path) = match action.as_str() {
        "jobs" => ("GET", "/v1/jobs".into()),
        "skills" => ("GET", "/v1/skills".into()),
        "pending" => ("GET", "/v1/pending".into()),
        "account" => ("GET", "/v1/account".into()),
        "integrations" => ("GET", "/v1/integrations/status".into()),
        "editor-context" => ("GET", "/v1/editor/context".into()),
        "profile-save" => ("POST", "/v1/me".into()),
        "coach-turn" => ("POST", "/v1/coach/turn".into()),
        "evidence-save" => ("POST", "/v1/evidence".into()),
        "assessment" => ("POST", "/v1/assessments".into()),
        "lesson-task-prepare" => ("POST", "/v1/lesson-task/prepare".into()),
        "plan-generate" => ("POST", "/v1/learning/plan/jobs".into()),
        "candidate-generate" => ("POST", "/v1/skills/generate/jobs".into()),
        "teaching-signal" => ("POST", "/v1/teaching/signals".into()),
        "account-claim" => ("POST", "/v1/account/claim".into()),
        "account-sync" => ("POST", "/v1/account/sync".into()),
        "account-sign-out" => ("POST", "/v1/account/sign-out".into()),
        "submission-config" => ("GET", "/v1/course-submissions/config".into()),
        "submission-create" => ("POST", "/v1/course-submissions".into()),
        "pending-detail" => ("GET", format!("/v1/pending/{}", segment("id")?)),
        "pending-approve" => ("POST", format!("/v1/pending/{}/approve", segment("id")?)),
        "course-task" => {
            let plan = segment("planId")?;
            let lesson = segment("lessonId")?;
            ("GET", format!("/v1/course-task/{plan}/{lesson}"))
        }
        "progress" => ("GET", format!("/v1/progress/{}", segment("planId")?)),
        "job" => ("GET", format!("/v1/jobs/{}", segment("id")?)),
        "submission" => ("GET", format!("/v1/course-submissions/{}", segment("id")?)),
        _ => return Err("此桌面操作未开放".into()),
    };
    let token = session(&state)?;
    let client = reqwest::Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(190))
        .build()
        .map_err(|_| "无法创建本地连接")?;
    let url = format!("http://127.0.0.1:18787{path}");
    let request = if method == "POST" {
        client.post(url).json(&body)
    } else {
        client.get(url)
    };
    let response = request
        .header("X-Trainer-Session", token)
        .send()
        .await
        .map_err(|_| "本地服务未完成此操作，请检查连接后重试")?;
    decode_response(response).await
}

#[tauri::command]
async fn import_project(
    state: tauri::State<'_, PreviewGateway>,
) -> Result<serde_json::Value, String> {
    let folder = rfd::FileDialog::new()
        .set_title("选择要生成教学课程的项目目录")
        .pick_folder()
        .ok_or_else(|| "已取消选择项目目录".to_string())?;
    let canonical = folder.canonicalize().map_err(|_| "无法读取所选项目目录")?;
    if !canonical.is_dir() {
        return Err("所选位置不是可读取的项目目录".into());
    }
    owned_request(
        state,
        "/v1/projects/import/jobs",
        Some(serde_json::json!({"path": canonical})),
    )
    .await
}

#[tauri::command]
async fn desktop_runtime(
    state: tauri::State<'_, PreviewGateway>,
) -> Result<serde_json::Value, String> {
    if !has_owned(&state)? {
        return Ok(
            serde_json::json!({"owned": false, "isolated": false, "settingsWritable": false}),
        );
    }
    owned_request(state, "/v1/desktop/runtime", None).await
}

#[tauri::command]
async fn ai_settings(state: tauri::State<'_, PreviewGateway>) -> Result<serde_json::Value, String> {
    owned_request(state, "/v1/desktop/settings", None).await
}

#[tauri::command]
async fn save_ai_settings(
    state: tauri::State<'_, PreviewGateway>,
    settings: serde_json::Value,
) -> Result<serde_json::Value, String> {
    owned_request(state, "/v1/desktop/settings", Some(settings)).await
}

#[tauri::command]
async fn courses(state: tauri::State<'_, PreviewGateway>) -> Result<serde_json::Value, String> {
    owned_request(state, "/v1/desktop/courses", None).await
}

#[tauri::command]
async fn course(
    state: tauri::State<'_, PreviewGateway>,
    plan_id: String,
) -> Result<serde_json::Value, String> {
    if plan_id.len() != 64
        || !plan_id
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err("课程标识无效".into());
    }
    owned_request(state, &format!("/v1/desktop/courses/{plan_id}"), None).await
}

// Deliberately read-only: no arbitrary URL, file access or shell execution from the webview.
#[tauri::command]
async fn dashboard(state: tauri::State<'_, PreviewGateway>) -> Result<serde_json::Value, String> {
    if has_owned(&state)? {
        owned_request(state, "/v1/desktop/dashboard", None).await
    } else {
        local_read("/v1/me").await
    }
}

#[tauri::command]
async fn service_health(
    state: tauri::State<'_, PreviewGateway>,
) -> Result<serde_json::Value, String> {
    if has_owned(&state)? {
        owned_request(state, "/v1/desktop/health", None).await
    } else {
        local_read("/health").await
    }
}

async fn local_read(path: &str) -> Result<serde_json::Value, String> {
    let client = local_client()?;
    // Developer-only isolated preview; production cannot choose an arbitrary URL.
    let port = if cfg!(debug_assertions)
        && std::env::var("TRAINER_DESKTOP_ISOLATED").as_deref() == Ok("1")
    {
        18787
    } else {
        8787
    };
    let response = client
        .get(format!("http://127.0.0.1:{port}{path}"))
        .send()
        .await
        .map_err(|_| "无法连接本地 Gateway。请稍后刷新或检查后端状态。".to_string())?;
    if !response.status().is_success() {
        return Err("本地 Gateway 未能读取档案，请检查服务状态。".into());
    }
    decode_response(response).await
}

fn local_client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|_| "无法创建本地连接".to_string())
}

fn main() {
    tauri::Builder::default()
        .manage(PreviewGateway::default())
        .setup(|app| {
            if cfg!(windows)
                || (cfg!(debug_assertions)
                    && std::env::var("TRAINER_DESKTOP_ISOLATED").as_deref() == Ok("1"))
            {
                // Keep the window available for actionable retry/errors.
                let _ = start_preview(app.handle().clone(), app.state());
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            dashboard,
            service_health,
            start_preview,
            preview_status,
            desktop_runtime,
            ai_settings,
            save_ai_settings,
            courses,
            course,
            trainer_action,
            import_project
        ])
        .build(tauri::generate_context!())
        .expect("Trainer desktop startup failed")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                app.state::<PreviewGateway>().stop();
            }
        });
}

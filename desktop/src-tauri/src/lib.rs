use serde::Serialize;
use std::{
    fs,
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Child, Command},
    sync::Mutex,
};
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use tauri::{webview::PageLoadEvent, AppHandle, Manager, RunEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

struct DesktopRuntimeState {
    backend_child: Mutex<Option<Child>>,
    runtime_bootstrap: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct FrontendRuntimePayload {
    api_base_url: String,
    screenshot_base_url: String,
    mode: String,
    desktop_embedded: bool,
    session_token: String,
}

#[tauri::command]
fn desktop_runtime_mode() -> &'static str {
    "desktop"
}

#[tauri::command]
fn desktop_runtime_bootstrap(app: AppHandle) -> String {
    let state = app.state::<DesktopRuntimeState>();
    state.runtime_bootstrap.clone()
}

#[tauri::command]
fn open_external_url(url: String) -> Result<(), String> {
    let trimmed = url.trim();
    if !(trimmed.starts_with("https://") || trimmed.starts_with("http://")) {
        return Err("only http/https urls are allowed".to_string());
    }

    #[cfg(target_os = "macos")]
    let mut command = {
        let mut command = Command::new("open");
        command.arg(trimmed);
        command
    };

    #[cfg(target_os = "windows")]
    let mut command = {
        let mut command = Command::new("cmd");
        command.args(["/C", "start", "", trimmed]);
        command
    };

    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = {
        let mut command = Command::new("xdg-open");
        command.arg(trimmed);
        command
    };

    command
        .spawn()
        .map(|_| ())
        .map_err(|err| format!("failed to open external url: {err}"))
}

#[tauri::command]
fn get_autostart_enabled(app: AppHandle) -> Result<bool, String> {
    app.autolaunch().is_enabled().map_err(|err| err.to_string())
}

#[tauri::command]
fn set_autostart_enabled(app: AppHandle, enabled: bool) -> Result<(), String> {
    let manager = app.autolaunch();
    if enabled {
        manager.enable().map_err(|err| err.to_string())
    } else {
        manager.disable().map_err(|err| err.to_string())
    }
}

fn desktop_backend_port() -> u16 {
    8483
}

fn ensure_fixed_backend_port_available() -> Result<u16, String> {
    let port = desktop_backend_port();
    let listener = TcpListener::bind(("127.0.0.1", port)).map_err(|err| {
        format!(
            "NoteMeld MCP port {port} is unavailable: {err}. Check the occupying process with `lsof -i :8483`."
        )
    })?;
    drop(listener);
    Ok(port)
}

fn repo_root() -> Result<PathBuf, String> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .map_err(|err| format!("failed to resolve repo root: {err}"))
}

fn ensure_dir(path: &Path) -> Result<(), String> {
    fs::create_dir_all(path).map_err(|err| format!("failed to create directory {}: {err}", path.display()))
}

#[cfg(unix)]
fn ensure_executable_permissions(path: &Path) -> Result<(), String> {
    let current_mode = fs::metadata(path)
        .map_err(|err| format!("failed to inspect {} permissions: {err}", path.display()))?
        .permissions()
        .mode();

    if current_mode & 0o111 == 0o111 {
        return Ok(());
    }

    fs::set_permissions(path, fs::Permissions::from_mode(0o755))
        .map_err(|err| format!("failed to mark {} executable: {err}", path.display()))
}

fn command_succeeds(program: &Path, arg: &str) -> bool {
    Command::new(program)
        .arg(arg)
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn packaged_ffmpeg_is_usable(ffmpeg_binary: &Path, ffprobe_binary: &Path) -> bool {
    ffmpeg_binary.exists()
        && ffprobe_binary.exists()
        && command_succeeds(ffmpeg_binary, "-version")
        && command_succeeds(ffprobe_binary, "-version")
}

fn optional_packaged_ffmpeg_dir(result: Result<Option<PathBuf>, String>) -> Option<PathBuf> {
    match result {
        Ok(ffmpeg_dir) => ffmpeg_dir,
        Err(err) => {
            eprintln!("[notemeld] warning=ffmpeg-runtime-unavailable reason={err}");
            None
        }
    }
}

fn resolve_desktop_paths(app: &AppHandle) -> Result<(PathBuf, PathBuf), String> {
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("failed to resolve app data dir: {err}"))?;
    let log_dir = app
        .path()
        .app_log_dir()
        .map_err(|err| format!("failed to resolve app log dir: {err}"))?;
    ensure_dir(&data_dir)?;
    ensure_dir(&log_dir)?;
    Ok((data_dir, log_dir))
}

fn generate_session_token() -> String {
    let mut bytes = [0_u8; 32];
    getrandom::fill(&mut bytes).expect("secure random session token generation failed");
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn build_runtime_payload(port: u16, session_token: String) -> FrontendRuntimePayload {
    FrontendRuntimePayload {
        api_base_url: format!("http://127.0.0.1:{port}/api"),
        screenshot_base_url: format!("http://127.0.0.1:{port}/static/screenshots"),
        mode: "desktop".to_string(),
        desktop_embedded: true,
        session_token,
    }
}

fn build_runtime_bootstrap(payload: &FrontendRuntimePayload) -> Result<String, String> {
    let payload_json = serde_json::to_string(payload).map_err(|err| err.to_string())?;
    Ok(format!("window.__NOTEMELD_RUNTIME__ = {payload_json};"))
}

fn resolve_dev_backend_command(repo_root: &Path) -> Option<(PathBuf, Vec<String>, PathBuf)> {
    let script = repo_root.join("backend/desktop_entry.py");
    let python_candidates = [
        repo_root.join(".venv/bin/python3"),
        repo_root.join(".venv/bin/python"),
    ];

    for python in python_candidates {
        if python.exists() && script.exists() {
            return Some((
                python,
                vec![script.to_string_lossy().into_owned()],
                repo_root.join("backend"),
            ));
        }
    }

    None
}

fn resolve_packaged_backend_command(app: &AppHandle) -> Option<(PathBuf, Vec<String>, PathBuf)> {
    let resource_dir = app.path().resource_dir().ok()?;
    let binary = if cfg!(target_os = "windows") {
        resource_dir.join("bin/backend/notemeld-backend.exe")
    } else {
        resource_dir.join("bin/backend/notemeld-backend")
    };
    if binary.exists() {
        Some((binary, Vec::new(), resource_dir))
    } else {
        None
    }
}

fn resolve_packaged_ffmpeg_dir(app: &AppHandle) -> Option<PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    let archive = resource_dir.join("ffmpeg").join("ffmpeg-runtime.zip");
    if archive.exists() {
        Some(resource_dir.join("ffmpeg"))
    } else {
        None
    }
}

fn ensure_packaged_ffmpeg_dir(app: &AppHandle, data_dir: &Path) -> Result<Option<PathBuf>, String> {
    let resource_dir = match resolve_packaged_ffmpeg_dir(app) {
        Some(dir) => dir,
        None => return Ok(None),
    };
    let archive = resource_dir.join("ffmpeg-runtime.zip");
    let extracted_dir = data_dir.join("tools").join("ffmpeg");
    ensure_dir(&extracted_dir)?;

    let ffmpeg_binary = if cfg!(target_os = "windows") {
        extracted_dir.join("ffmpeg.exe")
    } else {
        extracted_dir.join("ffmpeg")
    };
    let ffprobe_binary = if cfg!(target_os = "windows") {
        extracted_dir.join("ffprobe.exe")
    } else {
        extracted_dir.join("ffprobe")
    };

    if ffmpeg_binary.exists() && ffprobe_binary.exists() {
        #[cfg(unix)]
        {
            ensure_executable_permissions(&ffmpeg_binary)?;
            ensure_executable_permissions(&ffprobe_binary)?;
        }

        if !packaged_ffmpeg_is_usable(&ffmpeg_binary, &ffprobe_binary) {
            fs::remove_dir_all(&extracted_dir).map_err(|err| {
                format!(
                    "failed to remove unusable bundled ffmpeg runtime {}: {err}",
                    extracted_dir.display()
                )
            })?;
            ensure_dir(&extracted_dir)?;
        }
    }

    if !packaged_ffmpeg_is_usable(&ffmpeg_binary, &ffprobe_binary) {
        #[cfg(target_os = "windows")]
        let mut command = {
            let mut command = Command::new("powershell");
            command.args([
                "-NoProfile",
                "-Command",
                &format!(
                    "Expand-Archive -LiteralPath '{}' -DestinationPath '{}' -Force",
                    archive.display(),
                    extracted_dir.display()
                ),
            ]);
            command
        };

        #[cfg(not(target_os = "windows"))]
        let mut command = {
            let mut command = Command::new("ditto");
            command.args(["-x", "-k"]);
            command.arg(&archive);
            command.arg(&extracted_dir);
            command
        };

        command
            .status()
            .map_err(|err| format!("failed to extract bundled ffmpeg runtime: {err}"))
            .and_then(|status| {
                if status.success() {
                    Ok(())
                } else {
                    Err(format!("failed to extract bundled ffmpeg runtime: exit status {status}"))
                }
            })?;
    }

    #[cfg(unix)]
    {
        ensure_executable_permissions(&ffmpeg_binary)?;
        ensure_executable_permissions(&ffprobe_binary)?;
    }

    if !packaged_ffmpeg_is_usable(&ffmpeg_binary, &ffprobe_binary) {
        return Err(format!(
            "bundled ffmpeg runtime is not executable after extraction: {}",
            extracted_dir.display()
        ));
    }

    Ok(Some(extracted_dir))
}

fn spawn_backend_sidecar(
    app: &AppHandle,
    port: u16,
    payload: &FrontendRuntimePayload,
) -> Result<Child, String> {
    let dev_backend_command = repo_root()
        .ok()
        .and_then(|root| resolve_dev_backend_command(&root));
    let (program, args, current_dir) = dev_backend_command
        .or_else(|| resolve_packaged_backend_command(app))
        .ok_or_else(|| "failed to locate desktop backend command".to_string())?;

    let (data_dir, log_dir) = resolve_desktop_paths(app)?;
    let note_output_dir = data_dir.join("note_results");
    let vector_store_dir = data_dir.join("chroma");
    let config_dir = data_dir.join("config");
    let model_dir = data_dir.join("models");
    let app_data_dir = data_dir.join("data");
    let frame_dir = app_data_dir.join("output_frames");
    let upload_dir = data_dir.join("uploads");
    let static_dir = data_dir.join("static");
    let screenshot_dir = static_dir.join("screenshots");
    let database_path = data_dir.join("notemeld.db");
    let downloader_config = config_dir.join("downloader.json");

    for path in [
        &note_output_dir,
        &vector_store_dir,
        &config_dir,
        &model_dir,
        &frame_dir,
        &upload_dir,
        &screenshot_dir,
    ] {
        ensure_dir(path)?;
    }

    let mut command = Command::new(program);
    command.args(args);
    command.current_dir(current_dir);
    command.env("NOTEMELD_RUNTIME_MODE", "desktop");
    command.env("NOTEMELD_DESKTOP_EMBEDDED", "1");
    command.env("NOTEMELD_DESKTOP_SESSION_TOKEN", &payload.session_token);
    command.env("BACKEND_HOST", "127.0.0.1");
    command.env("BACKEND_PORT", port.to_string());
    command.env("NOTEMELD_API_BASE_URL", &payload.api_base_url);
    command.env("NOTEMELD_DATA_DIR", &data_dir);
    command.env("NOTEMELD_LOG_DIR", &log_dir);
    command.env("NOTE_OUTPUT_DIR", &note_output_dir);
    command.env("VECTOR_DB_DIR", &vector_store_dir);
    command.env("NOTEMELD_DOWNLOADER_CONFIG", &downloader_config);
    command.env("NOTEMELD_TRANSCRIBER_CONFIG", config_dir.join("transcriber.json"));
    command.env("NOTEMELD_DATABASE_PATH", &database_path);
    command.env("DATABASE_URL", format!("sqlite:///{}", database_path.display()));
    command.env("NOTEMELD_MODEL_DIR", &model_dir);
    command.env("NOTEMELD_APP_DATA_DIR", &app_data_dir);
    command.env("NOTEMELD_FRAME_DIR", &frame_dir);
    command.env("DATA_DIR", &app_data_dir);
    command.env("UPLOAD_DIR", &upload_dir);
    command.env("STATIC_DIR", &static_dir);
    command.env("OUT_DIR", &screenshot_dir);

    if let Some(ffmpeg_dir) = optional_packaged_ffmpeg_dir(ensure_packaged_ffmpeg_dir(app, &data_dir)) {
        command.env("FFMPEG_BIN_PATH", ffmpeg_dir);
    } else if let Ok(ffmpeg_path) = std::env::var("FFMPEG_BIN_PATH") {
        command.env("FFMPEG_BIN_PATH", ffmpeg_path);
    }

    command
        .spawn()
        .map_err(|err| format!("failed to spawn backend sidecar: {err}"))
}

fn kill_backend(app: &AppHandle) {
    let backend_child = app.state::<DesktopRuntimeState>();
    let child_lock = backend_child.backend_child.lock();
    if let Ok(mut guard) = child_lock {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let port = ensure_fixed_backend_port_available().map_err(std::io::Error::other)?;
            let runtime_payload = build_runtime_payload(port, generate_session_token());
            let runtime_bootstrap =
                build_runtime_bootstrap(&runtime_payload).map_err(std::io::Error::other)?;
            let backend_child =
                spawn_backend_sidecar(app.handle(), port, &runtime_payload).map_err(std::io::Error::other)?;

            app.manage(DesktopRuntimeState {
                backend_child: Mutex::new(Some(backend_child)),
                runtime_bootstrap,
            });

            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
            }

            Ok(())
        })
        .on_page_load(|webview, payload| {
            if payload.event() == PageLoadEvent::Finished {
                let state = webview.app_handle().state::<DesktopRuntimeState>();
                let _ = webview.eval(&state.runtime_bootstrap);
            }
        })
        .invoke_handler(tauri::generate_handler![
            desktop_runtime_mode,
            desktop_runtime_bootstrap,
            open_external_url,
            get_autostart_enabled,
            set_autostart_enabled
        ])
        .build(tauri::generate_context!())
        .expect("error while building NoteMeld desktop")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                kill_backend(app_handle);
            }
        });
}

#[cfg(test)]
mod tests {
    #[cfg(unix)]
    use super::{
        desktop_backend_port, ensure_executable_permissions, ensure_fixed_backend_port_available,
        optional_packaged_ffmpeg_dir, packaged_ffmpeg_is_usable,
    };
    #[cfg(unix)]
    use std::{
        fs::{self, File},
        net::TcpListener,
        os::unix::fs::PermissionsExt,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    #[cfg(unix)]
    fn temp_test_path(name: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time should be after epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("notemeld-desktop-{name}-{nonce}"))
    }

    #[cfg(unix)]
    #[test]
    fn executable_file_can_be_rechecked_without_error() {
        let path = temp_test_path("already-executable");
        File::create(&path).expect("temp file should be created");
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755))
            .expect("temp file should become executable");

        let result = ensure_executable_permissions(&path);

        let mode = fs::metadata(&path)
            .expect("temp file metadata should exist")
            .permissions()
            .mode()
            & 0o777;
        let _ = fs::remove_file(&path);

        assert!(result.is_ok(), "already executable file should not fail");
        assert_eq!(mode, 0o755);
    }

    #[cfg(unix)]
    #[test]
    fn non_executable_file_gets_execute_bits() {
        let path = temp_test_path("needs-chmod");
        File::create(&path).expect("temp file should be created");
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644))
            .expect("temp file permissions should be set");

        ensure_executable_permissions(&path).expect("helper should add execute bits");

        let mode = fs::metadata(&path)
            .expect("temp file metadata should exist")
            .permissions()
            .mode()
            & 0o777;
        let _ = fs::remove_file(&path);

        assert_eq!(mode, 0o755);
    }

    #[cfg(unix)]
    #[test]
    fn packaged_ffmpeg_check_rejects_missing_runtime() {
        let ffmpeg = temp_test_path("missing-ffmpeg");
        let ffprobe = temp_test_path("missing-ffprobe");

        assert!(!packaged_ffmpeg_is_usable(&ffmpeg, &ffprobe));
    }

    #[cfg(unix)]
    #[test]
    fn packaged_ffmpeg_check_requires_commands_to_run() {
        let ffmpeg = temp_test_path("fake-ffmpeg");
        let ffprobe = temp_test_path("fake-ffprobe");
        fs::write(&ffmpeg, "#!/usr/bin/env sh\nexit 0\n").expect("fake ffmpeg should be written");
        fs::write(&ffprobe, "#!/usr/bin/env sh\nexit 1\n").expect("fake ffprobe should be written");
        fs::set_permissions(&ffmpeg, fs::Permissions::from_mode(0o755))
            .expect("fake ffmpeg should become executable");
        fs::set_permissions(&ffprobe, fs::Permissions::from_mode(0o755))
            .expect("fake ffprobe should become executable");

        let usable = packaged_ffmpeg_is_usable(&ffmpeg, &ffprobe);

        let _ = fs::remove_file(&ffmpeg);
        let _ = fs::remove_file(&ffprobe);
        assert!(!usable);
    }

    #[cfg(unix)]
    #[test]
    fn packaged_ffmpeg_setup_failure_does_not_abort_desktop_startup() {
        let result = optional_packaged_ffmpeg_dir(Err("ffmpeg runtime is not executable".to_string()));

        assert!(result.is_none());
    }

    #[test]
    fn desktop_backend_port_is_fixed_for_mcp_clients() {
        assert_eq!(desktop_backend_port(), 8483);
    }

    #[test]
    fn occupied_fixed_backend_port_error_mentions_mcp_port() {
        let listener = TcpListener::bind(("127.0.0.1", 8483))
            .expect("test should reserve fixed NoteMeld MCP port");

        let error = ensure_fixed_backend_port_available().expect_err("occupied port should fail");

        drop(listener);
        assert!(error.contains("8483"));
        assert!(error.contains("lsof -i :8483"));
    }
}

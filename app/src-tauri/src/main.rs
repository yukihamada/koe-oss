// KOE desktop shell.
//
// The app is a thin window around the local Python API. All logic lives in
// Python; this binary owns the window, the data directory and the API process
// lifecycle.
//
// Finding a working Python is the fiddly part. The API needs `koe_oss` plus
// (for synthesis) `mlx_audio`, and those may live in any number of venvs. We
// probe in order: an explicit override, a venv shipped next to the app, then
// any interpreter that can already import the package.

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use tauri::Manager;

struct ApiProcess(std::sync::Mutex<Option<Child>>);

#[tauri::command]
fn api_port() -> u16 {
    // Exposed to the UI via invoke; also used when starting the API.
    std::env::var("KOE_API_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(8807)
}

/// A python interpreter that can import `koe_oss`, or None.
fn probe(program: &str) -> bool {
    Command::new(program)
        .args(["-c", "import koe_oss.server.api"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn find_python() -> Option<String> {
    // 1. Explicit override wins — lets a user point at their own venv.
    if let Ok(p) = std::env::var("KOE_PYTHON") {
        if probe(&p) {
            return Some(p);
        }
    }
    // 2. Walk up from the executable looking for a venv that can import the
    //    package. The depth differs between a bare binary
    //    (.../app/src-tauri/target/release/koe-oss) and a bundled .app
    //    (.../KOE.app/Contents/MacOS/koe-oss), so we search every ancestor
    //    rather than assuming a fixed number of levels.
    let exe = std::env::current_exe().ok()?;
    let mut dir = exe.parent()?.to_path_buf();
    loop {
        for rel in ["venv/bin/python", "venv/bin/python3", ".venv/bin/python3"] {
            let cand: PathBuf = dir.join(rel);
            if cand.exists() && probe(&cand.to_string_lossy()) {
                return Some(cand.to_string_lossy().to_string());
            }
        }
        // Also try the repo root one level up from an `app/` checkout.
        let cand: PathBuf = dir.join("app").join("venv").join("bin").join("python");
        if cand.exists() && probe(&cand.to_string_lossy()) {
            return Some(cand.to_string_lossy().to_string());
        }
        match dir.parent() {
            Some(parent) => dir = parent.to_path_buf(),
            None => break,
        }
    }
    // 3. Whatever is on PATH.
    for p in ["python3", "python"] {
        if probe(p) {
            return Some(p.to_string());
        }
    }
    None
}

fn main() {
    tauri::Builder::default()
        .manage(ApiProcess(std::sync::Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![api_port])
        .setup(|app| {
            let port = api_port();

            if let Some(win) = app.get_webview_window("main") {
                let js = format!("window.__KOE_PORT__ = {};", port);
                let _ = win.eval(&js);
            }

            match find_python() {
                Some(py) => {
                    match Command::new(&py)
                        .args([
                            "-m",
                            "uvicorn",
                            "koe_oss.server.api:app",
                            "--port",
                            &port.to_string(),
                            "--host",
                            "127.0.0.1",
                        ])
                        .stdout(Stdio::null())
                        .stderr(Stdio::null())
                        .spawn()
                    {
                        Ok(c) => {
                            let state = app.state::<ApiProcess>();
                            *state.0.lock().unwrap() = Some(c);
                        }
                        Err(e) => eprintln!("failed to start API: {e}"),
                    }
                }
                None => eprintln!(
                    "no python with koe_oss found; set KOE_PYTHON or run scripts/setup-python.sh"
                ),
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<ApiProcess>();
                let maybe_child = state.0.lock().unwrap().take();
                if let Some(mut child) = maybe_child {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running KOE");
}

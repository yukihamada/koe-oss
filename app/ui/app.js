/* KOE desktop UI.
 *
 * Talks to the local Python API over 127.0.0.1. There is no cloud call
 * anywhere in this file — if that ever changes, it should be obvious here.
 */

const API = "http://127.0.0.1:8801";

const I18N = {
  ja: {
    tagline: "あなたの声を、あなたの手に。",
    status: "環境", loading: "読み込み中…",
    voices: "声", registerVoice: "声を登録する",
    handle: "名前", refAudio: "録音ファイル", refText: "録音の内容",
    register: "登録", consentHint: "登録後に同意が必要です",
    speak: "話す", voice: "声", text: "テキスト",
    synthesize: "合成", cancel: "中止",
    readings: "読み", add: "追加",
    readingsHint: "登録した語は、合成前に読みへ置き換えられます",
    localNote: "すべて手元の端末で処理されます。音声は外部へ送信されません。",
    grantConsent: "同意する", revoke: "撤回",
    noVoices: "声がまだ登録されていません",
    engineMissing: "音声エンジンが見つかりません",
    engineOk: "利用可能",
    offline: "APIに接続できません。サーバーを起動してください。",
    consentNeeded: "この声は同意が未登録です",
    ready: "準備完了", synthesizing: "合成中…", done: "完了",
    failed: "失敗", cancelled: "中止しました",
  },
  en: {
    tagline: "Your voice. On your device.",
    status: "Environment", loading: "Loading…",
    voices: "Voices", registerVoice: "Register a voice",
    handle: "Name", refAudio: "Recording file", refText: "What you said",
    register: "Register", consentHint: "Consent is required after registering",
    speak: "Speak", voice: "Voice", text: "Text",
    synthesize: "Synthesize", cancel: "Cancel",
    readings: "Readings", add: "Add",
    readingsHint: "Registered words are replaced before synthesis",
    localNote: "Everything runs on this device. No audio leaves your machine.",
    grantConsent: "Consent", revoke: "Revoke",
    noVoices: "No voices registered yet",
    engineMissing: "No synthesis engine found",
    engineOk: "available",
    offline: "Cannot reach the API. Start the server.",
    consentNeeded: "This voice has no consent record",
    ready: "Ready", synthesizing: "Synthesizing…", done: "Done",
    failed: "Failed", cancelled: "Cancelled",
  },
};

let LANG = "ja";
const t = (k) => (I18N[LANG][k] ?? k);

function el(id) { return document.getElementById(id); }

/* ------------------------------------------------------------------ i18n */
function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((n) => {
    n.textContent = t(n.dataset.i18n);
  });
  el("lang-btn").textContent = LANG === "ja" ? "EN" : "日本語";
  document.documentElement.lang = LANG;
}

el("lang-btn").addEventListener("click", () => {
  LANG = LANG === "ja" ? "en" : "ja";
  applyI18n();
  refreshAll();
});

/* ------------------------------------------------------------------- api */
async function api(path, opts) {
  try {
    const r = await fetch(API + path, opts);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) return { error: body.detail ?? r.statusText, status: r.status };
    return body;
  } catch (e) {
    return { error: t("offline") };
  }
}

/* ---------------------------------------------------------------- status */
async function refreshStatus() {
  const h = await api("/health");
  const box = el("status-body");
  if (h.error) { box.textContent = h.error; box.className = "muted"; return; }
  const engine = h.engine
    ? `${h.engine} — ${t("engineOk")}`
    : t("engineMissing");
  box.className = h.engine ? "" : "muted";
  box.textContent = `${engine} · ${t("voices")}: ${h.voices} · ${h.data_dir}`;
}

/* ---------------------------------------------------------------- voices */
async function refreshVoices() {
  const r = await api("/voices");
  const box = el("voices");
  const sel = el("s-voice");
  box.innerHTML = "";
  sel.innerHTML = "";
  if (r.error) { box.innerHTML = `<div class="empty">${r.error}</div>`; return; }
  if (!r.voices.length) {
    box.innerHTML = `<div class="empty">${t("noVoices")}</div>`;
  }
  for (const v of r.voices) {
    const row = document.createElement("div");
    row.className = "item";
    const cls = v.consent_state === "current" ? "ok"
      : v.consent_state === "stale" ? "warn" : "err";
    row.innerHTML = `
      <span class="name">${v.handle}</span>
      <span class="badge ${cls}">${v.consent_state}</span>
      <span class="grow muted">${v.lang}</span>`;
    if (v.consent_state !== "current") {
      const b = document.createElement("button");
      b.className = "ghost";
      b.textContent = t("grantConsent");
      b.onclick = async () => {
        await api(`/voices/${v.handle}/consent`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ age_ok: true }),
        });
        refreshVoices();
      };
      row.appendChild(b);
    }
    box.appendChild(row);

    const o = document.createElement("option");
    o.value = v.handle;
    o.textContent = v.handle;
    sel.appendChild(o);
  }
}

el("v-add").addEventListener("click", async () => {
  const body = {
    handle: el("v-handle").value.trim(),
    ref_audio: el("v-ref").value.trim(),
    ref_text: el("v-text").value.trim(),
    lang: "ja",
  };
  if (!body.handle || !body.ref_audio) return;
  const r = await api("/voices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (r.error) { alert(r.error.message ?? JSON.stringify(r.error)); return; }
  el("v-handle").value = ""; el("v-ref").value = ""; el("v-text").value = "";
  refreshVoices();
});

/* --------------------------------------------------------------- readings */
async function refreshReadings() {
  const r = await api("/readings");
  const box = el("readings");
  box.innerHTML = "";
  if (r.error) return;
  const rows = [...(r.applied ?? []), ...(r.proposed ?? [])];
  if (!rows.length) box.innerHTML = `<div class="empty">—</div>`;
  for (const e of rows) {
    const row = document.createElement("div");
    row.className = "item";
    row.innerHTML = `<span class="name">${e.word}</span>
      <span class="muted">→</span><span>${e.reading}</span>
      ${e.state === "proposed" ? `<span class="badge warn">proposed</span>` : ""}
      <span class="grow"></span>`;
    const b = document.createElement("button");
    b.className = "ghost"; b.textContent = "×";
    b.onclick = async () => {
      await api(`/readings/${encodeURIComponent(e.word)}`, { method: "DELETE" });
      refreshReadings();
    };
    row.appendChild(b);
    box.appendChild(row);
  }
}

el("r-add").addEventListener("click", async () => {
  const word = el("r-word").value.trim();
  const reading = el("r-reading").value.trim();
  if (!word || !reading) return;
  await api(`/readings/${encodeURIComponent(word)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word, reading }),
  });
  el("r-word").value = ""; el("r-reading").value = "";
  refreshReadings();
});

/* ----------------------------------------------------------------- speak */
let currentJob = null;

el("s-go").addEventListener("click", async () => {
  const voice = el("s-voice").value;
  const text = el("s-text").value.trim();
  if (!voice || !text) return;

  el("s-go").disabled = true;
  el("s-stop").disabled = false;
  el("s-progress").textContent = t("synthesizing");
  el("s-result").innerHTML = "";

  const r = await api("/synth", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ voice_id: voice, text }),
  });

  el("s-go").disabled = false;
  el("s-stop").disabled = true;

  if (r.error) {
    const msg = r.error.message ?? JSON.stringify(r.error);
    el("s-progress").textContent = t("failed");
    el("s-result").innerHTML = `<div class="badge err">${msg}</div>`;
    return;
  }
  el("s-progress").textContent = t("done");
  el("s-result").innerHTML = `
    <audio controls src="${API}/audio?path=${encodeURIComponent(r.audio_path)}"></audio>
    <div class="hint">${r.duration_sec}s · ${r.engine}${
      r.corrected ? " · " + t("readingsHint") : ""}</div>`;
});

el("s-stop").addEventListener("click", async () => {
  if (currentJob) {
    await api(`/jobs/${currentJob}/cancel`, { method: "POST" });
  }
  el("s-stop").disabled = true;
  el("s-progress").textContent = t("cancelled");
});

/* ------------------------------------------------------------------ boot */
function refreshAll() {
  refreshStatus();
  refreshVoices();
  refreshReadings();
}

applyI18n();
refreshAll();
setInterval(refreshStatus, 10000);

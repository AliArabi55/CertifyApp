const API = "/api";
const state = {
  projectId: null,
  mode: null,
  canvas: null,
  bgScale: 1,
  fields: [],
  generatedRows: [],
  csrfToken: "",
  resetToken: "",
};

function $(id) {
  return document.getElementById(id);
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.csrfToken && !["GET", "HEAD", "OPTIONS"].includes((options.method || "GET").toUpperCase())) {
    headers.set("X-CSRF-Token", state.csrfToken);
  }
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join("; ")
      : data.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response;
}

function setAuthView(view) {
  const views = { login: "loginForm", register: "registerForm", forgot: "forgotForm", reset: "resetForm" };
  Object.entries(views).forEach(([name, id]) => { $(id).hidden = name !== view; });
  $("authHeading").textContent = view === "register" ? "Create your Certify account"
    : view === "forgot" ? "Reset your password"
      : view === "reset" ? "Choose a new password" : "Sign in to Certify";
}

function showSignedIn(user) {
  state.csrfToken = user.csrf_token;
  $("authView").hidden = true;
  document.querySelector(".steps").hidden = false;
  document.querySelector("main").hidden = false;
  $("accountBar").hidden = false;
  $("accountEmail").textContent = user.email;
  refreshGmailStatus().catch(() => { $("gmailStatus").textContent = "Could not check Gmail connection"; });
}

function showAuthError(error) {
  $("authStatus").textContent = error.message || "The request failed. Please try again.";
}

$("showRegisterBtn").addEventListener("click", () => setAuthView("register"));
$("showForgotBtn").addEventListener("click", () => setAuthView("forgot"));
$("showLoginFromRegisterBtn").addEventListener("click", () => setAuthView("login"));
$("showLoginFromForgotBtn").addEventListener("click", () => setAuthView("login"));

$("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("authStatus").textContent = "";
  try {
    const response = await apiFetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("loginEmail").value, password: $("loginPassword").value }),
    });
    showSignedIn(await response.json());
  } catch (error) { showAuthError(error); }
});

$("registerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("authStatus").textContent = "";
  try {
    const response = await apiFetch(`${API}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("registerEmail").value, password: $("registerPassword").value }),
    });
    const data = await response.json();
    $("authStatus").textContent = data.message;
    $("loginEmail").value = $("registerEmail").value;
    $("registerPassword").value = "";
    setAuthView("login");
  } catch (error) { showAuthError(error); }
});

$("forgotForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const response = await apiFetch(`${API}/auth/password-reset-request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("forgotEmail").value }),
    });
    $("authStatus").textContent = (await response.json()).message;
  } catch (error) { showAuthError(error); }
});

$("resetForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const response = await apiFetch(`${API}/auth/password-reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: state.resetToken, password: $("resetPassword").value }),
    });
    const data = await response.json();
    state.resetToken = "";
    $("resetPassword").value = "";
    $("authStatus").textContent = data.message;
    setAuthView("login");
  } catch (error) { showAuthError(error); }
});

$("signOutBtn").addEventListener("click", async () => {
  try { await apiFetch(`${API}/auth/logout`, { method: "POST" }); } catch (_) {}
  state.csrfToken = "";
  state.projectId = null;
  state.generatedRows = [];
  $("accountBar").hidden = true;
  $("authView").hidden = false;
  document.querySelector(".steps").hidden = true;
  document.querySelector("main").hidden = true;
  $("loginPassword").value = "";
  setAuthView("login");
});

async function initializeAuthentication() {
  const params = new URLSearchParams(window.location.search);
  const verificationToken = params.get("verify");
  state.resetToken = params.get("reset") || "";
  if (verificationToken) {
    try {
      const response = await apiFetch(`${API}/auth/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: verificationToken }),
      });
      $("authStatus").textContent = (await response.json()).message;
    } catch (error) { showAuthError(error); }
    history.replaceState(null, "", window.location.pathname);
  }
  if (state.resetToken) {
    setAuthView("reset");
    history.replaceState(null, "", window.location.pathname);
    return;
  }
  try {
    const response = await apiFetch(`${API}/auth/me`);
    showSignedIn(await response.json());
  } catch (_) {
    $("authView").hidden = false;
    document.querySelector(".steps").hidden = true;
    document.querySelector("main").hidden = true;
    setAuthView("login");
  }
}

function onAction(target, action) {
  const button = typeof target === "string" ? $(target) : target;
  button.addEventListener("click", async () => {
    button.disabled = true;
    $("appStatus").textContent = "";
    try {
      await action();
    } catch (error) {
      $("appStatus").textContent = error.message || "The request failed. Please try again.";
      if (button.id === "sendAllBtn") $("sendAllStatus").textContent = "Sending stopped. Check the error above before retrying.";
    } finally {
      button.disabled = false;
    }
  });
}

let emailEditor = null;
let editorMode = "html";
let editorSelection = { index: 0, length: 0 };
let draftDirty = false;

function markDraftDirty() {
  draftDirty = true;
  $("editorStatus").textContent = "Unsaved changes";
}

["subjectInput", "htmlTextarea"].forEach((id) => $(id).addEventListener("input", markDraftDirty));
window.addEventListener("beforeunload", (event) => {
  if (draftDirty && state.projectId) {
    event.preventDefault();
    event.returnValue = "";
  }
});

function previewImageSources(html) {
  return html.replace(/src=(["'])cid:([a-zA-Z0-9_-]+)\1/g, (_match, quote, cid) =>
    `src=${quote}${API}/projects/${state.projectId}/email-images/by-cid/${cid}${quote}`);
}

function getDraftHtml() {
  if (editorMode === "html") return $("htmlTextarea").value;
  if (emailEditor.getLength() === 1 && !emailEditor.root.querySelector("img")) return "";
  const documentBody = new DOMParser().parseFromString(emailEditor.getSemanticHTML(), "text/html");
  documentBody.querySelectorAll("img").forEach((image) => {
    const prefix = `${API}/projects/${state.projectId}/email-images/by-cid/`;
    const source = image.getAttribute("src") || "";
    if (source.startsWith(prefix)) image.setAttribute("src", `cid:${source.slice(prefix.length)}`);
    image.style.maxWidth = "100%";
  });
  return documentBody.body.innerHTML;
}

function setEditorMode(mode) {
  if (mode === editorMode) return;
  if (mode === "visual") {
    if (!emailEditor) return;
    const html = $("htmlTextarea").value;
    if (html.trim() && !confirm("Switch to Compose? Complex HTML layouts may be simplified. Cancel to keep editing the original HTML.")) return;
    emailEditor.clipboard.dangerouslyPasteHTML(DOMPurify.sanitize(previewImageSources(html)));
  } else {
    $("htmlTextarea").value = getDraftHtml();
  }
  editorMode = mode;
  $("visualComposer").hidden = mode !== "visual";
  $("htmlTextarea").hidden = mode !== "html";
  $("visualModeBtn").setAttribute("aria-pressed", String(mode === "visual"));
  $("htmlModeBtn").setAttribute("aria-pressed", String(mode === "html"));
}

if (window.Quill && window.DOMPurify) {
  ["align", "direction", "font", "size"].forEach((format) => {
    Quill.register(Quill.import(`attributors/style/${format}`), true);
  });
  emailEditor = new Quill("#emailEditor", {
    theme: "snow",
    modules: { toolbar: [
      [{ font: [] }, { size: ["10px", false, "18px", "32px"] }],
      ["bold", "italic", "underline", "strike"],
      [{ color: [] }, { background: [] }],
      [{ list: "ordered" }, { list: "bullet" }],
      [{ align: [] }, { direction: "rtl" }],
      ["link", "clean"],
    ] },
  });
  emailEditor.root.setAttribute("aria-label", "Email message");
  emailEditor.on("text-change", markDraftDirty);
  emailEditor.on("selection-change", (range) => { if (range) editorSelection = range; });
  document.querySelectorAll(".ql-toolbar button").forEach((button) => {
    const format = [...button.classList].find((name) => name.startsWith("ql-"))?.slice(3);
    const label = `${format || "Format"}${button.value ? ` ${button.value}` : ""}`;
    button.title = label;
    button.setAttribute("aria-label", label);
  });
  setEditorMode("visual");
} else {
  $("visualComposer").hidden = true;
  $("htmlTextarea").hidden = false;
  $("visualModeBtn").disabled = true;
  $("visualModeBtn").setAttribute("aria-pressed", "false");
  $("htmlModeBtn").setAttribute("aria-pressed", "true");
  $("editorStatus").textContent = "Compose could not load. HTML editing is still available.";
}
$("visualModeBtn").addEventListener("click", () => setEditorMode("visual"));
$("htmlModeBtn").addEventListener("click", () => setEditorMode("html"));

function insertEmailContent(html) {
  if (editorMode === "html") {
    insertAtCursor($("htmlTextarea"), html);
    markDraftDirty();
    return;
  }
  const index = Math.min(editorSelection.index, emailEditor.getLength() - 1);
  emailEditor.clipboard.dangerouslyPasteHTML(index, DOMPurify.sanitize(previewImageSources(html)), "user");
  emailEditor.focus();
}

// ---------- Step navigation ----------
document.querySelectorAll(".steps button").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (!state.projectId) return alert("Create a project first");
    showStep(btn.dataset.step);
  });
});

function showStep(n) {
  document.querySelectorAll(".step").forEach((s) => s.classList.remove("active"));
  document.querySelectorAll(".steps button").forEach((b) => b.classList.remove("active"));
  $(`step-${n}`).classList.add("active");
  document.querySelector(`.steps button[data-step="${n}"]`).classList.add("active");
}

// ---------- Step 0: choose mode & create project ----------
document.querySelectorAll(".mode-card").forEach((btn) => {
  onAction(btn, async () => {
    const name = $("projectNameInput").value.trim();
    if (!name) return alert("Enter a project name first");
    const mode = btn.dataset.mode;
    const form = new FormData();
    form.append("name", name);
    form.append("mode", mode);
    const res = await apiFetch(`${API}/projects`, { method: "POST", body: form });
    const project = await res.json();
    state.projectId = project.id;
    state.mode = mode;
    $("projectStatus").textContent = `Project created: ${project.name}`;
    applyMode(mode);
  });
});

function applyMode(mode) {
  $("step-0").classList.remove("active");
  document.querySelector('.steps button[data-step="1"]').style.display =
    mode === "emails_only" ? "none" : "";
  if (mode === "emails_only") {
    $("generateBtn").textContent = "Load recipients";
    showStep(2);
  } else {
    showStep(1);
  }
}

// ---------- Step 1: Designer ----------
const certificateFonts = {
  "arial.ttf": { family: "Arial" },
  "arialbd.ttf": { family: "Arial", bold: true },
  "times.ttf": { family: "Times New Roman" },
  "timesbd.ttf": { family: "Times New Roman", bold: true },
  "calibri.ttf": { family: "Calibri" },
  "calibrib.ttf": { family: "Calibri", bold: true },
};

onAction("uploadBgBtn", async () => {
  if (!state.projectId) return alert("Create a project first");
  const file = $("bgFileInput").files[0];
  if (!file) return alert("Choose an image file");
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API}/projects/${state.projectId}/background`, { method: "POST", body: form });
  const project = await res.json();
  $("designerRow").style.display = "flex";
  loadCanvasBackground(`${API}/projects/${state.projectId}/asset/${project.background}?t=${Date.now()}`);
});

function loadCanvasBackground(url) {
  const firstTime = !state.canvas;
  if (firstTime) {
    state.canvas = new fabric.Canvas("designerCanvas");
    bindCanvasSelectionEvents();
  }
  fabric.Image.fromURL(
    url,
    (img) => {
      const available = document.querySelector(".canvas-wrap").clientWidth || 800;
      const maxWidth = Math.max(260, Math.min(800, available));
      const scale = Math.min(1, maxWidth / img.width);
      state.bgScale = scale;
      state.canvas.setWidth(img.width * scale);
      state.canvas.setHeight(img.height * scale);
      state.canvas.setBackgroundImage(img, state.canvas.renderAll.bind(state.canvas), {
        scaleX: scale,
        scaleY: scale,
      });
    },
    { crossOrigin: "anonymous" }
  );
}

function bindCanvasSelectionEvents() {
  state.canvas.on("selection:created", updatePropsPanel);
  state.canvas.on("selection:updated", updatePropsPanel);
  state.canvas.on("selection:cleared", () => ($("fieldProps").style.display = "none"));
}

function updatePropsPanel() {
  const obj = state.canvas.getActiveObject();
  if (!obj) return;
  $("fieldProps").style.display = "block";
  $("fieldNameLabel").textContent = obj.data?.name || "";
  $("fontSizeInput").value = Math.round(obj.fontSize * obj.scaleY);
  $("fontColorInput").value = obj.fill;
  $("boldInput").checked = !!obj.data?.bold;
  $("italicInput").checked = !!obj.data?.italic;
  $("fontFamilySelect").value = obj.data?.font || "arial.ttf";
  const custom = certificateFonts[$("fontFamilySelect").value]?.custom || false;
  $("boldInput").disabled = custom;
  $("italicInput").disabled = custom;
}

$("addFieldBtn").addEventListener("click", () => {
  if (!state.canvas) return alert("Upload a background image first");
  const name = prompt("Variable name (e.g. Name, Role, Date):")?.trim();
  if (!name) return;
  if (!/^[A-Za-z0-9][A-Za-z0-9_]*$/.test(name)) return alert("Use only letters, numbers and underscores");
  if (state.canvas.getObjects().some((obj) => obj.data?.name === name)) return alert("This field already exists");
  const text = new fabric.Text(name, {
    left: state.canvas.getWidth() / 2,
    top: state.canvas.getHeight() / 2,
    fontSize: 28,
    fill: "#000000",
    fontFamily: "Arial",
    originX: "center",
    originY: "center",
    textAlign: "center",
    lockRotation: true,
    lockScalingFlip: true,
  });
  text.setControlsVisibility({ ml: false, mr: false, mt: false, mb: false, mtr: false });
  text.data = { name, font: "arial.ttf", bold: false, italic: false };
  state.canvas.add(text);
  state.canvas.setActiveObject(text);
  updatePropsPanel();
});

["fontSizeInput", "fontColorInput", "boldInput", "italicInput", "fontFamilySelect"].forEach((id) => {
  $(id).addEventListener("input", () => {
    const obj = state.canvas?.getActiveObject();
    if (!obj) return;
    const font = certificateFonts[$("fontFamilySelect").value] || { family: "Arial" };
    $("boldInput").disabled = !!font.custom;
    $("italicInput").disabled = !!font.custom;
    if (font.custom) {
      $("boldInput").checked = false;
      $("italicInput").checked = false;
    }
    if (id === "fontSizeInput") obj.set({ scaleX: 1, scaleY: 1 });
    obj.set({
      fontSize: id === "fontSizeInput" ? Math.max(6, Math.min(300, parseInt($("fontSizeInput").value, 10) || obj.fontSize)) : obj.fontSize,
      fill: $("fontColorInput").value,
      fontFamily: font.family,
      fontWeight: $("boldInput").checked || font.bold ? "bold" : "normal",
      fontStyle: $("italicInput").checked ? "italic" : "normal",
    });
    obj.data.bold = $("boldInput").checked;
    obj.data.italic = $("italicInput").checked;
    obj.data.font = $("fontFamilySelect").value;
    state.canvas.renderAll();
  });
});

$("deleteFieldBtn").addEventListener("click", () => {
  const obj = state.canvas.getActiveObject();
  if (obj) state.canvas.remove(obj);
  $("fieldProps").style.display = "none";
});

onAction("uploadFontBtn", async () => {
  const file = $("fontFileInput").files[0];
  if (!file || !state.projectId) return alert("Create a project and choose a .ttf file first");
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API}/projects/${state.projectId}/fonts`, { method: "POST", body: form });
  const data = await res.json();
  const family = `Custom_${data.filename.replace(/\W/g, "_")}`;
  const font = new FontFace(family, `url("${API}/projects/${state.projectId}/fonts/${encodeURIComponent(data.filename)}")`);
  document.fonts.add(await font.load());
  certificateFonts[data.filename] = { family, custom: true };
  const opt = document.createElement("option");
  opt.value = data.filename;
  opt.textContent = `${data.filename} (custom)`;
  $("fontFamilySelect").appendChild(opt);
});

onAction("saveFieldsBtn", async () => {
  if (!state.canvas) return;
  const fields = state.canvas.getObjects().filter((obj) => obj.data?.name).map((obj) => ({
    name: obj.data.name,
    x: Math.round(obj.left / state.bgScale),
    y: Math.round(obj.top / state.bgScale),
    font_size: Math.round(obj.fontSize * obj.scaleY / state.bgScale),
    color: obj.fill,
    font: obj.data.font,
    bold: obj.data.bold,
    italic: obj.data.italic,
    anchor: "mm",
  }));
  const res = await apiFetch(`${API}/projects/${state.projectId}/fields`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (res.ok) state.fields = fields;
  alert(res.ok ? `Saved ${fields.length} field(s).` : `Failed to save fields: ${await res.text()}`);
});

// ---------- Step 2: Recipients & bulk generation ----------
$("downloadTemplateBtn").addEventListener("click", () => {
  if (!state.projectId) return alert("Create a project first (Step 1)");
  window.location.href = `${API}/projects/${state.projectId}/template.xlsx`;
});

onAction("generateBtn", async () => {
  const file = $("excelFileInput").files[0];
  if (!file || !state.projectId) return alert("Choose the filled Excel file");
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API}/projects/${state.projectId}/generate`, { method: "POST", body: form });
  const data = await res.json();
  state.generatedRows = data.rows;
  renderGeneratedTable(data.rows);
  populateRowSelects(data.rows);
});

function renderGeneratedTable(rows) {
  const tbody = $("generatedTableBody");
  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [row.Name || "", row.Email || ""].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      tr.appendChild(cell);
    });
    const certificate = document.createElement("td");
    if (row._certificate_file) {
      const link = document.createElement("a");
      link.href = `${API}/projects/${state.projectId}/generated/${encodeURIComponent(row._certificate_file)}`;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "Download";
      certificate.appendChild(link);
    } else {
      certificate.textContent = "-";
    }
    tr.appendChild(certificate);
    tbody.appendChild(tr);
  });
  $("generatedCount").textContent = `${rows.length} recipient(s) loaded.`;
}

function populateRowSelects(rows) {
  ["previewRowSelect", "testRowSelect"].forEach((id) => {
    const select = $(id);
    select.innerHTML = "";
    rows.forEach((row, i) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = row.Name || row.Email || `Row ${i + 1}`;
      select.appendChild(opt);
    });
  });
}

// ---------- Step 3: Email draft ----------
function insertAtCursor(textarea, text) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  textarea.value = textarea.value.slice(0, start) + text + textarea.value.slice(end);
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = start + text.length;
}

$("generatePromptBtn").addEventListener("click", () => {
  const context = $("emailContextInput").value.trim() || "a general announcement email";
  const vars = [...new Set([...state.fields.map((f) => f.name), "Email"])];
  let p = `Write the HTML body of an email about: ${context}.\n`;
  p += vars.length
    ? `Use these exact merge placeholders where personalization is needed (do not invent new ones): ${vars.map((v) => "{{" + v + "}}").join(", ")}.\n`
    : "Use {{Variable}} style placeholders for any personalization (e.g. {{Name}}), matching column names I will provide in an Excel sheet.\n";
  p += "Always personalize the greeting with {{Name}} if it exists.\n";
  if ($("optBold").checked) {
    p += "Use <b>bold</b> text and varied HTML formatting (headings, short paragraphs, an emoji or two) to make it engaging, but keep it professional.\n";
  }
  if ($("optImage").checked) {
    p += "Leave a clearly marked placeholder comment <!-- IMAGE HERE --> where a photo/banner image should go; I will insert the actual <img> tag myself.\n";
  }
  if ($("optLinkedIn").checked) {
    p += 'Include a short paragraph inviting the recipient to share their achievement on LinkedIn; I will insert the actual share button myself, so just leave a placeholder comment <!-- LINKEDIN BUTTON HERE -->.\n';
  }
  if ($("optCertNote").checked) {
    p += "Mention that their certificate is attached to this email.\n";
  }
  p += "Output ONLY the inner HTML for the email body (no <html>/<head> tags), using inline CSS styles since email clients don't support external stylesheets.";
  $("aiPromptOutput").value = p;
  $("aiPromptOutput").style.display = "block";
  $("copyPromptBtn").style.display = "inline-block";
});

onAction("copyPromptBtn", async () => {
  await navigator.clipboard.writeText($("aiPromptOutput").value);
  alert("Prompt copied! Paste it into ChatGPT or Gemini, then paste the HTML it gives back into the box below.");
});

onAction("uploadEmailImageBtn", async () => {
  if (!state.projectId) return alert("Create a project first");
  const file = $("emailImageInput").files[0];
  if (!file) return alert("Choose an image");
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API}/projects/${state.projectId}/email-images`, { method: "POST", body: form });
  const data = await res.json();
  const tag = `<img src="cid:${data.cid}" alt="" style="max-width:100%;display:block;margin:12px 0;" />`;
  insertEmailContent(tag);
});

$("insertLinkedInBtn").addEventListener("click", () => {
  const snippet = `\n<table role="presentation" cellpadding="0" cellspacing="0"><tr><td align="center" style="background-color:#0a66c2;border-radius:6px;">\n<a href="{{LinkedIn_Share_Link}}" target="_blank" style="display:inline-block;padding:12px 24px;color:#ffffff;font-weight:bold;font-size:14px;text-decoration:none;">\ud83d\udc49 Share on LinkedIn</a>\n</td></tr></table>\n`;
  insertEmailContent(snippet);
  alert(
    "Inserted. This links to a {{LinkedIn_Share_Link}} column you provide in your Excel sheet " +
      "(pre-fills a LinkedIn post with your caption). Note: LinkedIn does not support auto-attaching " +
      "the certificate file via a link — the recipient will need to attach it manually on both desktop and mobile."
  );
});

async function saveCurrentDraft(forSending = false) {
  if (!state.projectId) throw new Error("Create a project first");
  const draft = { subject: $("subjectInput").value, html: getDraftHtml() };
  if (forSending && (!draft.subject.trim() || !draft.html.trim())) {
    throw new Error("Enter a subject and message before sending");
  }
  const res = await apiFetch(`${API}/projects/${state.projectId}/email-draft`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  const data = await res.json();
  $("detectedVariables").textContent = data.variables.length
    ? `Detected variables: ${data.variables.join(", ")}`
    : "No {{variables}} detected yet.";
  draftDirty = draft.subject !== $("subjectInput").value || draft.html !== getDraftHtml();
  $("editorStatus").textContent = draftDirty ? "Unsaved changes" : "Saved";
}

onAction("saveDraftBtn", () => saveCurrentDraft());

onAction("previewEmailBtn", async () => {
  const idx = $("previewRowSelect").value;
  const row = state.generatedRows[idx];
  if (!row) return alert("Load recipients first (Step 2)");
  await saveCurrentDraft();
  const res = await apiFetch(`${API}/projects/${state.projectId}/email-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(row),
  });
  const data = await res.json();
  $("previewSubject").textContent = data.subject;
  $("previewFrame").srcdoc = data.html;
});

// ---------- Step 4: Gmail connect & send ----------
onAction("connectGmailBtn", async () => {
  const email = $("gmailAddressInput").value.trim();
  const app_password = $("gmailAppPasswordInput").value.trim();
  if (!email || !app_password) return alert("Enter your Gmail address and App Password");
  $("gmailStatus").textContent = "Connecting…";
  try {
    const res = await apiFetch(`${API}/gmail/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, app_password }),
    });
    const data = await res.json();
    if (res.ok && data.connected) {
      $("gmailStatus").textContent = `Connected as ${data.email}`;
      $("gmailAppPasswordInput").value = "";
    } else {
      $("gmailStatus").textContent = `Connection failed: ${data.detail || "unknown error"}`;
    }
  } catch (e) {
    $("gmailStatus").textContent = `Connection failed: ${e}`;
  }
});

onAction("disconnectGmailBtn", async () => {
  if (!confirm("Forget the saved Gmail credentials on this machine?")) return;
  await apiFetch(`${API}/gmail/disconnect`, { method: "POST" });
  await refreshGmailStatus();
});

async function refreshGmailStatus() {
  const res = await apiFetch(`${API}/gmail/status`);
  const data = await res.json();
  $("gmailStatus").textContent = data.connected ? `Connected as ${data.email}` : "Not connected";
}
initializeAuthentication();

onAction("sendTestBtn", async () => {
  const idx = $("testRowSelect").value;
  const row = state.generatedRows[idx];
  const to = $("testToInput").value.trim();
  if (!row || !to) return alert("Pick a recipient row and enter a test address");
  await saveCurrentDraft(true);
  const res = await apiFetch(`${API}/projects/${state.projectId}/send-test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to, row }),
  });
  const data = await res.json();
  alert(res.ok ? "Test email sent!" : `Failed: ${data.detail || "unknown error"}`);
});

onAction("sendAllBtn", async () => {
  if (!state.generatedRows.length) return alert("Load recipients first (Step 2)");
  if (!confirm(`Send to all ${state.generatedRows.length} recipients now?`)) return;
  await saveCurrentDraft(true);
  $("sendAllStatus").textContent = "Sending… this can take a while.";
  const res = await apiFetch(`${API}/projects/${state.projectId}/send-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows: state.generatedRows, force: false }),
  });
  const data = await res.json();
  $("sendAllStatus").textContent = `Sent: ${data.sent}/${state.generatedRows.length}`;
  renderSendResults(data.results);
});

function renderSendResults(results) {
  const tbody = $("sendResultsBody");
  tbody.innerHTML = "";
  (results || []).forEach((r) => {
    const tr = document.createElement("tr");
    [r.email, r.status].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      tr.appendChild(cell);
    });
    tbody.appendChild(tr);
  });
}

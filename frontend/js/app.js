const API = "/api";
const state = {
  projectId: null,
  mode: null,
  canvas: null,
  bgScale: 1,
  fields: [],
  generatedRows: [],
};

function $(id) {
  return document.getElementById(id);
}

// ---------- Step navigation ----------
document.querySelectorAll(".steps button").forEach((btn) => {
  btn.addEventListener("click", () => showStep(btn.dataset.step));
});

function showStep(n) {
  document.querySelectorAll(".step").forEach((s) => s.classList.remove("active"));
  document.querySelectorAll(".steps button").forEach((b) => b.classList.remove("active"));
  $(`step-${n}`).classList.add("active");
  document.querySelector(`.steps button[data-step="${n}"]`).classList.add("active");
}

// ---------- Step 0: choose mode & create project ----------
document.querySelectorAll(".mode-card").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const name = $("projectNameInput").value.trim();
    if (!name) return alert("Enter a project name first");
    const mode = btn.dataset.mode;
    const form = new FormData();
    form.append("name", name);
    form.append("mode", mode);
    const res = await fetch(`${API}/projects`, { method: "POST", body: form });
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
$("uploadBgBtn").addEventListener("click", async () => {
  if (!state.projectId) return alert("Create a project first");
  const file = $("bgFileInput").files[0];
  if (!file) return alert("Choose an image file");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/projects/${state.projectId}/background`, { method: "POST", body: form });
  const project = await res.json();
  loadCanvasBackground(`${API}/projects/${state.projectId}/asset/${project.background}?t=${Date.now()}`);
  $("designerRow").style.display = "flex";
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
      const maxWidth = 800;
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
  $("fontSizeInput").value = Math.round(obj.fontSize);
  $("fontColorInput").value = obj.fill;
  $("boldInput").checked = !!obj.data?.bold;
  $("italicInput").checked = !!obj.data?.italic;
  $("fontFamilySelect").value = obj.data?.font || "arial.ttf";
}

$("addFieldBtn").addEventListener("click", () => {
  if (!state.canvas) return alert("Upload a background image first");
  const name = prompt("Variable name (e.g. Name, Role, Date):");
  if (!name) return;
  const text = new fabric.Textbox(name, {
    left: state.canvas.getWidth() / 2,
    top: state.canvas.getHeight() / 2,
    fontSize: 28,
    fill: "#000000",
    fontFamily: "Arial",
    originX: "center",
    originY: "center",
    textAlign: "center",
  });
  text.data = { name, font: "arial.ttf", bold: false, italic: false };
  state.canvas.add(text);
  state.canvas.setActiveObject(text);
  updatePropsPanel();
});

["fontSizeInput", "fontColorInput", "boldInput", "italicInput", "fontFamilySelect"].forEach((id) => {
  $(id).addEventListener("input", () => {
    const obj = state.canvas?.getActiveObject();
    if (!obj) return;
    obj.set({
      fontSize: parseInt($("fontSizeInput").value, 10) || obj.fontSize,
      fill: $("fontColorInput").value,
      fontWeight: $("boldInput").checked ? "bold" : "normal",
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

$("uploadFontBtn").addEventListener("click", async () => {
  const file = $("fontFileInput").files[0];
  if (!file || !state.projectId) return alert("Create a project and choose a .ttf file first");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/projects/${state.projectId}/fonts`, { method: "POST", body: form });
  const data = await res.json();
  const opt = document.createElement("option");
  opt.value = data.filename;
  opt.textContent = `${data.filename} (custom)`;
  $("fontFamilySelect").appendChild(opt);
});

$("saveFieldsBtn").addEventListener("click", async () => {
  if (!state.canvas) return;
  const fields = state.canvas.getObjects("textbox").map((obj) => ({
    name: obj.data.name,
    x: Math.round(obj.left / state.bgScale),
    y: Math.round(obj.top / state.bgScale),
    font_size: Math.round(obj.fontSize / state.bgScale),
    color: obj.fill,
    font: obj.data.font,
    bold: obj.data.bold,
    italic: obj.data.italic,
    anchor: "mm",
  }));
  const res = await fetch(`${API}/projects/${state.projectId}/fields`, {
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

$("generateBtn").addEventListener("click", async () => {
  const file = $("excelFileInput").files[0];
  if (!file || !state.projectId) return alert("Choose the filled Excel file");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/projects/${state.projectId}/generate`, { method: "POST", body: form });
  const data = await res.json();
  state.generatedRows = data.rows;
  renderGeneratedTable(data.rows);
  populateRowSelects(data.rows);
});

function renderGeneratedTable(rows) {
  const tbody = $("generatedTableBody");
  tbody.innerHTML = "";
  rows.forEach((row) => {
    const certCell = row._certificate_file
      ? `<a href="${API}/projects/${state.projectId}/generated/${row._certificate_file}" target="_blank">Download</a>`
      : "—";
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${row.Name || ""}</td><td>${row.Email || ""}</td><td>${certCell}</td>`;
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

$("copyPromptBtn").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("aiPromptOutput").value);
  alert("Prompt copied! Paste it into ChatGPT or Gemini, then paste the HTML it gives back into the box below.");
});

$("uploadEmailImageBtn").addEventListener("click", async () => {
  if (!state.projectId) return alert("Create a project first");
  const file = $("emailImageInput").files[0];
  if (!file) return alert("Choose an image");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/projects/${state.projectId}/email-images`, { method: "POST", body: form });
  const data = await res.json();
  const tag = `<img src="cid:${data.cid}" alt="" style="max-width:100%;display:block;margin:12px 0;" />`;
  insertAtCursor($("htmlTextarea"), tag);
});

$("insertLinkedInBtn").addEventListener("click", () => {
  const snippet = `\n<table role="presentation" cellpadding="0" cellspacing="0"><tr><td align="center" style="background-color:#0a66c2;border-radius:6px;">\n<a href="{{LinkedIn_Share_Link}}" target="_blank" style="display:inline-block;padding:12px 24px;color:#ffffff;font-weight:bold;font-size:14px;text-decoration:none;">\ud83d\udc49 Share on LinkedIn</a>\n</td></tr></table>\n`;
  insertAtCursor($("htmlTextarea"), snippet);
  alert(
    "Inserted. This links to a {{LinkedIn_Share_Link}} column you provide in your Excel sheet " +
      "(pre-fills a LinkedIn post with your caption). Note: LinkedIn does not support auto-attaching " +
      "the certificate file via a link — the recipient will need to attach it manually on both desktop and mobile."
  );
});

$("saveDraftBtn").addEventListener("click", async () => {
  if (!state.projectId) return alert("Create a project first");
  const draft = { subject: $("subjectInput").value, html: $("htmlTextarea").value };
  const res = await fetch(`${API}/projects/${state.projectId}/email-draft`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  const data = await res.json();
  $("detectedVariables").textContent = data.variables.length
    ? `Detected variables: ${data.variables.join(", ")}`
    : "No {{variables}} detected yet.";
});

$("previewEmailBtn").addEventListener("click", async () => {
  const idx = $("previewRowSelect").value;
  const row = state.generatedRows[idx];
  if (!row) return alert("Load recipients first (Step 2)");
  const res = await fetch(`${API}/projects/${state.projectId}/email-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(row),
  });
  const data = await res.json();
  $("previewSubject").textContent = data.subject;
  $("previewFrame").srcdoc = data.html;
});

// ---------- Step 4: Gmail connect & send ----------
$("connectGmailBtn").addEventListener("click", async () => {
  const email = $("gmailAddressInput").value.trim();
  const app_password = $("gmailAppPasswordInput").value.trim();
  if (!email || !app_password) return alert("Enter your Gmail address and App Password");
  $("gmailStatus").textContent = "Connecting…";
  try {
    const res = await fetch(`${API}/gmail/connect`, {
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

$("disconnectGmailBtn").addEventListener("click", async () => {
  if (!confirm("Forget the saved Gmail credentials on this machine?")) return;
  await fetch(`${API}/gmail/disconnect`, { method: "POST" });
  refreshGmailStatus();
});

async function refreshGmailStatus() {
  const res = await fetch(`${API}/gmail/status`);
  const data = await res.json();
  $("gmailStatus").textContent = data.connected ? `Connected as ${data.email}` : "Not connected";
}
refreshGmailStatus();

$("sendTestBtn").addEventListener("click", async () => {
  const idx = $("testRowSelect").value;
  const row = state.generatedRows[idx];
  const to = $("testToInput").value.trim();
  if (!row || !to) return alert("Pick a recipient row and enter a test address");
  const res = await fetch(`${API}/projects/${state.projectId}/send-test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to, row }),
  });
  const data = await res.json();
  alert(res.ok ? "Test email sent!" : `Failed: ${data.detail || "unknown error"}`);
});

$("sendAllBtn").addEventListener("click", async () => {
  if (!state.generatedRows.length) return alert("Load recipients first (Step 2)");
  if (!confirm(`Send to all ${state.generatedRows.length} recipients now?`)) return;
  $("sendAllStatus").textContent = "Sending… this can take a while.";
  const res = await fetch(`${API}/projects/${state.projectId}/send-all`, {
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
    tr.innerHTML = `<td>${r.email}</td><td>${r.status}</td>`;
    tbody.appendChild(tr);
  });
}

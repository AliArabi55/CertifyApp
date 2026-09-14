# Certify

Design certificates and send personalized emails in one place.

A local web app for clubs, teams, and event organizers. Design a certificate, upload your participants from Excel, and send each person a personalized email with their certificate through Gmail. You can also send emails without certificates.

![Home screen and project modes](docs/images/home.png)

## At a Glance

| Feature | What you can do |
| --- | --- |
| Certificate designer | Upload your background, drag text fields into place, and customize fonts, sizes, and colors. |
| Bulk generation | Create a separate PDF certificate for each participant in your Excel sheet. |
| Personalized emails | Use placeholders such as `{{Name}}` and preview the message for each recipient. |
| Rich content | Add inline images, a LinkedIn share button, or build a writing prompt for ChatGPT or Gemini. |
| Gmail sending | Connect your account with an App Password, without Google Cloud or OAuth setup. |
| Test before sending | Send a test first; the send log skips recipients already marked as sent when you retry. |

## Quick Start

You need **Python 3.10 or later**. Open PowerShell in the project folder and run these commands. Creating the environment and installing dependencies are only needed the first time:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8080
```

Open **[http://localhost:8080](http://localhost:8080)**. Keep the terminal open while using the app. Press `Ctrl+C` to stop the server.

In VS Code, you can also choose **Terminal > Run Task > Run Certify (8080)** after installing dependencies. If the port is busy, stop your previous app instance or replace `8080` in the command with an available port and open the matching URL.

## Use It in 5 Steps

1. **Create a project:** Enter a name and choose **Design & send certificates** or **Send emails only**.
2. **Design your certificate:** Upload a background, add fields such as `Name`, and click **Save fields**. Skip this step in emails-only mode.
3. **Prepare your message and data:** In **Email**, write your subject and HTML body with placeholders, then save the draft. Return to **Recipients**, download the Excel template, fill in one row per person including `Email`, and upload it to generate certificates or load recipients. Defining placeholders before downloading the template ensures their columns are included.
4. **Check the preview:** Open **Email**, choose a recipient, and click **Preview for this recipient** to check the personalized content.
5. **Test and send:** Connect Gmail in **Send**, send a test to yourself, and review it before clicking **Send to all recipients**.

![Email editor and writing prompt helper](docs/images/email.png)

## Gmail and Privacy

- Enable [2-Step Verification](https://myaccount.google.com/security), then create an [App Password](https://myaccount.google.com/apppasswords) and enter it in the app with your Gmail address. Do not use your regular account password. Some account policies may prevent creating App Passwords.
- Project data and certificates are stored locally in `backend/projects/`. Gmail credentials are saved in plain text in `config/.env`; never share or commit this file. Use **Forget credentials** to remove them locally.
- The app connects to external services to send email and load a frontend library. If you use ChatGPT or Gemini, do not paste recipient data or passwords into your prompts.
- Sending is subject to Gmail limits and account policies. The LinkedIn button does not upload a certificate automatically; recipients attach it themselves.

<details>
<summary>Detailed reference and additional features</summary>

## Certificate & Mail-Merge Web App

A local, self-hosted, **plug & play** web app to:
1. (Optional) Design a certificate (drag-and-drop text fields onto your own background image),
2. Bulk-generate certificates from an Excel sheet, and
3. Send personalized emails (with `{{Variable}}` placeholders) from **your own Gmail account**, with the matching certificate auto-attached.

Runs locally without cloud hosting, a Google Cloud project, or OAuth setup. Sending email uses Gmail, and the frontend loads a library from a public CDN.

> This repo is generic/reusable for any club or organization (built with GitHub Campus Experts in mind). It ships with no hardcoded branding — everything (the certificate design, the variables, the email copy) is defined by you inside the app.

## Features
- **Two modes** — pick "Design & send certificates" for the full flow, or "Send emails only" to skip certificates entirely and just mail-merge a recipient list.
- **Certificate designer** — upload a background image, drag text fields onto it, set font/size/color/bold/italic per field, upload custom `.ttf` fonts.
- **Auto-generated Excel template** — download a blank sheet with exactly the columns you need (your certificate fields + any `{{Variable}}` used in your email + `Email`).
- **Bulk certificate generation** — upload the filled sheet, get one PDF per recipient.
- **Email composer** — write your subject/HTML with `{{Name}}`, `{{Role}}`, etc.; variables are auto-detected; per-recipient live preview.
  - **AI drafting helper** — tick a few checkboxes (bold formatting, image spot, LinkedIn button, certificate mention), describe the email in one line, and get a ready-to-paste prompt for ChatGPT/Gemini that writes the HTML for you.
  - **Insert images** — upload an image and it's embedded inline (via CID, not a flaky `data:` URI) and shown correctly in both the preview and the real email.
  - **Insert a LinkedIn share button** — one click adds a styled button linking to a `{{LinkedIn_Share_Link}}` column you provide. Note: LinkedIn's link parameters don't support auto-attaching a file, so the recipient still has to attach their certificate manually on LinkedIn — this is a platform limitation, not something this app can work around.
- **Your own Gmail, via an App Password** — no Google Cloud project, no OAuth consent screens, no verification wait times. Enter your Gmail address + a 16-character App Password once; it's saved locally in `config/.env`.
- **Safe send flow** — mandatory test send first, then send-to-all with a resumable log (re-running skips anyone already marked "sent").

## Prerequisites
- Python 3.10+
- A Gmail account with 2-Step Verification enabled (needed to generate an App Password — see below)

## Installation
```powershell
git clone <this-repo-url> CertifyApp
cd CertifyApp
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## One-time: get a Gmail App Password (3 steps, ~1 minute)
This app sends email over SMTP using an **App Password** — a 16-character code Google generates for you, completely separate from your real password. No Google Cloud project, no API enablement, no consent screen.

1. Turn on **2-Step Verification** on your Google account, if it isn't already: https://myaccount.google.com/security
2. Go to https://myaccount.google.com/apppasswords, enter a name for it (e.g. "Certify"), and click **Create**.
3. Copy the 16-character password Google shows you (spaces don't matter) — paste it into the app's **Connect Gmail** step along with your Gmail address. It's saved locally to `config/.env` so you won't need to re-enter it next time.

## Running the app
```powershell
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```
Open http://localhost:8080 in your browser. From VS Code, you can also run the **Run Certify (8080)** task after installing dependencies in `venv`.

## Usage walkthrough
1. **Choose a mode** — name your project, then pick "Design & send certificates" or "Send emails only".
2. **Design** *(certificates mode only)* — upload your certificate background image, click "+ Add variable field" for each piece of text you want personalized (e.g. `Name`, `Role`), drag it into position, and adjust font/size/color/bold/italic in the side panel. Click **Save fields**.
3. **Recipients** — click **Download Excel template** (columns match your fields + any email variables + `Email`), fill in one row per recipient, then upload it and click **Generate certificates** (or **Load recipients** in emails-only mode).
4. **Email** — write your subject and HTML body using `{{Name}}`-style placeholders, or use the AI prompt helper to get a draft from ChatGPT/Gemini. Insert images or a LinkedIn button with one click. Save the draft, then preview it for any recipient.
5. **Send** — enter your Gmail address + App Password and click **Connect Gmail** (first time only), send a **test** to yourself, check it, then **Send to all recipients**. The send log lets you safely re-run the app later — already-sent recipients are skipped.

## Data storage
Everything for a project lives under `backend/projects/<project_id>/`: the background image, `project.json` (fields + email draft), uploaded fonts, uploaded email images, generated certificates, and the send log. This folder is gitignored — it's your data, not source code.

## Gmail sending limits
Gmail enforces daily sending caps: ~500 emails/day for a personal `@gmail.com` account, ~2,000/day for Google Workspace accounts. The app waits a couple of seconds between sends to stay well under rate limits, but very large recipient lists may need to be split across days.

## Security notes
- `config/.env` contains your Gmail address and App Password in plain text — never commit or share it (already gitignored). Treat the App Password as a sensitive account credential; you can revoke it anytime from https://myaccount.google.com/apppasswords without changing your real password. Use **Forget credentials** in the app to delete it locally.
- Treat this like any locally-saved credential: don't run the app on a shared/public machine, and revoke the App Password if the machine is ever compromised.

## Roadmap / ideas not yet implemented
- Plain-text alternative part alongside the HTML email (better deliverability).
- A send-log/history dashboard across projects.
- Multiple certificate templates per project.
- CSV import alongside Excel.
- "Re-run this campaign" export/reuse of a saved project for future events.

</details>


# Gmail API Setup Instructions

## Files You Need

You'll receive **2 files** via Slack:

| File | Description |
|------|-------------|
| `token.json` | Access token for the project Gmail account |
| `oauth_credentials.json` | OAuth app credentials |

---

## Where to Place the Files

Place the files in the project like this:

```
OSiri_Mac_Assistant/
├── token.json                          ← PUT HERE (project root)
├── maf_agent/
│   └── oauth_credentials.json          ← PUT HERE
└── test_gmail.py
```

---

## How to Run

### 1. Activate the virtual environment

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

### 2. Install dependencies (if needed)

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```
### 3. Run the server :
python -m maf.maf_a2a.maf_a2a_server

### 4. Run the test script

```bash
python test_gmail.py
```

---

## Expected Output

If everything is set up correctly, you should see:

```
[INBOX] Reading last 5 emails...
   - From: ...
     Subject: ...
     Snippet: ...
----------------------------------------
...

[SEND] Sending test email to ...
[OK] Email sent! Message Id: ...
```

---

## Troubleshooting

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'google_auth_oauthlib'` | Activate venv and run `pip install` command above |
| `FileNotFoundError: token.json` | Make sure `token.json` is in the project root folder |
| `FileNotFoundError: credentials.json` | Make sure `oauth_credentials.json` is in `maf_agent/` folder |

---

## Notes

- The `token.json` gives access to the **shared project Gmail account**
- Do not share these files publicly
- If the token expires, you may need to get a fresh `token.json` from the project owner


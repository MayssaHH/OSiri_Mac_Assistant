# 🍎 OSiri UI

A beautiful Mac-native styled chat interface for OSiri Assistant.

![UI Preview](https://img.shields.io/badge/style-Mac%20Native-007AFF?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.11+-blue?style=for-the-badge)
![Gradio](https://img.shields.io/badge/gradio-4.0+-orange?style=for-the-badge)

## 🚀 Quick Start

### Option 1: Web Browser (Recommended for Testing)

```bash
# From the project root
cd ui

# Install dependencies
pip install -r requirements.txt

# Run the web UI
python app.py
```

Then open http://localhost:7860 in your browser.

### Option 2: Desktop App (Codex-like)

```bash
# From the project root
cd ui

# Install dependencies (includes pywebview)
pip install -r requirements.txt

# Run as floating desktop window
python desktop.py
```

This opens a native Mac window that's always on top - just like Codex!

### Option 3: Docker (For Demos)

```bash
# From the project root

# Run just the UI (connects to external orchestrator)
docker-compose up ui

# Or run the full stack
docker-compose up
```

Then open http://localhost:7860 in your browser.

---

## 📁 Files

| File | Description |
|------|-------------|
| `app.py` | Main Gradio web interface |
| `desktop.py` | PyWebView wrapper for desktop experience |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Docker image for containerized deployment |

---

## 🎨 Features

- **Mac-native styling** - Inspired by macOS Sonoma
- **Real-time chat** - Async communication with orchestrator
- **Approval flow** - Handles terminal safety approvals
- **Example prompts** - Quick-start suggestions
- **Always-on-top** - Desktop mode stays visible (Codex-like)

---

## ⚙️ Configuration

Set these environment variables (or in `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `A2A_BASE_URL` | `http://127.0.0.1:9997/` | Orchestrator URL |
| `OPENAI_API_KEY` | - | Required for LLM calls |

---

## 🔧 Development

### Running with Hot Reload

```bash
gradio app.py
```

### Customizing the Theme

Edit the `MAC_CSS` variable in `app.py` to customize:
- Colors (`--mac-accent`, `--mac-bg-primary`, etc.)
- Fonts
- Border radius
- Shadows

---

## 🐳 Docker - Full Stack

### Quick Start (Recommended)

```bash
# From project root
cd /path/to/OSiri_Mac_Assistant

# 1. Make sure your .env file has OPENAI_API_KEY set
#    (Copy env.example to .env if needed)

# 2. Build and run everything
docker-compose up --build

# 3. Open http://localhost:7860 in your browser
```

### What Gets Started

| Service | Port | Description |
|---------|------|-------------|
| **UI** | 7860 | Gradio chat interface |
| **Orchestrator** | 9997 | Routes tasks to agents |
| **Terminal Agent** | 9998 | File/system operations |
| **Web Agent** | 9999 | Web search |

### Build Individual Images

```bash
docker build -f ui/Dockerfile -t osiri-ui .
docker build -f orchestrator/Dockerfile -t osiri-orchestrator .
docker build -f terminal/Dockerfile -t osiri-terminal .
docker build -f web/Dockerfile -t osiri-web .
```

---

## 🛠 Troubleshooting

### "Connection refused" error

Make sure the orchestrator is running:
```bash
# In terminal 1 - start orchestrator
cd orchestrator && python orchestrator_a2a_server.py

# In terminal 2 - start terminal agent  
cd terminal/terminal_a2a && python terminal_a2a_server.py

# In terminal 3 - start web agent
cd web/web_a2a && python -m web_a2a.web_a2a_server

# In terminal 4 - start UI
cd ui && python app.py
```

### PyWebView not working

On macOS, you might need:
```bash
pip install pyobjc-framework-WebKit
```

### Gradio version issues

Make sure you have Gradio 4.0+:
```bash
pip install --upgrade gradio
```


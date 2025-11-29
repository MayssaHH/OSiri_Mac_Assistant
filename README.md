# 🍎 OSiri Mac Assistant

> *Your intelligent multi-agent Mac assistant powered by AI*

OSiri is a sophisticated multi-agent system that brings Siri-like capabilities to your Mac through natural language. It orchestrates specialized agents to handle terminal commands, web searches, email, Slack messaging, and more.

---

## 🎯 Features

| Agent | Tagline | Capabilities |
|-------|---------|--------------|
| **🧠 Orchestrator** | *The brain that plans, delegates, and synthesizes across all agents.* | Task planning, agent coordination, result synthesis |
| **💻 Terminal** | *Your command-line companion for file and system operations.* | File management, shell commands, safe execution with rollback |
| **🌐 Web** | *Search, scrape, and browse the web on your behalf.* | Web search (Tavily), URL scraping, browser history access |
| **📱 App (MAF)** | *Seamless communication across Slack and Gmail.* | Send/read Slack messages, send/read Gmail emails |
| **🎨 UI** | *Your conversational gateway to OSiri's multi-agent system.* | Beautiful chat interface, voice input, approval workflows |

---

## 🚀 Two Ways to Run OSiri

### Option 1: 🌐 Web Interface (Docker)

The web interface runs entirely in Docker and is accessible via your browser.

```bash
# 1. Clone and setup
git clone <repository>
cd OSiri_Mac_Assistant

# 2. Configure environment
cp env.example .env
# Edit .env with your API keys (see Configuration section)

# 3. Start all services
docker-compose up --build

# 4. Open in browser
open http://localhost:7860
```

### Option 2: 🖥️ Desktop App (Native macOS)

A beautiful Siri-style floating command bar that stays on top of your screen.

```bash
# 1. First, start the backend services
docker-compose up -d

# 2. Install desktop app dependencies
cd ui
pip install pywebview

# 3. Run the desktop app
python desktop.py
```

The desktop app provides:
- 🎯 Frameless floating window
- 🔝 Always-on-top display
- 🖱️ Drag anywhere to reposition
- 🎤 Voice input support
- 🌈 Transparent Siri-inspired design

---

## ⚙️ Configuration

### Required API Keys

Create a `.env` file in the project root:

```bash
# Required - OpenAI API Key
OPENAI_API_KEY=sk-your-openai-api-key-here

# Required for Web Search - Tavily API Key
TAVILY_API_KEY=tvly-your-tavily-api-key-here

# Required for Slack integration
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token

# Gmail is configured via OAuth (see Gmail Setup section)
```

### Getting API Keys

| Service | Get Key From | Notes |
|---------|--------------|-------|
| OpenAI | https://platform.openai.com/api-keys | Required for all agents |
| Tavily | https://tavily.com/ | Free tier available, required for web search |
| Slack | https://api.slack.com/apps | Create a bot with required scopes |

---

## ⚠️ Important: VPN Required for Web Search

> **🔐 ProtonVPN is required for Tavily web search to work properly.**

The Tavily API may be blocked in certain regions or networks. To ensure web search functionality works:

1. **Install ProtonVPN**: https://protonvpn.com/
2. **Connect to a VPN server** before starting OSiri
3. **Keep VPN connected** while using web search features

Without VPN, you may see `ForbiddenError` when using web search.

---

## 📧 Gmail Setup

Gmail integration uses OAuth2 for secure authentication:

1. **Create Google Cloud Project**
   - Go to https://console.cloud.google.com/
   - Create a new project
   - Enable the Gmail API

2. **Create OAuth Credentials**
   - Go to APIs & Services → Credentials
   - Create OAuth 2.0 Client ID (Desktop app)
   - Download as `credentials.json`

3. **Place credentials and authenticate**
   ```bash
   # Place credentials in the correct location
   cp credentials.json app/maf_agent/credentials.json
   
   # Run authentication (opens browser)
   cd app && python test_gmail.py
   ```

4. **Token is saved** - `token.json` is created automatically and mounted into Docker

See `app/GMAIL_SETUP.md` for detailed instructions.

---

## 💬 Slack Setup

1. **Create Slack App** at https://api.slack.com/apps

2. **Add OAuth Scopes** under OAuth & Permissions:
   - `chat:write` - Send messages
   - `channels:read` - List channels
   - `channels:history` - Read channel messages
   - `groups:read` - List private channels
   - `groups:history` - Read private channel messages

3. **Install to Workspace** and copy the Bot User OAuth Token

4. **Invite bot to channels**: `/invite @YourBotName` in each channel

5. **Add token to `.env`**:
   ```bash
   SLACK_BOT_TOKEN=xoxb-your-token-here
   ```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                        │
│              (Web UI :7860 / Desktop App)                   │
└─────────────────────────┬───────────────────────────────────┘
                          │ A2A Protocol
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator :9997                      │
│         "The brain that plans and coordinates"               │
│    ┌──────────┐  ┌──────────┐  ┌─────────────┐              │
│    │ Planner  │→ │ Executor │→ │ Synthesizer │              │
│    └──────────┘  └──────────┘  └─────────────┘              │
└────────┬─────────────────┬─────────────────┬────────────────┘
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  Terminal   │   │     Web     │   │     App     │
│    :9998    │   │    :9999    │   │    :9996    │
│             │   │             │   │             │
│ • Files     │   │ • Search    │   │ • Slack     │
│ • Shell     │   │ • Scrape    │   │ • Gmail     │
│ • System    │   │ • History   │   │             │
└─────────────┘   └─────────────┘   └─────────────┘
```

### Communication Protocols

- **A2A (Agent-to-Agent)**: HTTP-based protocol for inter-agent communication
- **MCP (Model Context Protocol)**: Tool exposure within agents

---

## 📁 Project Structure

```
OSiri_Mac_Assistant/
├── docker-compose.yml      # Container orchestration
├── .env                    # API keys (create from env.example)
├── requirements.txt        # Python dependencies
│
├── ui/                     # User interfaces
│   ├── app.py             # Web UI (FastAPI)
│   ├── siri_ui.py         # Compact Siri-style UI
│   └── desktop.py         # Native macOS desktop app
│
├── orchestrator/           # Central coordinator
│   ├── planner.py         # Task planning
│   ├── synthesizer.py     # Result synthesis
│   └── prompt.py          # System prompts
│
├── terminal/               # Terminal agent
│   ├── terminal_mcp/      # MCP tools
│   └── terminal_a2a/      # A2A server
│
├── web/                    # Web agent
│   ├── web_mcp/           # MCP tools (search, scrape)
│   └── web_a2a/           # A2A server
│
├── app/                    # Communication agent
│   ├── maf/               # MAF implementation
│   │   ├── maf_mcp/       # Slack & Gmail tools
│   │   └── maf_a2a/       # A2A server
│   └── maf_agent/         # OAuth tokens
│
└── common/                 # Shared utilities
    └── checkpoint.py      # Rollback support
```

---

## 🎮 Usage Examples

### Terminal Operations
```
"Create a folder called projects on my Desktop"
"List all PDF files in my Downloads folder"
"Move the latest file from Downloads to Documents"
```

### Web Search & Browsing
```
"Search for the latest AI news"
"What GitHub repos did I visit today?"
"Summarize the article at https://example.com"
```

### Email & Slack
```
"Check my last 5 emails"
"Send a message to #general saying I'm online"
"Read the last email and summarize it to #team channel"
```

### Multi-Step Tasks
```
"Read my last email, summarize it, and save it to a file on my Desktop"
"Find the papers I read today and download the most recent one"
```

---

## 🔧 Troubleshooting

### Web search returns "ForbiddenError"
- **Solution**: Connect to ProtonVPN before using web search
- Verify `TAVILY_API_KEY` is set correctly in `.env`

### Gmail not working in Docker
- Ensure `token.json` exists in `app/maf_agent/`
- Run `python test_gmail.py` locally first to authenticate
- Check that files are not directories: `ls -la app/maf_agent/`

### Slack "channel_not_found" error
- Invite the bot to the channel: `/invite @YourBotName`
- Verify bot has required OAuth scopes
- Check channel name spelling (with or without #)

### Terminal commands timeout
- Some commands with special characters may fail
- Try simpler file names without spaces or special characters

### Desktop app won't start
- Ensure Docker services are running: `docker-compose up -d`
- Install pywebview: `pip install pywebview`
- On macOS, grant accessibility permissions if prompted

---

## 🛠️ Development

### Running Individual Services

```bash
# Start specific service
docker-compose up terminal

# Rebuild and start
docker-compose up --build web

# View logs
docker-compose logs -f orchestrator
```

### Testing Agents Locally

```bash
# Test terminal agent
cd terminal && python -m terminal_a2a.test_terminal_a2a

# Test web agent
cd web && python test_web_a2a.py

# Test app agent
cd app && python test_gmail.py
cd app && python test_slack.py
```

---

## 🙏 Acknowledgments

- Built with [OpenAI GPT-4](https://openai.com/)
- Web search powered by [Tavily](https://tavily.com/)
- Agent framework used is Microsoft's Agent Framework (MAF)
- A2A protocol for agent communication

---

<p align="center">
  <strong>Made with ❤️ for Mac users who love AI</strong>
</p>


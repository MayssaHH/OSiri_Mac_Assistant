# OSiri Mac Assistant

An AI-powered assistant capable of managing emails via Gmail and interacting with Slack. This system is designed to be a helpful personal agent that can read/send emails and read/post to Slack channels using natural language commands.

## 🚀 Setup Guide

### Prerequisites
- Python 3.11+
- A Google Cloud Account (for Gmail)
- A Slack Workspace (for Slack integration)

### 1. Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd OSiri_Mac_Assistant
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Mac/Linux
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Create a `.env` file in the root directory:
   ```env
   OPENAI_API_KEY=sk-...
   SLACK_BOT_TOKEN=xoxb-...
   ```

---

## 📂 Project Structure & Architecture

This project is designed with modularity in mind, separating core agent logic, tools, and external interfaces.

```text
OSiri_Mac_Assistant/
├── maf_agent/                  # MAIN AGENT LOGIC
│   ├── core/
│   │   └── orchestrator.py     # The "Brain". Manages LLM context & tool execution.
│   ├── tools/
│   │   ├── email_ops.py        # Gmail API implementation (OAuth & Logic)
│   │   └── slack_ops.py        # Slack SDK implementation
│   ├── config.py               # Central configuration & environment validation
│   ├── main.py                 # Entry point for the CLI agent
│   └── oauth_credentials.json  # (Generated) Google OAuth secrets
│
├── maf_mcp/                    # MODEL CONTEXT PROTOCOL (MCP)
│   ├── email_server.py         # Standalone MCP server for Email
│   ├── maf_mcp_server.py       # Combined MCP server for Agent tools
│   └── maf_client.py           # Client to connect to MCP servers
│
├── agent_framework/            # REUSABLE AI UTILITIES
│   ├── openai.py               # Wrapper for OpenAI API interactions
│   └── __init__.py             # Decorators for defining AI functions
│
└── requirements.txt            # Python dependencies
```

### 🏗️ How It Works

#### 1. The Core Loop (`maf_agent/main.py` & `orchestrator.py`)
The system runs as a **ReAct (Reasoning + Acting) Loop**:
1.  **Initialization**: `main.py` loads environment variables and initializes the `Orchestrator`.
2.  **User Input**: The user types a command (e.g., "Check my emails and tell the team on Slack").
3.  **LLM Reasoning**: The `Orchestrator` sends the user prompt + system instructions + tool definitions to OpenAI (GPT-4o).
4.  **Tool Selection**: The LLM decides if it needs to call a tool (e.g., `read_email`).
5.  **Execution**: The code executes the chosen tool function in `maf_agent/tools/`.
6.  **Feedback**: The tool's output (e.g., list of emails) is fed back to the LLM.
7.  **Response**: The LLM generates a final natural language response or decides to call another tool (e.g., `send_slack`).

#### 2. Email System (`maf_agent/tools/email_ops.py`)
Unlike simple SMTP scripts, this uses the **Gmail API** with OAuth2 for secure access.
-   **Authentication**: It implements a full local web server flow. When you first run it, it opens a browser to get your permission.
-   **Token Management**: It saves your access/refresh tokens to `token.json`. On subsequent runs, it automatically refreshes expired tokens so you don't have to log in again.
-   **Operations**: Supports reading unread emails (filtering via Gmail labels) and sending rich text emails.

#### 3. Slack System (`maf_agent/tools/slack_ops.py`)
Uses the official `slack_sdk`.
-   **Channel Resolution**: Automatically converts channel names (e.g., `#general`) to Channel IDs (e.g., `C12345`) which the API requires. Caches these IDs for performance.
-   **Reading**: Fetches history from public/private channels the bot is invited to.
-   **Posting**: Sends formatted messages as the bot user.

#### 4. MCP (Model Context Protocol) Layer (`maf_mcp/`)
This folder contains an implementation of the **Model Context Protocol**, a standard for exposing tools to AI models.
-   **`email_server.py`**: A standalone server that exposes email tools. This allows *other* AI agents (like Claude Desktop or other MCP clients) to connect to and use your email tools without needing your full agent code.
-   **`maf_client.py`**: Demonstrates how to connect to these modular servers.

---

## 🔑 Google Gmail API Configuration (Detailed)

To allow the assistant to read and send emails, you need to generate `oauth_credentials.json`.

### Step A: Create Project & Enable API
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown (top left) and select **"New Project"**. Name it `OSiri-Assistant` and create it.
3. Select your new project.
4. In the search bar, type **"Gmail API"**, select it, and click **Enable**.

### Step B: Configure OAuth Consent Screen
1. Go to **APIs & Services > OAuth consent screen**.
2. Choose **External** (allows you to use your personal @gmail.com) and click **Create**.
3. **App Information**:
   - App name: `OSiri Assistant`
   - User support email: Select your email.
   - Developer contact info: Enter your email.
   - Click **Save and Continue**.
4. **Scopes**:
   - Click **Add or Remove Scopes**.
   - Filter for `Gmail API`.
   - Select the scope: `https://www.googleapis.com/auth/gmail.modify` (Read, compose, send, and permanently delete all your email).
   - Click **Update**, then **Save and Continue**.
5. **Test Users**:
   - Click **Add Users**.
   - Enter the exact Gmail address you want to control with this agent.
   - **Important:** Since the app is in "Testing" mode, ONLY email addresses added here will be able to authenticate.
   - Click **Save and Continue**.

### Step C: Create Credentials
1. Go to **APIs & Services > Credentials**.
2. Click **+ Create Credentials** > **OAuth client ID**.
3. **Application type**: Select **Web application** (Required for the specific redirect flow used in this code).
4. **Name**: `OSiri Client`.
5. **Authorized redirect URIs**:
   - Click **+ Add URI**.
   - Enter exactly: `http://localhost:4100/code`
   - *Note: The codebase explicitly listens on port 4100 for the callback.*
6. Click **Create**.

### Step D: Download & Place JSON
1. A popup will appear with your Client ID and Secret.
2. Click **Download JSON**.
3. Rename the downloaded file to `oauth_credentials.json`.
4. Move this file into the `maf_agent/` folder inside your project.
   - Final path: `maf_agent/oauth_credentials.json`.

---

## 💬 Slack App Configuration (Detailed)

To allow the assistant to read and post to Slack.

### Step A: Create the App
1. Go to [Slack API: Your Apps](https://api.slack.com/apps).
2. Click **Create New App**.
3. Select **From scratch**.
4. Name it `OSiri` and select your Workspace.

### Step B: Configure Scopes (Permissions)
1. In the left sidebar, click **OAuth & Permissions**.
2. Scroll down to **Scopes** > **Bot Token Scopes**.
3. Add the following scopes:
   - `chat:write` (Send messages)
   - `channels:history` (Read messages in public channels)
   - `channels:read` (List public channels to find IDs)
   - `groups:history` (Read messages in private channels)
   - `im:history` (Read Direct Messages)
   - `mpim:history` (Read Group DMs)

### Step C: Install & Get Token
1. Scroll up to **OAuth Tokens for Your Workspace**.
2. Click **Install to Workspace** and click **Allow**.
3. Copy the **Bot User OAuth Token** (it starts with `xoxb-`).
4. Paste this token into your `.env` file as `SLACK_BOT_TOKEN`.

### Step D: Invite the Bot
The bot cannot see messages in a channel unless it is a member.
1. Go to your Slack app.
2. Go to the channel you want the agent to use (e.g., `#general`).
3. Type `/invite @OSiri` (or whatever you named your bot).

---

## 🏃‍♂️ Usage

### First Run (Authentication)
1. Run the agent:
   ```bash
   python maf_agent/main.py
   ```
2. On the first run, it will detect `oauth_credentials.json` but no `token.json`.
3. It will automatically open your default web browser to a Google Sign-in page.
4. Sign in with the **Test User** email you configured.
5. You will see a "Google hasn't verified this app" warning (normal for personal apps). Click **Advanced** > **Go to OSiri Assistant (unsafe)**.
6. Click **Continue** to grant permissions.
7. You should be redirected to `http://localhost:4100/code` and see "Authentication successful!".
8. A `token.json` file will be created in `maf_agent/`. **Do not share this file.**

### Normal Usage
Once authenticated, the agent will use the saved `token.json` to access your email without opening the browser again.

```bash
python maf_agent/main.py
```

## ⚠️ Troubleshooting

**"Error 400: redirect_uri_mismatch"**
- Ensure you added `http://localhost:4100/code` to the Authorized Redirect URIs in Google Cloud Console.
- Ensure you downloaded the JSON *after* adding that URI.

**"Error 403: access_denied"**
- Ensure the email you are logging in with is added to the "Test Users" list in the OAuth Consent Screen.

**Slack "channel_not_found"**
- Ensure you have invited the bot to the channel using `/invite @BotName`.

# AI Email Assistant

## 1. Project Overview
A LangChain and LangGraph-based AI Email Assistant that securely interfaces with Gmail. It features user authentication, role-based tool access, and a progressive dual-stage Human-in-the-Loop (HITL) approval system. The application serves a Streamlit-based UI, providing a seamless chatting experience with real-time token streaming and interactive dialogs.

## 2. Key Features
- **User Authentication:** Login system checking against `users.csv`.
- **Per-User Permissions:** Granular controls for reading, sending, and replying to emails.
- **Dynamic Tool Authorization:** Enforces per-user tool authorization based on the user's permissions via middleware.
- **Human-in-the-Loop (HITL):** A robust two-stage draft review and final AI review pipeline before sending emails.
- **Gmail Integration:** Fully authenticated read, search, send, and reply operations.
- **Web Search:** Integrated Tavily search for general queries.
- **Stateful Memory:** Persistent conversational context per user within the session using LangGraph's `InMemorySaver`.

## 3. Architecture / How the Agent Works
The system uses the LangGraph framework to orchestrate the AI operations:
- **Graph & State:** The agent operates on an `EmailState` that tracks permissions and contextual metadata (like `last_email_list`).
- **Context Injection:** The `EmailContext` securely passes user identity (ID, Name, Email) outside the mutable state.
- **ReAct Loop:** The `gpt-4o-mini` LLM uses tools iteratively. Tool results inform the subsequent steps.
- **Middleware:** `@wrap_model_call` dynamically injects context (like the user's real name for signatures) into the system prompt and verifies permissions.

## 4. Authentication and Per-User Permissions
Auth is handled by `auth.py`, which reads from `data/users.csv`. Users are granted access based on their User ID. The returned payload includes explicit boolean flags (`can_read_email`, `can_send_email`, `can_reply_email`). These flags are injected into the agent's state, preventing unauthorized operations at both the UI and tool-execution levels.

## 5. Gmail Integration and OAuth
`gmail.py` implements the core Google API connections. It requires OAuth 2.0 `credentials.json`. On the first run, it initiates a local server flow to securely generate a `token.json` for subsequent authenticated requests. It handles reading metadata, parsing email headers, threaded replies, and sending raw base64-encoded MIME messages.

## 6. Available Tools
- **`web_search`:** Powered by Tavily for general internet queries.
- **`list_emails`:** Retrieves the user's most recent inbox messages (default 5, max 50).
- **`search_gmail`:** Performs native Gmail queries to find specific threads.
- **`read_email`:** Retrieves full email contents by direct message ID or UI position reference (e.g., "Read email #2").
- **`send_email`:** Drafts and initiates the sending process for new emails.
- **`reply_email`:** Automatically determines recipients and drafts contextual replies within an existing thread.

## 7. Dynamic Tool Authorization
The agent employs LangGraph middleware (`dynamic_tool_authorization`) to enforce per-user tool authorization based on the user's permissions. When a tool is invoked, the middleware checks `runtime.state` against the required permissions. If a user lacks `can_send_email` but the LLM attempts a tool call, the middleware safely intercepts and denies the operation.

## 8. Human-in-the-Loop (HITL) Email Flow
To prevent unreviewed modifications from reaching the Gmail API, a strict two-stage process is enforced:
1. **Draft Review Phase:** The agent creates a draft and pauses the graph. The Streamlit UI surfaces a read-only dialog. The user can `[Continue]` (accept as-is) or `[Edit]` to make changes.
2. **Final AI Review:** Whether edited or unchanged, the text is returned to the LLM for a final review to ensure it remains professional and appropriate.
3. **Final Approval Phase:** The LLM pauses the graph a second time. The UI displays the *exact, AI-reviewed* final version. The user clicks `[Approve & Send]` or `[Reject]`. The email is ONLY sent if this final approval is granted.

## 9. Logging
The application actively records operations using Python's standard logging. Tool names, tool arguments, and tool completion events are written to `logs/agent.log`, along with other library and application logs that use Python logging, aiding in debugging and security auditing.

## 10. Project Structure
```text
email_assistant/
├── credentials/                 # [LOCAL, EXCLUDED FROM GIT]
│   ├── credentials.json        # Gmail OAuth credentials
│   └── token.json              # Generated OAuth token
├── data/
│   ├── users.csv               # [LOCAL, EXCLUDED FROM GIT] Actual user data
│   └── users.example.csv       # Safe example committed to the repository
├── logs/                       # [LOCAL, EXCLUDED FROM GIT]
│   └── agent.log               # Local execution logs
├── agent.py                    # LangGraph agent, tools, and HITL logic
├── app.py                      # Streamlit UI
├── auth.py                     # Authentication and permission handling
├── gmail.py                    # Gmail API integration
└── .env                        # [LOCAL, EXCLUDED FROM GIT] Environment variables
```

## 11. Installation / Setup
1. Create and activate a Python virtual environment.
2. Install the required dependencies (LangChain, LangGraph, Streamlit, Google API python client, pandas, bs4, tavily-python, langchain-openai, etc).
3. Create the `credentials/`, `data/`, and `logs/` directories.
4. Place your Google OAuth credentials inside `credentials/credentials.json`.

## 12. Required Environment Variables
Create a `.env` file in the root directory:
```env
OPENAI_API_KEY=your_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
```

## 13. Gmail Credentials Setup
1. Go to the Google Cloud Console.
2. Enable the Gmail API for your project.
3. Configure the OAuth Consent Screen.
4. Create an OAuth 2.0 Client ID (Desktop Application type).
5. Download the JSON and save it as `credentials/credentials.json`.
6. Run the application; the first auth attempt will pop up a browser window to generate `token.json`.

## 14. How to Run the Application
Start the Streamlit interface:
```bash
python -m streamlit run app.py
```
Or if using `uv`:
```bash
uv run python -m streamlit run app.py
```

## 15. Example Users and Permissions (`users.example.csv`)
Create a `data/users.csv` file structured like this:
```csv
user_id,name,email,can_read_email,can_send_email,can_reply_email
U001,John Doe,johndoe@example.com,True,True,True
U002,Jane Smith,janesmith@example.com,True,False,False
U003,Bob Admin,bob@example.com,True,True,False
```



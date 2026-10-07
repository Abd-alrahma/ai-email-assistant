from dotenv import load_dotenv
import logging
import os
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "agent.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)
load_dotenv()
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from dataclasses import dataclass
from typing import Callable

from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import (
    wrap_model_call,
    wrap_tool_call,
    ModelRequest,
    ModelResponse,
)
from langchain.messages import HumanMessage
from langchain_core.messages import ToolMessage
from langchain.tools import tool, ToolRuntime
from langchain_groq import ChatGroq
from tavily import TavilyClient
from typing import Dict, Any
from auth import authenticate_user

from gmail import (
    get_gmail_service,
    get_recent_emails,
    get_email,
    search_emails,
    send_email_action,
    reply_email_action,
)


# ============================================================
# CONTEXT
# ============================================================

@dataclass
class EmailContext:
    user_id: str
    email_address: str
    name: str = ""


# ============================================================
# STATE
# ============================================================

class EmailState(AgentState):
    authenticated: bool
    can_read_email: bool
    can_send_email: bool
    can_reply_email: bool
    last_email_list: list


# ============================================================
# TOOLS
# ============================================================

tavily_client = TavilyClient()

@tool
def web_search(query: str) -> Dict[str, Any]:
    """Search the web for information"""
    return tavily_client.search(query)


@tool
def list_emails(
    max_results: int = 5,
    runtime: ToolRuntime = None,
) -> str:
    """
    List the user's most recent Gmail emails.

    The user can specify how many emails to retrieve.
    Default is 5 and maximum is 50.
    """

    # --------------------------------------------------------
    # Permission check
    # --------------------------------------------------------

    if not runtime.state["can_read_email"]:
        return (
            "Permission denied: "
            "You do not have permission to read emails."
        )

    # --------------------------------------------------------
    # Validate number of emails
    # --------------------------------------------------------

    if max_results < 1:
        return "The number of emails must be at least 1."

    if max_results > 50:
        return (
            "You can request a maximum of "
            "50 emails at a time."
        )

    # --------------------------------------------------------
    # Retrieve emails
    # --------------------------------------------------------

    try:

        service = get_gmail_service()

        emails = get_recent_emails(
            service,
            max_results=max_results,
        )

        if not emails:
            return "No emails were found."

        # ----------------------------------------------------
        # Format email metadata
        # ----------------------------------------------------

        email_lines = []
        last_email_list = []

        for i, email in enumerate(
            emails,
            start=1,
        ):
            last_email_list.append({
                "position": i,
                "message_id": email["id"],
                "subject": email["subject"],
                "from": email["from"]
            })

            email_lines.append(
                f"Email #{i}\n"
                f"Message ID: {email['id']}\n"
                f"From: {email['from']}\n"
                f"To: {email['to']}\n"
                f"Subject: {email['subject']}\n"
                f"Date: {email['date']}"
            )

        output_str = "\n\n".join(email_lines)

        return Command(
            update={
                "last_email_list": last_email_list,
                "messages": [
                    ToolMessage(
                        content=output_str,
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except Exception as e:

        return (
            "Failed to retrieve emails "
            f"from Gmail: {e}"
        )


@tool
def search_gmail(
    query: str,
    max_results: int = 5,
    runtime: ToolRuntime = None,
) -> str:
    """
    Search the user's Gmail using a search query.
    
    The user can specify how many emails to retrieve.
    Default is 5 and maximum is 50.
    """

    if not runtime.state["can_read_email"]:
        return "Permission denied: You do not have permission to read emails."

    if max_results < 1:
        return "The number of emails must be at least 1."

    if max_results > 50:
        return "You can request a maximum of 50 emails at a time."

    try:
        service = get_gmail_service()
        emails = search_emails(
            service,
            query=query,
            max_results=max_results,
        )

        if not emails:
            return "No emails were found for the given search query."

        email_lines = []
        last_email_list = []

        for i, email in enumerate(emails, start=1):
            last_email_list.append({
                "position": i,
                "message_id": email["id"],
                "subject": email["subject"],
                "from": email["from"]
            })

            email_lines.append(
                f"Email #{i}\n"
                f"Message ID: {email['id']}\n"
                f"From: {email['from']}\n"
                f"To: {email['to']}\n"
                f"Subject: {email['subject']}\n"
                f"Date: {email['date']}"
            )

        output_str = "\n\n".join(email_lines)

        return Command(
            update={
                "last_email_list": last_email_list,
                "messages": [
                    ToolMessage(
                        content=output_str,
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except Exception as e:
        return f"Failed to search emails in Gmail: {e}"


@tool
def read_email(
    message_id: str,
    runtime: ToolRuntime = None,
) -> str:
    """
    Read the full content of a specific Gmail email.
    You can pass the exact Gmail message ID, OR you can pass the position number
    (as a string, e.g. "1", "2") if the user refers to an email from the recently listed emails.
    """

    # --------------------------------------------------------
    # Permission check
    # --------------------------------------------------------

    if not runtime.state["can_read_email"]:
        return (
            "Permission denied: "
            "You do not have permission to read emails."
        )

    # --------------------------------------------------------
    # Resolve numbered reference
    # --------------------------------------------------------
    
    idx_str = message_id.lstrip("#")
    if idx_str.isdigit():
        idx = int(idx_str)
        last_email_list = runtime.state.get("last_email_list", [])
        found = next((e for e in last_email_list if e["position"] == idx), None)
        if found:
            message_id = found["message_id"]
        elif last_email_list:
            return f"Could not find email #{idx} in the latest displayed list."
        else:
            return "No recent email list found to reference by number. Please ask to list emails first or provide a direct message ID."

    # --------------------------------------------------------
    # Retrieve email
    # --------------------------------------------------------

    try:

        service = get_gmail_service()

        email = get_email(
            service,
            message_id,
        )

        return (
            f"From: {email['from']}\n"
            f"To: {email['to']}\n"
            f"Subject: {email['subject']}\n"
            f"Date: {email['date']}\n\n"
            f"Body:\n{email['body']}"
        )

    except Exception as e:

        return (
            "Failed to retrieve the email "
            f"from Gmail: {e}"
        )


@tool
def send_email(
    to: str,
    subject: str,
    body: str,
    is_final_approval: bool = False,
    runtime: ToolRuntime = None,
) -> str:
    """Send an email."""

    # --------------------------------------------------------
    # Permission check
    # --------------------------------------------------------

    if not runtime.state["can_send_email"]:
        return (
            "Permission denied: "
            "You do not have permission to send emails."
        )

    # --------------------------------------------------------
    # Human in the Loop Approval
    # --------------------------------------------------------

    if not is_final_approval:
        # First Interrupt: Draft Review / Edit
        approval = interrupt({
            "action": "review_draft",
            "to": to,
            "subject": subject,
            "body": body
        })

        if isinstance(approval, dict) and approval.get("action") == "continue":
            edited_sub = approval.get("subject", subject)
            edited_body = approval.get("body", body)
            return (f"The user has reviewed and optionally edited the draft. "
                    f"FINAL SUBJECT: {edited_sub}\nFINAL BODY: {edited_body}\n"
                    f"Please review this final version for professionalism and correctness. "
                    f"If it is acceptable, call the send_email tool again with the exact final subject and body, and set is_final_approval=True.")
        else:
            return "The user rejected the email draft. Cancel the operation."
    else:
        # Second Interrupt: Final Approval
        approval = interrupt({
            "action": "final_approval",
            "to": to,
            "subject": subject,
            "body": body
        })

        if isinstance(approval, dict) and approval.get("action") == "approve":
            is_approved = True
        elif str(approval).strip().lower() in ["yes", "y", "approve", "approved", "true"]:
            is_approved = True
        else:
            is_approved = False

        if not is_approved:
            return "The user rejected the final email. Do NOT send the email. Cancel the operation."

    # --------------------------------------------------------
    # Send email
    # --------------------------------------------------------

    try:
        service = get_gmail_service()
        send_email_action(service, to, subject, body)
        return (
            f"Email sent successfully.\n"
            f"To: {to}\n"
            f"Subject: {subject}\n"
            f"Body: {body}"
        )
    except Exception as e:
        return f"Failed to send email: {e}"


@tool
def reply_email(
    message_id: str,
    body: str,
    is_final_approval: bool = False,
    runtime: ToolRuntime = None,
) -> str:
    """
    Reply to an email.
    The message_id can be a direct Gmail ID or a position number (e.g. "1", "2") from the recent list.
    """

    # --------------------------------------------------------
    # Permission check
    # --------------------------------------------------------

    if not runtime.state["can_reply_email"]:
        return (
            "Permission denied: "
            "You do not have permission to reply to emails."
        )

    # --------------------------------------------------------
    # Resolve message ID
    # --------------------------------------------------------

    actual_id = message_id

    idx_str = message_id.lstrip("#")
    if idx_str.isdigit():
        idx = int(idx_str)
        last_email_list = runtime.state.get("last_email_list", [])
        found = next((e for e in last_email_list if e["position"] == idx), None)
        if found:
            actual_id = found["message_id"]
        elif last_email_list:
            return f"Could not find email #{idx} in the latest displayed list."
        else:
            return "No recent email list found to reference by number. Please provide a direct message ID."

    # --------------------------------------------------------
    # Retrieve original email metadata
    # --------------------------------------------------------

    try:
        service = get_gmail_service()
        orig_email = get_email(service, actual_id)
    except Exception as e:
        return f"Failed to retrieve original email: {e}"

    # Determine recipient (To) and Subject
    reply_to = orig_email.get("from", "")
    if not reply_to:
        return "Could not determine the sender of the original email to reply to."

    orig_subject = orig_email.get("subject", "")
    reply_subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"
    
    thread_id = orig_email.get("threadId")
    msg_id_header = orig_email.get("message_id_header")
    references = orig_email.get("references", "")

    # --------------------------------------------------------
    # Human in the Loop Approval
    # --------------------------------------------------------

    if not is_final_approval:
        # First Interrupt: Draft Review / Edit
        approval = interrupt({
            "action": "review_reply_draft",
            "to": reply_to,
            "subject": reply_subject,
            "body": body
        })

        if isinstance(approval, dict) and approval.get("action") == "continue":
            edited_sub = approval.get("subject", reply_subject)
            edited_body = approval.get("body", body)
            return (f"The user has reviewed and optionally edited the reply draft. "
                    f"FINAL BODY: {edited_body}\n"
                    f"Please review this final version for professionalism and correctness. "
                    f"If it is acceptable, call the reply_email tool again with the exact final body, and set is_final_approval=True.")
        else:
            return "The user rejected the email reply draft. Cancel the operation."
    else:
        # Second Interrupt: Final Approval
        approval = interrupt({
            "action": "final_reply_approval",
            "to": reply_to,
            "subject": reply_subject,
            "body": body
        })

        if isinstance(approval, dict) and approval.get("action") == "approve":
            is_approved = True
        elif str(approval).strip().lower() in ["yes", "y", "approve", "approved", "true"]:
            is_approved = True
        else:
            is_approved = False

        if not is_approved:
            return "The user rejected the final email reply. Do NOT send the reply. Cancel the operation."

    # --------------------------------------------------------
    # Send reply
    # --------------------------------------------------------

    try:
        # get_gmail_service() again since interrupt might have paused for a while
        service = get_gmail_service()
        reply_email_action(
            service, 
            to=reply_to, 
            subject=reply_subject, 
            body=body, 
            thread_id=thread_id, 
            message_id_header=msg_id_header, 
            references=references
        )
        return (
            f"Reply sent successfully.\n"
            f"To: {reply_to}\n"
            f"Subject: {reply_subject}\n"
            f"Body: {body}"
        )
    except Exception as e:
        return f"Failed to send reply: {e}"


# ============================================================
# DYNAMIC TOOL AUTHORIZATION
# ============================================================

@wrap_model_call
def dynamic_tool_authorization(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:

    can_read_email = request.state["can_read_email"]
    can_send_email = request.state["can_send_email"]
    can_reply_email = request.state["can_reply_email"]

    # --------------------------------------------------------
    # Every authenticated user gets web search
    # --------------------------------------------------------

    tools = [
        web_search
    ]

    # --------------------------------------------------------
    # Gmail read permission
    # --------------------------------------------------------

    if can_read_email:
        tools.append(list_emails)
        tools.append(read_email)
        tools.append(search_gmail)

    # --------------------------------------------------------
    # Gmail send permission
    # --------------------------------------------------------

    if can_send_email:
        tools.append(send_email)

    # --------------------------------------------------------
    # Gmail reply permission
    # --------------------------------------------------------

    if can_reply_email:
        tools.append(reply_email)

    # --------------------------------------------------------
    # Make these tools available to the model
    # for this specific request, and inject the user's name.
    # --------------------------------------------------------

    # Get the static system message content
    sys_content = request.system_message.content if request.system_message else ""
    permission_info = f"""
    CURRENT USER PERMISSIONS:

    - Read emails: {"YES" if can_read_email else "NO"}
    - Search emails: {"YES" if can_read_email else "NO"}
    - Send emails: {"YES" if can_send_email else "NO"}
    - Reply to emails: {"YES" if can_reply_email else "NO"}
    - Web search: YES

    IMPORTANT:
     These are the actual permissions of the currently authenticated user.
    When asked about the user's permissions, use these values exactly.
     Never claim that the user has a permission when its value is NO.
    """

    sys_content += permission_info
    
    name = request.runtime.context.name if getattr(request.runtime, "context", None) and getattr(request.runtime.context, "name", None) else None
    
    if name:
        sys_content += f"\n\nIMPORTANT: The user's real name is '{name}'. You MUST use this exact name as the sender signature for any email or reply draft. DO NOT ask the user for their name."
    else:
        sys_content += f"\n\nIMPORTANT: The user's real name is currently UNKNOWN. You MUST ask the user for their name before creating and sending any final email or reply draft."

    from langchain.messages import SystemMessage

    request = request.override(
        tools=tools,
        system_message=SystemMessage(content=sys_content)
    )

    return handler(request)


# ============================================================
# MODEL
# ============================================================

#model = ChatGroq(
    model="openai/gpt-oss-120b"
#)


# ============================================================
# AGENT
# ============================================================
@wrap_tool_call
def log_tool_call(request, handler):
    tool_name = request.tool_call["name"]

    logger.info(f"Tool called: {tool_name}")
    logger.info(f"Arguments: {request.tool_call.get('args', {})}")

    result = handler(request)

    logger.info(f" Tool finished: {tool_name}")

    return result



checkpointer = InMemorySaver()
agent = create_agent(
    model="gpt-4o-mini",

    # Register every possible tool with the agent.
    # Middleware decides which tools the model can actually
    # use for the current user.
    tools=[
        web_search,
        list_emails,
        read_email,
        send_email,
        search_gmail,
        reply_email,
    ],

    state_schema=EmailState,
    context_schema=EmailContext,

    middleware=[
        dynamic_tool_authorization,
        log_tool_call,
    ],

    checkpointer=checkpointer,

    system_prompt="""
You are an email assistant.

You can help the user with general questions,
web searches, and email operations.

EMAIL RULES:

1. When the user asks to list or retrieve recent emails,
   check if the list_emails tool is available to you. If it is, use it. If not, explain that they don't have permission.

2. When the user asks to search or find specific emails (e.g., "Find emails from X", "Search for Y"),
   check if the search_gmail tool is available to you. If it is, use it. If not, explain that they don't have permission.

3. The user can specify how many emails they want.

4. If the user specifies a number,
   pass that number as max_results.

5. If the user does not specify a number,
   use max_results=5.

6. Never request more than 50 emails at once.

7. When the user asks to read the full content
   of a specific email, use the read_email tool.

8. The read_email tool accepts either the direct Gmail message ID, OR the position number (e.g. "1", "2") if referring to an email from the most recently listed or searched emails.
   If the user says "Read email #2" or "Read the second email", simply pass "2" as the message_id to the read_email tool.

9. Never invent or guess a Gmail message ID or position.

10. If the user asks to send an email, check if the send_email tool is available to you. If not, explain that they don't have permission.
    If it is available, first ask the user who should receive the email and what they want to say (their idea).
    Do NOT let the user provide a complete ready-made email. They must provide the idea, and you write the draft.
    Once they provide the idea, create a professional draft from it, review it for clarity, grammar, and tone (preserving the user's intended meaning), and THEN call the send_email tool with the generated draft (and is_final_approval=False).
    The send_email tool will then interrupt to ask the user. When the tool returns the final drafted text (which the user might have edited), you MUST review this final text.
    If it is acceptable, call the send_email tool a SECOND time with the exact same final subject and body, but with is_final_approval=True to proceed to final human approval.

11. If the user asks to reply to an email (e.g., "Reply to email #2"), check if the reply_email tool is available. If not, explain that they don't have permission.
    If available, first ask the user what they want to say in the reply (their idea). Do NOT let the user provide a complete ready-made email.
    Once they provide the idea, create a professional draft from it, review it, and THEN call the reply_email tool with the generated draft (and is_final_approval=False).
    The message_id passed to reply_email can be the number (e.g. "2") just like read_email.
    The reply_email tool will return the user's potentially edited text. You MUST review this final text.
    If acceptable, call reply_email a SECOND time with the exact final body, and with is_final_approval=True.

12. Never claim that an email was sent or replied to unless the respective tool actually confirms it.

13. Never invent or guess a Gmail message ID or position.

14. Never invent email contents or metadata.

15. Respect the user's permissions.

16. If a requested email operation is not available because of the user's permissions, clearly explain that the user does not have the required permission.

17. Do not claim that you accessed Gmail unless the corresponding Gmail tool was actually executed.

WEB SEARCH RULES:
18. For general web or internet questions (e.g. "What is the latest Python version?"), use the web_search tool.
19. Keep Gmail search and web search separate.
20. When drafting an email or reply, NEVER use placeholders like "[Your Name]", "<Name>", or similar for the signature.
    If the user's name is provided in the context, you MUST use that real name as the sender's signature, or do not include a signature at all if the user specifies.
    If the user's name is NOT provided in the context, you MUST ask the user for their name BEFORE creating and sending the final email draft. Never hardcode a made-up name.
"""
)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Authenticate user
    # --------------------------------------------------------

    user_id = input("Enter your User ID: ")

    user = authenticate_user(user_id)

    if user is None:
        print("\nAuthentication failed.")
        print("User ID not found.")
        raise SystemExit

    print(f"\nWelcome, {user['name']}!")

    # --------------------------------------------------------
    # Build context
    # --------------------------------------------------------

    context = EmailContext(
        user_id=user["user_id"],
        email_address=user["email"],
        name=user["name"],
    )

    # --------------------------------------------------------
    # Config for Memory
    # --------------------------------------------------------

    config = {
        "configurable": {
            "thread_id": f"user_{user['user_id']}"
        }
    }

    # --------------------------------------------------------
    # Chat loop
    # --------------------------------------------------------

    while True:

        # --------------------------------------------------------
        # Get user request
        # --------------------------------------------------------

        user_message = input("\nYou: ")

        if user_message.strip().lower() in ["exit", "quit"]:
            print("\nExiting chat. Goodbye!")
            break

        # --------------------------------------------------------
        # Build state
        # --------------------------------------------------------

        state_update = {
            "messages": [
                HumanMessage(
                    content=user_message
                )
            ],

            "authenticated": True,

            "can_read_email": user["can_read_email"],
            "can_send_email": user["can_send_email"],
            "can_reply_email": user["can_reply_email"],
        }

        response = agent.invoke(
            state_update,
            config=config,
            context=context,
        )

        state = agent.get_state(config)

        if state.tasks and state.tasks[0].interrupts:
            interrupt_val = state.tasks[0].interrupts[0].value
            if isinstance(interrupt_val, dict):
                action = interrupt_val.get("action")
                if action in ["send_email", "reply_email"]:
                    print("\nAssistant:")
                    print("Draft Email:")
                    print(f"To: {interrupt_val['to']}")
                    print(f"Subject: {interrupt_val['subject']}")
                    print(f"Body:\n{interrupt_val['body']}")

                    user_approval = input("\nDo you approve sending this email? (y/n): ")

                    response = agent.invoke(
                        Command(resume=user_approval),
                        config=config,
                        context=context,
                    )

        # --------------------------------------------------------
        # Display response
        # --------------------------------------------------------

        print("\nAssistant:")
        print(
            response["messages"][-1].content
        )
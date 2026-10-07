
import streamlit as st
from langchain.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.types import Command
from agent import agent, EmailContext
from auth import authenticate_user

# ============================================================
# PAGE CONFIG & CSS
# ============================================================

st.set_page_config(
    page_title="AI Email Assistant",
    page_icon="📧",
    layout="centered"
)

st.markdown("""
<style>
.stDialog > div {
    border-radius: 12px;
}
.draft-container {
    background-color: #f8f9fa;
    padding: 15px;
    border-radius: 8px;
    border: 1px solid #e9ecef;
    margin-bottom: 20px;
    color: #212529;
}
.draft-field {
    margin-bottom: 10px;
}
.draft-label {
    font-weight: 600;
    color: #495057;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# SESSION INITIALIZATION
# ============================================================

if "user" not in st.session_state:
    st.session_state.user = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# ============================================================
# AUTHENTICATION
# ============================================================

if st.session_state.user is None:
    st.title("📧 AI Email Assistant")
    st.markdown("Welcome! Please log in to continue.")
    
    with st.form("login_form"):
        user_id = st.text_input("User ID", placeholder="e.g. U001")
        submit = st.form_submit_button("Login")
        
        if submit:
            if not user_id.strip():
                st.error("Please enter a User ID.")
            else:
                user = authenticate_user(user_id)
                if user:
                    st.session_state.user = user
                    st.session_state.messages = []
                    st.rerun()
                else:
                    st.error("Authentication failed. User ID not found.")
    st.stop()


# ============================================================
# MAIN APPLICATION
# ============================================================

user = st.session_state.user

with st.sidebar:
    st.markdown("### 📧 AI Email Assistant")
    st.markdown(f"**User:** {user['name']}")
    st.markdown(f"**Email:** {user['email']}")
    st.divider()
    
    if st.button("Clear Conversation"):
        st.session_state.messages = []
        # In a real app we might also want to reset the thread id, 
        # but the requirements say "preserve the same thread for the user during the session".
        st.rerun()
        
    if st.button("Logout"):
        st.session_state.user = None
        st.session_state.messages = []
        st.rerun()

st.title("AI Email Assistant")

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# LangGraph config and context
config = {"configurable": {"thread_id": f"user_{user['user_id']}"}}
context = EmailContext(user_id=user["user_id"], email_address=user["email"], name=user["name"])


# ============================================================
# HANDLE INTERRUPTS (DRAFT REVIEW DIALOG)
# ============================================================

# Check if graph is currently interrupted
g_state = agent.get_state(config)
if g_state.tasks and g_state.tasks[0].interrupts:
    interrupt_val = g_state.tasks[0].interrupts[0].value
    
    if isinstance(interrupt_val, dict) and interrupt_val.get("action") in ["review_draft", "review_reply_draft", "final_approval", "final_reply_approval"]:
        
        # Determine if it's the draft phase or final approval phase
        action_val = interrupt_val.get("action")
        is_final = action_val in ["final_approval", "final_reply_approval"]
        action_type = "Send" if "reply" not in action_val else "Reply"
        title = f"Final Approval: {action_type} Email" if is_final else f"Draft Review: {action_type} Email"
        
        @st.dialog(title)
        def review_draft_dialog(draft):
            if "edit_mode" not in st.session_state:
                st.session_state.edit_mode = False

            if is_final:
                # ========================================================
                # 2. FINAL APPROVAL PHASE (STRICTLY READ ONLY)
                # ========================================================
                st.markdown(f"**To:** {draft['to']}")
                st.markdown(f"**Subject:** {draft['subject']}")
                st.markdown(f"**Body:**\n\n{draft['body']}")
                st.info("The AI has reviewed this final version. Please confirm sending.")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Approve & Send", use_container_width=True):
                        with st.spinner(f"Sending {action_type.lower()}..."):
                            response = agent.invoke(Command(resume={"action": "approve"}), config=config, context=context)
                            if response.get("messages"):
                                for msg in reversed(response["messages"]):
                                    if msg.__class__.__name__ in ["AIMessage", "AIMessageChunk"] and getattr(msg, "content", ""):
                                        st.session_state.messages.append({"role": "assistant", "content": msg.content})
                                        break
                        st.rerun()
                with col2:
                    if st.button("❌ Reject", use_container_width=True):
                        with st.spinner("Cancelling..."):
                            response = agent.invoke(Command(resume="n"), config=config, context=context)
                            if response.get("messages"):
                                for msg in reversed(response["messages"]):
                                    if msg.__class__.__name__ in ["AIMessage", "AIMessageChunk"] and getattr(msg, "content", ""):
                                        st.session_state.messages.append({"role": "assistant", "content": msg.content})
                                        break
                        st.rerun()

            else:
                # ========================================================
                # 1. DRAFT REVIEW PHASE
                # ========================================================
                if not st.session_state.edit_mode:
                    # Read Only View
                    st.markdown(f"**To:** {draft['to']}")
                    st.markdown(f"**Subject:** {draft['subject']}")
                    st.markdown(f"**Body:**\n\n{draft['body']}")
                    
                    st.markdown("Please review the draft.")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✏️ Edit", use_container_width=True):
                            st.session_state.edit_mode = True
                            st.rerun()
                    with col2:
                        if st.button("✅ Continue", use_container_width=True):
                            with st.spinner("Passing to AI for final review..."):
                                st.session_state.edit_mode = False
                                resume_payload = {
                                    "action": "continue",
                                    "subject": draft['subject'],
                                    "body": draft['body']
                                }
                                response = agent.invoke(Command(resume=resume_payload), config=config, context=context)
                                if response.get("messages"):
                                    for msg in reversed(response["messages"]):
                                        if msg.__class__.__name__ in ["AIMessage", "AIMessageChunk"] and getattr(msg, "content", ""):
                                            st.session_state.messages.append({"role": "assistant", "content": msg.content})
                                            break
                            st.rerun()
                else:
                    # Edit View
                    st.markdown(f"**To:** {draft['to']}")
                    edited_subject = st.text_input("Subject", value=draft['subject'])
                    edited_body = st.text_area("Body", value=draft['body'], height=200)
                    
                    if st.button("✅ Submit Changes", use_container_width=True):
                        with st.spinner("Passing edited draft to AI for final review..."):
                            st.session_state.edit_mode = False
                            resume_payload = {
                                "action": "continue",
                                "subject": edited_subject,
                                "body": edited_body
                            }
                            response = agent.invoke(Command(resume=resume_payload), config=config, context=context)
                            if response.get("messages"):
                                for msg in reversed(response["messages"]):
                                    if msg.__class__.__name__ in ["AIMessage", "AIMessageChunk"] and getattr(msg, "content", ""):
                                        st.session_state.messages.append({"role": "assistant", "content": msg.content})
                                        break
                        st.rerun()

        review_draft_dialog(interrupt_val)
        st.stop()


# ============================================================
# CHAT INPUT & STREAMING
# ============================================================

prompt = st.chat_input("How can I help you today?")

if "pending_feedback" in st.session_state and st.session_state.pending_feedback:
    prompt = st.session_state.pending_feedback
    st.session_state.pending_feedback = None

if prompt:
    
    # Only append if it's from chat_input (pending_feedback already appended it in the dialog)
    if not (st.session_state.messages and st.session_state.messages[-1].get("content") == prompt and st.session_state.messages[-1].get("role") == "user"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        state_input = {
            "messages": [HumanMessage(content=prompt)],
            "authenticated": True,
            "can_read_email": user["can_read_email"],
            "can_send_email": user["can_send_email"],
            "can_reply_email": user["can_reply_email"],
        }
        
        try:
            # Stream the response
            chunks = agent.stream(state_input, config=config, context=context, stream_mode="messages")
            for chunk_tuple in chunks:
                chunk, metadata = chunk_tuple
                
                # Filter strictly for user-facing model messages (AIMessageChunk)
                # Ignore ToolMessage, HumanMessage, etc.
                if chunk.__class__.__name__ == "AIMessageChunk":
                    # Some chunks might only contain tool_calls, so check if there's text content
                    if getattr(chunk, "content", "") and isinstance(chunk.content, str):
                        full_response += chunk.content
                        message_placeholder.markdown(full_response + "▌")
            
            # Remove cursor
            if full_response:
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            
            st.rerun()
                
        except Exception as e:
            error_str = str(e)
            if "rate_limit" in error_str.lower() or "429" in error_str or "413" in error_str:
                import re
                msg = "Groq rate limit reached. Please try again after the limit resets."
                # Look for retry time like "Please try again in 14m"
                match = re.search(r"try again in\s+([0-9a-zA-Z]+)", error_str, re.IGNORECASE)
                if match:
                    msg = f"Groq rate limit reached. Please try again in {match.group(1)}."
                st.error(msg)
            else:
                st.error("Sorry, an error occurred while processing your request. Please try again.")
            print(f"Error: {e}") # Log internally

import os.path
import base64

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
]


def get_gmail_service():
    creds = None

    if os.path.exists("credentials/token.json"):
        creds = Credentials.from_authorized_user_file(
            "credentials/token.json",
            SCOPES
        )

    if not creds or not creds.valid or not creds.has_scopes(SCOPES):

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials/credentials.json",
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open("credentials/token.json", "w") as token:
            token.write(creds.to_json())

    return build(
        "gmail",
        "v1",
        credentials=creds
    )


def get_recent_emails(service, max_results=5):

    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])

    emails = []

    for message in messages:

        email = service.users().messages().get(
            userId="me",
            id=message["id"],
            format="metadata",
            metadataHeaders=[
                "From",
                "To",
                "Subject",
                "Date"
            ]
        ).execute()

        headers = email["payload"]["headers"]

        email_data = {
            "id": email["id"],
            "from": None,
            "to": None,
            "subject": None,
            "date": None
        }

        for header in headers:

            if header["name"] == "From":
                email_data["from"] = header["value"]

            elif header["name"] == "To":
                email_data["to"] = header["value"]

            elif header["name"] == "Subject":
                email_data["subject"] = header["value"]

            elif header["name"] == "Date":
                email_data["date"] = header["value"]

        emails.append(email_data)

    return emails


def search_emails(service, query, max_results=5):

    results = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])

    emails = []

    for message in messages:

        email = service.users().messages().get(
            userId="me",
            id=message["id"],
            format="metadata",
            metadataHeaders=[
                "From",
                "To",
                "Subject",
                "Date"
            ]
        ).execute()

        headers = email["payload"]["headers"]

        email_data = {
            "id": email["id"],
            "from": None,
            "to": None,
            "subject": None,
            "date": None
        }

        for header in headers:

            if header["name"] == "From":
                email_data["from"] = header["value"]

            elif header["name"] == "To":
                email_data["to"] = header["value"]

            elif header["name"] == "Subject":
                email_data["subject"] = header["value"]

            elif header["name"] == "Date":
                email_data["date"] = header["value"]

        emails.append(email_data)

    return emails


def get_email_body(payload):

    if payload.get("body", {}).get("data"):

        data = payload["body"]["data"]

        body = base64.urlsafe_b64decode(data).decode(
            "utf-8",
            errors="replace"
        )

        if payload.get("mimeType") == "text/html":

            soup = BeautifulSoup(
                body,
                "html.parser"
            )

            return soup.get_text(
                separator="\n",
                strip=True
            )

        return body

    for part in payload.get("parts", []):

        mime_type = part.get("mimeType")

        if mime_type in ["text/plain", "text/html"]:

            data = part.get("body", {}).get("data")

            if data:

                body = base64.urlsafe_b64decode(
                    data
                ).decode(
                    "utf-8",
                    errors="replace"
                )

                if mime_type == "text/html":

                    soup = BeautifulSoup(
                        body,
                        "html.parser"
                    )

                    return soup.get_text(
                        separator="\n",
                        strip=True
                    )

                return body

        if part.get("parts"):

            body = get_email_body(part)

            if body:
                return body

    return ""


def get_email(service, message_id):

    email = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()

    headers = email["payload"]["headers"]

    email_data = {
        "id": email["id"],
        "threadId": email.get("threadId"),
        "message_id_header": None,
        "from": None,
        "to": None,
        "subject": None,
        "date": None,
        "body": ""
    }

    for header in headers:

        if header["name"] == "From":
            email_data["from"] = header["value"]

        elif header["name"] == "To":
            email_data["to"] = header["value"]

        elif header["name"] == "Subject":
            email_data["subject"] = header["value"]

        elif header["name"] == "Date":
            email_data["date"] = header["value"]
            
        elif header["name"] == "Message-ID":
            email_data["message_id_header"] = header["value"]
            
        elif header["name"] == "References":
            email_data["references"] = header["value"]

    email_data["body"] = get_email_body(
        email["payload"]
    )

    return email_data


def send_email_action(service, to, subject, body):
    from email.message import EmailMessage
    
    message = EmailMessage()
    message.set_content(body)
    message["To"] = to
    message["Subject"] = subject
    
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {"raw": encoded_message}
    
    send_message = service.users().messages().send(userId="me", body=create_message).execute()
    return send_message


def reply_email_action(service, to, subject, body, thread_id, message_id_header, references):
    from email.message import EmailMessage
    
    message = EmailMessage()
    message.set_content(body)
    message["To"] = to
    message["Subject"] = subject
    
    if message_id_header:
        message["In-Reply-To"] = message_id_header
        if references:
            message["References"] = f"{references} {message_id_header}"
        else:
            message["References"] = message_id_header
            
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {
        "raw": encoded_message,
        "threadId": thread_id
    }
    
    send_message = service.users().messages().send(userId="me", body=create_message).execute()
    return send_message
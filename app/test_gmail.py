import os.path
import base64
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
]

def get_service():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens
    
    # CHANGE: Check maf_agent/token.json first
    token_file = "token.json"
    if not os.path.exists(token_file) and os.path.exists("maf_agent/token.json"):
        token_file = "maf_agent/token.json"
        
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # CHANGE: Look in maf_agent/oauth_credentials.json if credentials.json is not in root
            creds_file = "credentials.json"
            if not os.path.exists(creds_file):
                creds_file = "maf_agent/oauth_credentials.json"

            if not os.path.exists(creds_file):
                print(f"[ERROR] '{creds_file}' not found.")
                print("   Please download OAuth 2.0 Desktop credentials from Google Cloud Console.")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(
                creds_file, SCOPES
            )
            
            print("[INFO] Opening browser for Google authentication...")
            
            try:
                creds = flow.run_local_server(port=0)  # port=0 lets OS pick available port
            except Exception as e:
                print(f"\n[ERROR] Authentication failed: {e}")
                return None
            
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("gmail", "v1", credentials=creds)
        return service
    except HttpError as error:
        print(f"[ERROR] An error occurred: {error}")
        return None

def read_recent_emails(service, limit=5):
    print(f"\n[INBOX] Reading last {limit} emails...")
    try:
        # Call the Gmail API
        results = service.users().messages().list(userId="me", maxResults=limit).execute()
        messages = results.get("messages", [])

        if not messages:
            print("   No labels found.")
            return

        for msg in messages:
            txt = service.users().messages().get(userId="me", id=msg["id"]).execute()
            payload = txt.get("payload", {})
            headers = payload.get("headers", [])
            
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "(Unknown)")
            snippet = txt.get("snippet", "")
            
            print(f"   - From: {sender}")
            print(f"     Subject: {subject}")
            print(f"     Snippet: {snippet[:60]}...")
            print("-" * 40)

    except HttpError as error:
        print(f"[ERROR] An error occurred: {error}")

def send_test_email(service, to_email):
    print(f"\n[SEND] Sending test email to {to_email}...")
    try:
        message = EmailMessage()
        message.set_content("This is a test email sent from OSiri MAF Agent script.")
        message["To"] = to_email
        message["From"] = "me"  # Special value for authenticated user
        message["Subject"] = "Test Email from OSiri"

        # encoded message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {"raw": encoded_message}
        send_message = (
            service.users()
            .messages()
            .send(userId="me", body=create_message)
            .execute()
        )
        print(f"[OK] Email sent! Message Id: {send_message['id']}")
    except HttpError as error:
        print(f"[ERROR] An error occurred: {error}")

if __name__ == "__main__":
    service = get_service()
    if service:
        read_recent_emails(service)
        
        # Uncomment to test sending (replace with your email)
        send_test_email(service, "mcs12@mail.aub.edu") 
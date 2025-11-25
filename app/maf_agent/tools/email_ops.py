import os
import base64
import webbrowser
import threading
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes required for reading and sending
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth callback on the specific redirect URI path."""
    auth_code = None
    
    def do_GET(self):
        # Match the path /code explicitly as required by your Google Console config
        if self.path.startswith('/code'):
            query_components = parse_qs(urlparse(self.path).query)
            if 'code' in query_components:
                OAuthCallbackHandler.auth_code = query_components['code'][0]
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Authentication successful!</h1><p>You can close this window and return to the terminal.</p></body></html>")
            else:
                self.send_response(400)
                self.wfile.write(b"Missing 'code' parameter in callback.")
        else:
            self.send_response(404)
            self.wfile.write(b"Not Found. Expected callback at /code.")
    
    def log_message(self, format, *args):
        # Suppress HTTP logs to console to keep output clean
        return

class EmailManager:
    def __init__(self):
        self.creds = None
        self.service = None
        self.authenticate()

    def authenticate(self):
        """Handles OAuth2 Flow"""
        # Use absolute paths or relative to CWD. Assuming CWD is project root.
        creds_path = 'app/maf_agent/oauth_credentials.json'
        token_path = 'app/maf_agent/token.json'
        
        if not os.path.exists(creds_path) and os.path.exists('oauth_credentials.json'):
             creds_path = 'oauth_credentials.json'
             token_path = 'token.json'

        # token.json stores the user's access and refresh tokens
        if os.path.exists(token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            except Exception:
                self.creds = None
        
        # If there are no (valid) credentials available, let the user log in.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    print(f"Error refreshing token: {e}, forcing re-login.")
                    self.creds = None

            if not self.creds:
                if not os.path.exists(creds_path):
                     raise FileNotFoundError(f"Credentials file not found at {creds_path}")
                
                print("Launching browser for authentication...")
                
                # Initialize Flow
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                
                # CRITICAL: Match the redirect URI exactly as registered in Google Console
                # The user's JSON specified: "http://localhost:4100/code"
                redirect_uri = "http://localhost:4100/code"
                flow.redirect_uri = redirect_uri
                
                # Generate authorization URL
                auth_url, _ = flow.authorization_url(prompt='consent')
                
                # Start local server to listen for the callback
                # Note: HTTPServer listens on the port, but we handle the /code path in the handler
                server = HTTPServer(('localhost', 4100), OAuthCallbackHandler)
                
                print(f"Opening: {auth_url}")
                webbrowser.open(auth_url)
                
                # Wait for the single request containing the code
                # We loop until we get the code, handling potential favicon requests etc.
                OAuthCallbackHandler.auth_code = None
                while not OAuthCallbackHandler.auth_code:
                    server.handle_request()
                
                server.server_close()
                
                # Exchange the code for a token
                flow.fetch_token(code=OAuthCallbackHandler.auth_code)
                self.creds = flow.credentials
            
            # Save the credentials for the next run
            with open(token_path, 'w') as token:
                token.write(self.creds.to_json())

        self.service = build('gmail', 'v1', credentials=self.creds)

    def fetch_unread(self, limit: int = 5) -> str:
        """Fetches unread emails using Gmail API"""
        try:
            # 'q' parameter filters for unread messages
            results = self.service.users().messages().list(
                userId='me', labelIds=['UNREAD'], maxResults=limit
            ).execute()
            messages = results.get('messages', [])

            if not messages:
                return "No unread emails found."

            summary = []
            for msg in messages:
                # Get full message details
                txt = self.service.users().messages().get(
                    userId='me', id=msg['id']
                ).execute()
                
                headers = txt['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                
                summary.append(f"From: {sender} | Subject: {subject}")

            return "\n".join(summary)

        except Exception as e:
            return f"Error fetching emails: {str(e)}"

    def send_email(self, to_email: str, subject: str, body: str) -> str:
        """Sends email using Gmail API"""
        try:
            message = MIMEText(body)
            message['to'] = to_email
            message['from'] = "me" # 'me' is a special value in Gmail API
            message['subject'] = subject
            
            # Encode the message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            body = {'raw': raw_message}

            self.service.users().messages().send(userId='me', body=body).execute()
            return f"Email sent successfully to {to_email}"
        except Exception as e:
            return f"Error sending email: {str(e)}"

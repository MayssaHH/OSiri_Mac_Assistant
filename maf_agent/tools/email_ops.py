import smtplib
from email.mime.text import MIMEText
from imap_tools import MailBox, A
from typing import List, Dict

class EmailManager:
    def __init__(self, email: str, password: str, imap_server: str, smtp_server: str):
        self.email = email
        self.password = password
        self.imap_server = imap_server
        self.smtp_server = smtp_server

    def fetch_unread(self, limit: int = 5) -> str:
        """Fetches unread emails from the Inbox."""
        print(f"DEBUG: Connecting to IMAP {self.imap_server} as {self.email}...")
        try:
            summary = []
            # Using imap-tools for cleaner API
            with MailBox(self.imap_server).login(self.email, self.password) as mailbox:
                # Fetch unseen messages
                for msg in mailbox.fetch(A(seen=False), limit=limit, reverse=True):
                    summary.append(
                        f"From: {msg.from_} | Subject: {msg.subject} | Date: {msg.date_str}"
                    )
            
            if not summary:
                return "No unread emails found."
            return "\n".join(summary)

        except Exception as e:
            print(f"DEBUG: IMAP Error Details: {e}")
            return f"Error fetching emails: {str(e)}"

    def send_email(self, to_email: str, subject: str, body: str) -> str:
        """Sends an email using SMTP with STARTTLS (port 587) or SSL (port 465)."""
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = self.email
        msg['To'] = to_email

        try:
            # Try STARTTLS on port 587 first (for Outlook.com / modern providers)
            try:
                with smtplib.SMTP(self.smtp_server, 587) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.ehlo()
                    smtp.login(self.email, self.password)
                    smtp.send_message(msg)
                return f"Email sent successfully to {to_email} (via STARTTLS)"
            except Exception as starttls_err:
                print(f"DEBUG: STARTTLS failed: {starttls_err}, trying SSL...")
                # Fall back to SSL on port 465 (for Gmail / legacy)
                with smtplib.SMTP_SSL(self.smtp_server, 465) as smtp:
                    smtp.login(self.email, self.password)
                    smtp.sendmail(self.email, to_email, msg.as_string())
                return f"Email sent successfully to {to_email} (via SSL)"
        except Exception as e:
            return f"Error sending email: {str(e)}"


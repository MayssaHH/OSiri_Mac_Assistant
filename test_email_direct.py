import os
from dotenv import load_dotenv
from imap_tools import MailBox

load_dotenv()

EMAIL = os.getenv("EMAIL_ACCOUNT")
PASSWORD = os.getenv("EMAIL_PASSWORD")
IMAP_SERVER = os.getenv("IMAP_SERVER")

print(f"Testing IMAP connection...")
print(f"Email: {EMAIL}")
print(f"Server: {IMAP_SERVER}")
print(f"Password length: {len(PASSWORD)} chars")

try:
    with MailBox(IMAP_SERVER).login(EMAIL, PASSWORD) as mailbox:
        print("✅ LOGIN SUCCESS!")
        count = len(list(mailbox.fetch(limit=1)))
        print(f"Found {count} message(s) in inbox.")
except Exception as e:
    print(f"❌ LOGIN FAILED: {e}")
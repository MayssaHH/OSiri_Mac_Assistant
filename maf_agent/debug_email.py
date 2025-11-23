import os
import imaplib
from dotenv import load_dotenv

# Load environment variables
import os
env_path = os.path.join(os.getcwd(), "maf_agent", ".env")
print(f"Loading .env from: {env_path}")
load_dotenv(env_path)

email = os.getenv("EMAIL_ACCOUNT")
password = os.getenv("EMAIL_PASSWORD")
server = os.getenv("IMAP_SERVER")

print("-" * 30)
print("EMAIL DEBUGGER")
print("-" * 30)
print(f"Email Account: '{email}'")
print(f"IMAP Server:   '{server}'")

if not password:
    print("ERROR: Password is empty or None.")
else:
    print(f"Password Len:  {len(password)} characters")
    # Check for spaces in password
    if " " in password:
        print("WARNING: Password contains spaces! Gmail App Passwords should usually be concatenated.")

print("-" * 30)
print("Attempting Connection...")

try:
    # Connect to server
    mail = imaplib.IMAP4_SSL(server)
    print("1. Connected to IMAP Server.")
    
    # Login
    mail.login(email, password)
    print("2. Login SUCCESSFUL!")
    
    # Select Inbox
    mail.select("inbox")
    print("3. Inbox Selected.")
    
    # Logout
    mail.logout()
    print("4. Logged out.")
    print("-" * 30)
    print("VERDICT: Credentials are CORRECT.")

except Exception as e:
    print("\nFAILED!")
    print(f"Error: {e}")
    print("-" * 30)
    print("VERDICT: Credentials or Server Settings are INCORRECT.")


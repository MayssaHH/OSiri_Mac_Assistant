import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    
    EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    IMAP_SERVER = os.getenv("IMAP_SERVER")
    SMTP_SERVER = os.getenv("SMTP_SERVER")

    @classmethod
    def validate(cls):
        """Ensure critical environment variables are present."""
        missing = []
        if not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        # Slack and Email checks relaxed for testing or if using OAuth
        # if not cls.SLACK_BOT_TOKEN:
        #    missing.append("SLACK_BOT_TOKEN")
            
        if missing:
            raise ValueError(f"Missing critical environment variables: {', '.join(missing)}")

# Validate on import
# Note: We might want to defer validation to main execution to allow importing for other reasons,
# but per requirements, we'll keep it here or call it explicitly in main.
# For now, let's not call it immediately on import to avoid crashing tools if envs aren't set during development.
# We will call Config.validate() in main.py.


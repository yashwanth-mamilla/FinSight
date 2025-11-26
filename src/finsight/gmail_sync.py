"""
Gmail synchronization module for downloading bank statement attachments.
"""
import os
import datetime
import base64
from pathlib import Path
from typing import List, Dict, Optional
import yaml
import click
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gmail API scope
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify'  # for marking as read
]

class GmailSync:
    """Handles Gmail operations: authentication, search, download."""

    def __init__(self, config_path: str = 'config/gmail_config.yaml'):
        self.config_path = config_path
        self.config = self.load_config()
        self.credentials = self.get_credentials()
        self.service = build('gmail', 'v1', credentials=self.credentials)
        self.download_dir = Path('statements')
        self.download_dir.mkdir(exist_ok=True)

    def load_config(self) -> Dict:
        """Load Gmail search configuration."""
        if not Path(self.config_path).exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config

    def get_credentials(self) -> Credentials:
        """Handle OAuth2 flow and return credentials."""
        creds = None

        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        return creds

    def search_emails(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search Gmail with query and return message metadata."""
        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            return results.get('messages', [])
        except HttpError as error:
            click.echo(f'An error occurred: {error}')
            return []

    def get_message_attachments(self, message_id: str) -> List[Dict]:
        """Extract attachment information from message."""
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            attachments = []
            for part in message['payload']['parts']:
                if 'filename' in part and part['filename']:
                    if 'attachmentId' in part['body']:
                        attachments.append({
                            'filename': part['filename'],
                            'attachment_id': part['body']['attachmentId'],
                            'message_id': message_id,
                            'date': message['internalDate']
                        })

            return attachments
        except HttpError as error:
            click.echo(f'An error occurred getting message {message_id}: {error}')
            return []

    def download_attachment(self, message_id: str, attachment_id: str, filename: str) -> str:
        """Download attachment and save to local file."""
        try:
            attachment = self.service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute()

            data = attachment['data']
            file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))

            # Create unique filename with date
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{filename}"
            file_path = self.download_dir / unique_filename

            with open(file_path, 'wb') as f:
                f.write(file_data)

            return str(file_path)
        except HttpError as error:
            click.echo(f'An error occurred downloading attachment: {error}')
            return ''

    def sync_statements(self, since_days: int = 7) -> List[str]:
        """Main sync function: search queries, download attachments."""
        downloaded_files = []
        processed_message_ids = self.get_processed_message_ids()

        # Calculate date query
        since_date = (datetime.datetime.now() - datetime.timedelta(days=since_days)).strftime('%Y/%m/%d')
        base_query = f"after:{since_date}"

        # Process each query from config
        for query_config in self.config.get('gmail', {}).get('queries', []):
            subject_pattern = query_config.get('subject', '')
            attachment_pattern = query_config.get('attachment', '*.pdf')

            query = f"{base_query} {subject_pattern}"

            click.echo(f"Searching: {query}")

            messages = self.search_emails(query)
            for message in messages:
                if message['id'] in processed_message_ids:
                    continue  # Skip already processed

                attachments = self.get_message_attachments(message['id'])
                for attachment in attachments:
                    filename = attachment['filename']
                    if self.matches_attachment_pattern(filename, attachment_pattern):
                        click.echo(f"Downloading: {filename}")
                        file_path = self.download_attachment(
                            message['id'], attachment['attachment_id'], filename
                        )
                        if file_path:
                            downloaded_files.append(file_path)
                            self.mark_message_processed(message['id'])

        return downloaded_files

    def matches_attachment_pattern(self, filename: str, pattern: str) -> bool:
        """Simple pattern matching for attachment names."""
        import fnmatch
        return fnmatch.fnmatch(filename.lower(), pattern.lower())

    def get_processed_message_ids(self) -> set:
        """Load IDs of previously processed messages."""
        id_file = Path('.processed_emails.txt')
        if id_file.exists():
            with open(id_file, 'r') as f:
                return set(line.strip() for line in f)
        return set()

    def mark_message_processed(self, message_id: str):
        """Save message ID to avoid processing again."""
        id_file = Path('.processed_emails.txt')
        mode = 'a' if id_file.exists() else 'w'
        with open(id_file, mode) as f:
            f.write(f"{message_id}\n")

def install_oauth():
    """Guide user through OAuth2 setup."""
    click.echo("""
    📧 Gmail Integration Setup:

    1. Go to the Google Cloud Console: https://console.cloud.google.com/
    2. Create a new project or select existing
    3. Enable Gmail API: APIs & Services > Library > search "Gmail API" > Enable
    4. Go to Credentials > Create Credentials > OAuth 2.0 Client ID
    5. Set application type to "Desktop application"
    6. Download the client_secret_*.json file and rename to credentials.json
    7. Place credentials.json in the project root
    8. First run will open OAuth flow in browser

    🔒 Account Protection: The system verifies the selected account against config
                        to prevent wrong account selection mistakes.
    """)

def verify_gmail_account(credentials: Credentials, expected_email: str = None) -> str:
    """
    Verify Gmail account after OAuth authorization.

    Args:
        credentials: OAuth2 credentials object
        expected_email: Expected email address (optional)

    Returns:
        str: Verified Gmail account email

    Raises:
        ValueError: If account verification fails or wrong account selected
    """
    try:
        service = build('gmail', 'v1', credentials=credentials)
        profile = service.users().getProfile(userId='me').execute()
        actual_email = profile['emailAddress']

        if expected_email and actual_email.lower() != expected_email.lower():
            click.echo(f"🚨 ACCOUNT MISMATCH DETECTED!")
            click.echo(f"   CLI Request: {expected_email}")
            click.echo(f"   Browser Selection: {actual_email}")
            click.echo(f"   ❌ Please retry OAuth and select the correct Gmail account")
            raise ValueError(f"Wrong account selected. Expected: {expected_email}, Got: {actual_email}")

        return actual_email

    except HttpError as e:
        raise Exception(f"Gmail API error during verification: {e}")

class MultiAccountGmail:
    """Manages multiple Gmail account tokens and OAuth flows."""

    def __init__(self, config_path: str = 'config/gmail_config.yaml'):
        self.config_path = config_path
        self.config = self.load_config()
        self.tokens_dir = Path('config/tokens')
        self.tokens_dir.mkdir(exist_ok=True)

    def load_config(self) -> dict:
        """Load Gmail account configuration."""
        if not Path(self.config_path).exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config

    def get_credentials_file_for_account(self, email: str) -> str:
        """
        Return the appropriate credentials file for an account.
        For now, use single credentials.json for all accounts.
        """
        # Get account config from gmail_accounts section
        account_config = self.config.get('gmail_accounts', {}).get(email, {})
        return account_config.get('credentials_file', 'credentials.json')

    def get_token_file_for_account(self, email: str) -> str:
        """Return the token file path for a specific account."""
        account_config = self.config.get('gmail_accounts', {}).get(email, {})
        token_filename = account_config.get('token_file', f"token_{email.split('@')[0]}.json")
        return str(self.tokens_dir / token_filename)

    def get_credentials_for_account(self, account_email: str) -> Credentials:
        """
        Get OAuth2 credentials for a specific Gmail account.
        Handles token file storage per account with verification.
        """
        token_file = self.get_token_file_for_account(account_email)
        credentials_file = self.get_credentials_file_for_account(account_email)

        creds = None

        # Check if token exists for this account
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                click.echo(f"🔐 OAuth Setup for: {account_email}")
                click.echo(f"📧 Browser will open - SELECT: {account_email}")

                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)

                # Verify the account immediately after authorization
                try:
                    verified_email = verify_gmail_account(creds, expected_email=account_email)
                    click.echo(f"✅ Account verified: {verified_email}")
                except ValueError as e:
                    # Delete the invalid token file
                    if os.path.exists(token_file):
                        os.remove(token_file)
                        click.echo(f"🗑️  Deleted invalid token file: {token_file}")
                    raise e

            # Save the credentials for this account
            with open(token_file, 'w') as f:
                f.write(creds.to_json())
            click.echo(f"💾 Token saved: {token_file}")

        return creds

@click.command()
@click.option('--config', default='config/gmail_config.yaml', help='Path to Gmail config file')
@click.option('--since-days', default=7, help='Search emails from last N days')
@click.option('--setup-oauth', is_flag=True, help='Setup OAuth2 credentials')
def sync_gmail(config: str, since_days: int, setup_oauth: bool):
    """Download bank statement attachments from Gmail."""
    if setup_oauth:
        install_oauth()
        return

    if not Path('credentials.json').exists():
        click.echo("Error: credentials.json not found. Run --setup-oauth first.")
        return

    try:
        syncer = GmailSync(config)
        downloaded = syncer.sync_statements(since_days)
        click.echo(f"Downloaded {len(downloaded)} statement files to '{syncer.download_dir}':")
        for file in downloaded:
            click.echo(f"  {file}")
    except Exception as e:
        click.echo(f"Sync failed: {e}")

if __name__ == '__main__':
    sync_gmail()

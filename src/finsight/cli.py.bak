import click
from pathlib import Path
import yaml

from .parsers import hdfc_cred_bill, amazon_pay_statement, HDFCStatementParser, SBIStatementParser
from .utils import write_expenses_convert, analyze_spending, load_expenses_from_csv
from .database import get_database

try:
    from .gmail_sync import sync_gmail as gmail_sync_command
except ImportError:
    gmail_sync_command = None

# Load supported banks configuration
def load_banks_config():
    """Load bank configuration from YAML."""
    config_path = Path(__file__).parent / '..' / '..' / 'config' / 'banks.yaml'
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        click.echo("Error: config/banks.yaml not found")
        return {"supported_bank_identifiers": ["hdfc-cred", "hdfc-bank", "sbi", "auto"]}

# Initialize banks config
banks_config = load_banks_config()
supported_banks = banks_config.get('supported_bank_identifiers', [])
bank_details = banks_config.get('banks', {})

@click.group()
def cli():
    pass

def get_pdf_password(file_path: str, bank_cli_id: str = None) -> str:
    """Get PDF password from config file using bank identifiers and filename."""
    import yaml
    from pathlib import Path

    # Load passwords config
    config_path = Path('config/passwords.yaml')
    if not config_path.exists():
        return None

    try:
        with open(config_path, 'r') as f:
            password_config = yaml.safe_load(f)
        passwords = password_config.get('passwords', {})

        # Always try filename as key first (most specific)
        filename = Path(file_path).stem
        if filename in passwords:
            return passwords[filename]

        # If bank CLI ID provided, use its password identifiers
        if bank_cli_id and bank_details:
            for bank_key, details in bank_details.items():
                if details.get('cli_identifier') == bank_cli_id:
                    password_keys = details.get('password_identifiers', [])
                    for key in password_keys:
                        if key in passwords:
                            return passwords[key]
                    break

        # Fallback: look for any matching key in passwords
        filename_lower = filename.lower()
        for key, password in passwords.items():
            if key.lower() in filename_lower or filename_lower.count(key.lower()) > 0:
                return password

    except Exception:
        pass  # Ignore errors, just continue without password

    return None

def format_bank_help():
    """Format help text for bank options from config."""
    if not bank_details:
        return "hdfc-cred, hdfc-bank, sbi, auto"

    bank_list = []
    for bank_key, details in bank_details.items():
        cli_id = details.get('cli_identifier', bank_key)
        name = details.get('name', cli_id)
        description = details.get('description', name)
        bank_list.append(f"{cli_id} ({name})")

    auto_option = "auto (auto-detect)"
    return ", ".join(bank_list) + f", {auto_option}"

@cli.command()
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--bank", default="auto", help=f"Bank type: {format_bank_help()}")
@click.option("--output", default="unified.csv", help="Output CSV file")
@click.option("--db", is_flag=True, help="Store transactions in database")
@click.option("--password", default=None, help="Password for encrypted PDF files")
def parse(file_path, bank, output, db, password):
    file_path = Path(file_path)
    expenses = []

    # Get password from config if PDF (using bank CLI identifier)
    pdf_password = password
    if not pdf_password and file_path.suffix.lower() == ".pdf":
        pdf_password = get_pdf_password(str(file_path), bank)

    if bank == "hdfc-cred" and file_path.suffix.lower() == ".pdf":
        click.echo("Parsing HDFC Credit Card PDF...")
        expenses = hdfc_cred_bill(str(file_path), pdf_password)
    elif bank in ["hdfc-bank", "hdfcbank"] or bank == "auto":
        if bank == "auto":
            # Simple auto-detect by extension
            if file_path.suffix.lower() == ".pdf":
                click.echo("Auto-detected as HDFC Credit Card PDF, use --bank hdfc-cred")
                return
            elif file_path.suffix.lower() in [".xlsx", ".xls"]:
                click.echo("Excel support not yet implemented.")
                return
            else:
                click.echo("Auto-assuming HDFC Bank CSV, use --bank for others.")
                parser = HDFCStatementParser()
                expenses = parser.parse_file(str(file_path))
        else:
            click.echo(f"Parsing {bank} statement...")
            parser = HDFCStatementParser()
            expenses = parser.parse_file(str(file_path))
    elif bank == "sbi":
        click.echo("Parsing SBI statement...")
        parser = SBIStatementParser()
        expenses = parser.parse_file(str(file_path))
    elif bank == "amazon-pay" and file_path.suffix.lower() == ".pdf":
        click.echo("Parsing Amazon Pay PDF...")
        expenses = amazon_pay_statement(str(file_path), pdf_password)
    else:
        supported_list = ", ".join(supported_banks[:-1]) + ", and " + supported_banks[-1] if len(supported_banks) > 1 else supported_banks[0] if supported_banks else "none"
        click.echo(f"Unsupported bank '{bank}'. Supported: {supported_list}")
        return
    
    if not expenses:
        click.echo("No transactions parsed.")
        return

    # Store to database if requested
    if db:
        db_instance = get_database()
        stored_count = db_instance.store_transactions(expenses, bank, str(file_path))
        click.echo(f"Stored {stored_count} transactions in database")

    # Always save to CSV as well
    output_path = write_expenses_convert(expenses, output)
    click.echo(f"Parsed {len(expenses)} transactions to {output_path}")

@cli.command()
@click.argument("csv_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--no-plots", is_flag=True, help="Disable plots")
def analyze(csv_file, no_plots):
    click.echo("Analyzing spending...")
    expenses = load_expenses_from_csv(csv_file)
    if no_plots:
        # To disable plots, perhaps catch
        analyze_spending(expenses)
    else:
        analyze_spending(expenses)
    click.echo("Analysis complete.")

@click.group()
def db():
    """Database operations for FinSight."""
    pass

cli.add_command(db)

@db.command('query')
@click.option('--bank', default=None, help='Filter by bank name (e.g., hdfc-cred)')
@click.option('--from-date', default=None, help='Start date (YYYY-MM-DD)')
@click.option('--to-date', default=None, help='End date (YYYY-MM-DD)')
@click.option('--category', default=None, help='Filter by category')
@click.option('--limit', default=50, type=int, help='Max results to return')
@click.option('--json', is_flag=True, help='Output as JSON')
def db_query(bank, from_date, to_date, category, limit, json):
    """Query transactions from database."""
    db_instance = get_database()

    filters = {}
    if bank:
        filters['bank_name'] = bank
    if from_date:
        filters['date_from'] = from_date
    if to_date:
        filters['date_to'] = to_date
    if category and category != 'all':
        filters['category'] = category

    transactions = db_instance.query_transactions(filters=filters, limit=limit)

    if json:
        import json
        click.echo(json.dumps(transactions, indent=2, default=str))
    else:
        if not transactions:
            click.echo("No transactions found matching criteria.")
            return

        click.echo(f"Found {len(transactions)} transactions:")
        for txn in transactions[:10]:  # Show first 10
            click.echo(f"  {txn['date']} | {txn['bank_name']} | {txn['description']} | ₹{txn['amount']}")

        if len(transactions) > 10:
            click.echo(f"  ... and {len(transactions) - 10} more")

@db.command('analyze')
@click.option('--bank', default=None, help='Analyze specific bank')
@click.option('--months', default=3, type=int, help='Months to analyze')
def db_analyze(bank, months):
    """Analyze spending patterns from database."""
    db_instance = get_database()
    stats = db_instance.get_spending_summary(bank_name=bank, months=months)

    if stats['total_transactions'] == 0:
        click.echo("No transaction data available for analysis.")
        return

    click.echo(f"📊 Database Analytics ({'All Banks' if not bank else f'{bank}'}) - Last {months} Months:")
    click.echo(f"📈 Total Transactions: {stats['total_transactions']}")
    click.echo(f"💰 Total Amount: ₹{stats['total_amount']:.2f}")
    click.echo(f"📊 Average Transaction: ₹{stats['average_transaction']:.2f}")

    if stats['top_categories']:
        click.echo("\n🏷️  Top Spending Categories:")
        for cat in stats['top_categories'][:5]:
            click.echo(f"  • {cat['category']}: ₹{abs(cat['total']):.2f} ({cat['count']} transactions)")

@db.command('stats')
def db_stats():
    """Show database statistics."""
    db_instance = get_database()
    stats = db_instance.get_db_stats()

    click.echo("📊 FinSight Database Statistics:")
    click.echo(f"📅 Date Range: {stats['date_range']['from']} to {stats['date_range']['to']}")

    if stats['banks']:
        click.echo(f"\n🏦 Bank Breakdown ({len(stats['banks'])} banks):")
        for bank in stats['banks']:
            click.echo(f"  • {bank['bank']}: {bank['transactions']} transactions, ₹{bank['total_amount']:.2f}")
    else:
        click.echo("📝 No transaction data in database yet.")
        click.echo("💡 Use 'finsight parse <file.pdf> --bank <type> --db' to import transactions.")

@cli.command()
@click.option('--config', default='config/gmail_config.yaml', help='Path to Gmail config file')
@click.option('--since-days', default=7, help='Search emails from last N days')
@click.option('--account', default=None, help='Specific Gmail account email (e.g., personal@gmail.com)')
@click.option('--banks', default=None, help='Comma-separated list of banks to sync (e.g., hdfc-cred,sbi)')
@click.option('--setup-oauth', is_flag=True, help='Setup OAuth2 for multi-account Gmail')
@click.option('--list-accounts', is_flag=True, help='List configured Gmail accounts')
def sync_gmail(config: str, since_days: int, account: str, banks: str, setup_oauth: bool, list_accounts: bool):
    """Download bank statement attachments from Gmail with multi-account support."""

    if setup_oauth:
        from .gmail_sync import install_oauth
        install_oauth()
        click.echo("\nMulti-account setup guide:")
        click.echo("1. For each email account, get OAuth credentials from Google Cloud Console")
        click.echo("2. Save as: credentials_{account}.json (e.g., credentials_personal.json)")
        click.echo("3. First run per account will create token_{account}.json")
        click.echo("4. Update config/gmail_config.yaml with your account details")
        return

    if list_accounts:
        try:
            gmail_config = yaml.safe_load(open(config)) if Path(config).exists() else {}
            accounts = gmail_config.get('gmail_accounts', {})
            click.echo("Configured Gmail accounts:")
            for email in accounts.keys():
                click.echo(f"  - {email}")
        except Exception as e:
            click.echo(f"Error reading config: {e}")
        return

    # Validate CLI parameters
    if account and banks:
        click.echo("Error: Use either --account OR --banks, not both.")
        click.echo("  --account: Sync all banks for specified email account")
        click.echo("  --banks: Sync specified banks from their configured accounts")
        return

    if account or banks:
        # Multi-account/sync implementation
        try:
            accounts_to_sync = _resolve_gmail_accounts(account, banks)
            total_downloaded = 0

            for gmail_account, account_banks in accounts_to_sync.items():
                click.echo(f"\n🔄 Syncing {gmail_account}...")
                click.echo(f"   Banks: {', '.join(account_banks) if account_banks else 'all'}")

                try:
                    downloaded = _sync_gmail_account(gmail_account, account_banks, since_days)
                    total_downloaded += len(downloaded)
                    click.echo(f"   📥 Downloaded {len(downloaded)} files")
                except Exception as e:
                    click.echo(f"   ❌ Failed: {e}")

            click.echo(f"\n✅ Total files downloaded: {total_downloaded}")

        except Exception as e:
            click.echo(f"Gmail sync error: {e}")
    else:
        # Legacy single-account (backward compatibility)
        click.echo("Warning: No --account or --banks specified.")
        click.echo("Using legacy single-account mode (requires credentials.json).")
        if not Path('credentials.json').exists():
            click.echo("Error: credentials.json not found. Use --setup-oauth or specify --account")
            return

        try:
            from .gmail_sync import GmailSync
            syncer = GmailSync(config)
            downloaded = syncer.sync_statements(since_days)
            click.echo(f"Downloaded {len(downloaded)} files in legacy mode")
        except Exception as e:
            click.echo(f"Sync failed: {e}")


def _resolve_gmail_accounts(account_email: str = None, banks_list: str = None) -> Dict[str, List[str]]:
    """Resolve which Gmail accounts and banks to sync."""

    # Load bank configurations
    banks_config = load_banks_config()
    all_banks = banks_config.get('banks', {})

    result = {}

    if account_email:
        # Account-by-account approach: find all banks for this account
        result[account_email] = []
        for bank_key, bank_info in all_banks.items():
            if bank_info.get('gmail_account') == account_email:
                cli_id = bank_info.get('cli_identifier', bank_key)
                result[account_email].append(cli_id)

        if not result[account_email]:
            raise ValueError(f"No banks configured for account: {account_email}")

    elif banks_list:
        # Bank-by-bank approach: group banks by their Gmail account
        bank_names = [b.strip() for b in banks_list.split(',') if b.strip()]

        for bank_name in bank_names:
            # Find the bank in config
            bank_config = None
            for bank_key, bank_info in all_banks.items():
                if bank_info.get('cli_identifier') == bank_name:
                    bank_config = bank_info
                    break

            if not bank_config:
                raise ValueError(f"Bank not configured: {bank_name}")

            gmail_account = bank_config.get('gmail_account')
            if not gmail_account:
                raise ValueError(f"No Gmail account configured for bank: {bank_name}")

            if gmail_account not in result:
                result[gmail_account] = []
            result[gmail_account].append(bank_name)

    return result


def _sync_gmail_account(account_email: str, bank_filters: List[str], since_days: int) -> List[str]:
    """Sync a single Gmail account for specific banks."""

    # Load Gmail config
    gmail_config_path = 'config/gmail_config.yaml'
    gmail_config = yaml.safe_load(open(gmail_config_path)) if Path(gmail_config_path).exists() else {}
    account_config = gmail_config.get('gmail_accounts', {}).get(account_email)

    if not account_config:
        raise ValueError(f"Account not configured: {account_email}")

    # Load bank configs to get bank-specific Gmail settings
    banks_config = load_banks_config()
    all_banks = banks_config.get('banks', {})

    # Create GmailSync with account-specific credentials
    from .gmail_sync import GmailSync

    class BankGmailSync(GmailSync):
        # Custom version that uses bank filters and bank-specific query patterns

        def sync_statements(self, since_days: int = 7) -> List[str]:
            """Override to use bank-specific queries instead of legacy ones."""
            downloaded_files = []
            processed_message_ids = self.get_processed_message_ids()

            since_date = (datetime.datetime.now() - datetime.timedelta(days=since_days)).strftime('%Y/%m/%d')
            base_query = f"after:{since_date}"

            # Get account-specific queries from bank configurations
            account_banks = self.banks_filter or []
            queries_to_run = []

            if account_banks:
                # Bank-specific mode
                for bank_name in account_banks:
                    # Find bank config
                    bank_config = None
                    for bank_key, bank_info in all_banks.items():
                        if bank_info.get('cli_identifier') == bank_name:
                            bank_config = bank_info
                            break

                    if bank_config:
                        subjects = bank_config.get('gmail_subjects', [])
                        attachments = bank_config.get('gmail_attachments', [])

                        for subject in subjects:
                            queries_to_run.append({
                                'subject': subject.replace('subject:(', '').replace(')', ''),
                                'attachment': attachments[0] if attachments else '*.pdf'
                            })
            else:
                # Account-wide mode - get queries from all banks for this account
                for bank_key, bank_info in all_banks.items():
                    if bank_info.get('gmail_account') == account_email:
                        subjects = bank_info.get('gmail_subjects', [])
                        attachments = bank_info.get('gmail_attachments', [])

                        for subject in subjects:
                            queries_to_run.append({
                                'subject': subject.replace('subject:(', '').replace(')', ''),
                                'attachment': attachments[0] if attachments else '*.pdf'
                            })

            # Remove duplicates
            seen = set()
            unique_queries = []
            for q in queries_to_run:
                key = (q['subject'], q['attachment'])
                if key not in seen:
                    seen.add(key)
                    unique_queries.append(q)

            # Process queries
            for query_config in unique_queries:
                subject_pattern = query_config.get('subject', '')
                attachment_pattern = query_config.get('attachment', '*.pdf')

                query = f"{base_query} {subject_pattern}"

                click.echo(f"    Searching: {query}")

                messages = self.search_emails(query)
                for message in messages:
                    if message['id'] in processed_message_ids:
                        continue

                    attachments = self.get_message_attachments(message['id'])
                    for attachment in attachments:
                        filename = attachment['filename']
                        if self.matches_attachment_pattern(filename, attachment_pattern):
                            file_path = self.download_attachment(
                                message['id'], attachment['attachment_id'], filename
                            )
                            if file_path:
                                downloaded_files.append(file_path)
                                self.mark_message_processed(message['id'])

            return downloaded_files

    # Create and run syncer
    syncer = BankGmailSync(
        config_path=gmail_config_path,
        account_email=account_email,
        banks_filter=bank_filters
    )

    return syncer.sync_statements(since_days)

def main():
    cli()

if __name__ == "__main__":
    main()

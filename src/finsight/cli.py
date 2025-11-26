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
@click.option('--setup-oauth', is_flag=True, help='Setup OAuth2 credentials')
def sync_gmail(config: str, since_days: int, setup_oauth: bool):
    """Download bank statement attachments from Gmail."""
    if gmail_sync_command is None:
        click.echo("Error: Gmail sync dependencies not installed. Install with: pip install google-api-python-client google-auth")
        return

    if setup_oauth:
        # Run the OAuth setup guide
        import io
        from contextlib import redirect_stdout
        from .gmail_sync import install_oauth
        install_oauth()
        return

    if not Path('credentials.json').exists():
        click.echo("Error: credentials.json not found. Run 'finsight sync-gmail --setup-oauth' first.")
        return

    try:
        from .gmail_sync import GmailSync
        syncer = GmailSync(config)
        downloaded = syncer.sync_statements(since_days)
        click.echo(f"Downloaded {len(downloaded)} statement files to '{syncer.download_dir}':")
        for file in downloaded:
            click.echo(f"  {file}")
    except Exception as e:
        click.echo(f"Sync failed: {e}")

def main():
    cli()

if __name__ == "__main__":
    main()

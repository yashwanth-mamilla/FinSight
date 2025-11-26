import click
from pathlib import Path
import yaml

from .parsers import hdfc_cred_bill, amazon_pay_statement, HDFCStatementParser, SBIStatementParser
from .utils import write_expenses_convert, analyze_spending, load_expenses_from_csv

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
@click.option("--password", default=None, help="Password for encrypted PDF files")
def parse(file_path, bank, output, password):
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

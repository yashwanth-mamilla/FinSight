import click
from pathlib import Path

from .parsers import hdfc_cred_bill, HDFCStatementParser, SBIStatementParser
from .utils import write_expenses_convert, analyze_spending, load_expenses_from_csv

try:
    from .gmail_sync import sync_gmail as gmail_sync_command
except ImportError:
    gmail_sync_command = None

@click.group()
def cli():
    pass

@cli.command()
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--bank", default="auto", help="Bank type: hdfc-cred, hdfc-bank, sbi, auto")
@click.option("--output", default="unified.csv", help="Output CSV file")
def parse(file_path, bank, output):
    file_path = Path(file_path)
    expenses = []
    if bank == "hdfc-cred" and file_path.suffix.lower() == ".pdf":
        click.echo("Parsing HDFC Credit Card PDF...")
        expenses = hdfc_cred_bill(str(file_path))
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
    else:
        click.echo("Unsupported bank. Supported: hdfc-cred, hdfc-bank, sbi")
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

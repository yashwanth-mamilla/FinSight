import click
from pathlib import Path

from .parsers import hdfc_cred_bill, HDFCStatementParser, SBIStatementParser
from .utils import write_expenses_convert, analyze_spending, load_expenses_from_csv

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

def main():
    cli()

if __name__ == "__main__":
    main()

# FinSight

CLI tool to unify and analyze bank statements.

## Installation

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install click pydantic pandas openpyxl pdfplumber matplotlib [langchain-ollama]
```

## Usage

Activate the virtual environment:
```bash
. .venv/bin/activate
```

Run the CLI (from project root):
```bash
python run.py --help
```

Parse a bank statement:
```bash
python run.py parse /path/to/statement.pdf --bank hdfc-cred --output my_statements.csv
```

Analyze spending:
```bash
python run.py analyze my_statements.csv
```

## Supported Banks/Formats

- HDFC Credit Card (PDF)
- HDFC Bank CSV
- SBI Bank CSV
- Excel support planned

## Future Features

- Notion integration for syncing
- More bank parsers
- Web dashboard

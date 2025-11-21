# FinSight

CLI tool to unify and analyze bank statements.

## Installation

```bash
git clone https://github.com/yashwanth-mamilla/FinSight.git
cd FinSight
python3 -m venv .venv
. .venv/bin/activate
pip install -e .  # Install dependencies and the finsight command globally
```

## Usage

Now you can use the `finsight` command directly:

```bash
finsight --help
```

Parse a bank statement:
```bash
finsight parse /path/to/statement.pdf --bank hdfc-cred --output my_statements.csv
```

Analyze spending:
```bash
finsight analyze my_statements.csv
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

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
# For password-protected PDFs:
finsight parse statement.pdf --bank hdfc-cred --password "mypass123" --output my_statements.csv
```

Configure PDF passwords in `config/passwords.yaml` for automatic detection:
```yaml
passwords:
  amazon_pay: "myamazonpass"
  hdfc_card: "mycardpass"
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

## Gmail Integration (Auto-download Statements)

FinSight can automatically download bank statement attachments from your Gmail:

### Gmail Setup:
1. **Get Gmail API credentials:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create project → Enable Gmail API
   - Create OAuth 2.0 client ID (Desktop application)
   - Download `client_secret_*.json` → rename to `credentials.json` in project root

2. **Configure search queries:**
   - Edit `config/gmail_config.yaml` with your bank email patterns

3. **Authenticate & Sync:**
   ```bash
   # Setup OAuth (first time only)
   finsight sync-gmail --setup-oauth
   
   # Download recent statements
   finsight sync-gmail --since-days 7
   ```

Downloads are saved to `statements/` directory, ready for parsing with `finsight parse`.

## Future Features

- Notion integration for syncing
- More bank parsers

import os
import csv
from datetime import datetime
from typing import List, Optional, Dict
import pdfplumber
from .models import ExpenseItem, clean_amount, parse_datetime

# Amazon Pay PDF Parser
def amazon_pay_statement(pdf_path: str, password: str = None, bank_name: str = "Amazon Pay") -> List[ExpenseItem]:
    """Parse Amazon Pay statement PDF using text-based transaction extraction."""
    transactions = []
    import re
    from datetime import datetime

    def parse_date(date_str):
        """Parse DD/MM/YYYY to date object."""
        try:
            return datetime.strptime(date_str, '%d/%m/%Y').date()
        except ValueError:
            return None

    try:
        with pdfplumber.open(pdf_path, password=password) as pdf:
            # Parse all pages - transaction lines can appear anywhere
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                # Check if this page contains the transaction header
                header_pattern = r'Date\s+SerNo\.\s+Transaction Details\s+Reward\s+Intl\.#\s+Amount'
                has_header = bool(re.search(header_pattern, text))

                if not has_header:
                    continue  # Skip pages without transaction header

                lines = text.split('\n')

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Look for lines starting with date pattern: DD/MM/YYYY
                    # e.g., "15/10/2025 12158779277 IGST-CI@18% 0 31.59"
                    date_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+', line)
                    if not date_match:
                        continue

                    date_str = date_match.group(1)
                    date = parse_date(date_str)
                    if not date:
                        continue

                    # Remove the date part to get remaining line
                    remaining = line[len(date_str)+1:].strip()

                    # Split by spaces and dots (for decimals)
                    # Need to be careful with variable number of tokens
                    parts = re.split(r'\s+', remaining)
                    if len(parts) < 3:  # Need at least SerNo, Transaction, Amount
                        continue

                    # Pattern analysis from user examples:
                    # "12158779277 IGST-CI@18% 0 31.59" -> SerNo, Description, Reward, Amount
                    ser_no = parts[0]

                    # Check if SerNo looks valid (long number)
                    if not ser_no.isdigit() or len(ser_no) < 8:
                        continue

                    # The last 1-2 parts should be numbers (reward + amount)
                    # Look for patterns: "... reward_points amount [CR]"
                    #獎 Amount is usually the last part, possibly with CR

                    # Find the amount (decimal number, possibly with CR)
                    amount = None
                    amount_idx = -1

                    # Check last part for amount pattern
                    if parts[-1] in ['CR', 'DR']:  # Special case for CR/DR
                        amount_str = parts[-2]
                        amount_idx = -2
                    else:
                        amount_str = parts[-1]
                        amount_idx = -1

                    # Check if it's a valid amount
                    if re.match(r'\d+(?:,\d+)*(?:\.\d{2})?', amount_str):
                        try:
                            amount = clean_amount(amount_str)
                        except ValueError:
                            continue
                    else:
                        continue

                    # Now extract transaction details - everything between SerNo and numbers
                    # This is everything from parts[1] to amount_idx-1

                    if amount_idx == -1:
                        # CR/DR at end, so description to parts[-3]
                        description_parts = parts[1:-2]
                    else:
                        # Normal case, description to parts[-2]
                        description_parts = parts[1:-1]

                    # Clean up description (remove extra numbers that might be international codes)
                    description = ' '.join(p for p in description_parts if not re.match(r'^\d+%?$', p))

                    if not description.strip():
                        description = ' '.join(description_parts)

                    # Handle CR (credits are negative in our system)
                    is_credit = line.upper().endswith(' CR')
                    if is_credit:
                        amount = -abs(amount)  # Ensure it's negative for credits

                    expense = ExpenseItem(
                        date=date,
                        time=None,
                        description=description.strip(),
                        amount=amount,
                        bank_name=bank_name
                    )
                    transactions.append(expense)

    except Exception as e:
        print(f"Amazon Pay parsing error: {e}")
        return []

    return transactions

# Moved from a.py
def hdfc_cred_bill(pdf_path: str, password: str = None, bank_name: str = "HDFC Credit Card") -> List[ExpenseItem]:
    transactions = []

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table[1:]:  # Skip header row
                    # 1️⃣ **Skip completely empty rows**
                    if not any(row) or all(cell in [None, '', ' '] for cell in row):
                        continue

                    # 2️⃣ **Extract date and check validity**
                    date_str = row[0] if row[0] else None  # Ensure we have a valid date column
                    if not date_str or len(date_str.strip()) < 10:
                        continue

                    date, time = parse_datetime(date_str, False)
                    if date is None:
                        continue

                    # 3️⃣ **Extract description safely**
                    description = row[1] if len(row) > 1 and row[1] else "No Description"

                    # 4️⃣ **Ensure the amount is present before conversion**
                    amount_str = row[-2] if len(row) > 2 and row[-2] else None
                    if not amount_str:
                        print(f"Skipping row due to missing amount: {row}")
                        continue

                    try:
                        amount = clean_amount(amount_str)
                    except ValueError:
                        print(f"Skipping row due to conversion error: {row}")
                        continue

                    # 5️⃣ **Process transaction**
                    expense = ExpenseItem(
                        date=date, time=time, description=description,
                        amount=amount, bank_name=bank_name
                    )
                    transactions.append(expense)
                    # if expense.category == 'Uncategorized':
                    #     print(f"Uncategorized Expense: {expense}")

    return transactions

class HDFCStatementParser:
    def parse_file(self, file_path: str, bank_name: str = "HDFC Bank") -> List[ExpenseItem]:
        """ Parses CSV-like HDFC bank statements from a file. """
        expenses = []
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return expenses

        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Assume columns: Date, Time, Description, Amount, Dr/Cr, etc.
                # But since sample not raw, this is placeholder
                # Need actual HDFC bank CSV format
                # For now, assume 'Date', 'Description', 'Debit', 'Credit'
                date_str = row.get('Date', row.get('Txn Date', ''))
                if not date_str:
                    continue
                try:
                    date = datetime.strptime(date_str, '%d-%m-%Y').date()
                    time = row.get('Time', '00:00:00') or '00:00:00'
                except ValueError:
                    continue

                description = row.get('Description', row.get('Details', ''))
                debit = row.get('Debit', row.get('Dr', '0'))
                credit = row.get('Credit', row.get('Cr', '0'))

                try:
                    amount = float(credit or 0) - float(debit or 0)
                except ValueError:
                    continue

                expense = ExpenseItem(date=date, time=time, description=description, amount=amount, bank_name=bank_name)
                expenses.append(expense)
        return expenses

class SBIStatementParser:
    def parse_file(self, file_path: str, bank_name: str = "State Bank of India (SBI)") -> List[ExpenseItem]:
        """ Parses CSV-like SBI bank statements from a file. """
        expenses = []
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return expenses

        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                date_str = row.get('Txn Date', row.get('Date', ''))
                if not date_str:
                    continue
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    time = row.get('Time', '00:00:00') or '00:00:00'
                except ValueError:
                    continue

                description = row.get('Details', row.get('Description', ''))
                debit = row.get('Debit', row.get('Dr', '')) or '0'
                credit = row.get('Credit', row.get('Cr', '')) or '0'

                try:
                    amount = float(credit.strip()) if credit.strip() else -float(debit.strip())
                except ValueError:
                    continue

                expense = ExpenseItem(date=date, time=time, description=description, amount=amount, bank_name=bank_name)
                expenses.append(expense)
        return expenses

import os
import csv
import re
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

                    # Look for lines containing date pattern: DD/MM/YYYY
                    # Handle various formats:
                    # - Direct: "15/10/2025 12158779277 IGST-CI@18% 0 31.59"
                    # - With prefix: "7% 25/10/2025 12219871867 Swiggy Limited Bangalore IN 5 591.00"
                    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
                    if not date_match:
                        continue

                    date_str = date_match.group(1)
                    date = parse_date(date_str)
                    if not date:
                        continue

                    # Find the position of the date and take everything after it
                    date_position = date_match.start()
                    remaining = line[date_position + len(date_str):].strip()

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
    print(f"DEBUG: Opening PDF {pdf_path} with password: {password}")

    with pdfplumber.open(pdf_path, password=password) as pdf:
        print(f"DEBUG: PDF has {len(pdf.pages)} pages")

        for page_num, page in enumerate(pdf.pages):
            print(f"DEBUG: Processing page {page_num + 1}")
            table = page.extract_table()

            if table:
                print(f"DEBUG: Page {page_num + 1} has table with {len(table)} rows, {len(table[0]) if table else 0} columns")
                print(f"DEBUG: Table[0] (header): {table[0] if table else 'No table'}")

                for row_idx, row in enumerate(table[1:], 1):  # Skip header row
                    print(f"DEBUG: Row {row_idx}: {row}")

                    # Handle HDFC single-column format
                    if len(row) == 1 and row[0]:
                        # Parse single column: "27/10/2025| 03:46 SWIGGYBENGALURU C 384.00 l"
                        full_line = row[0].strip()

                        # Skip if not enough content
                        if len(full_line) < 20:
                            print(f"DEBUG: Skipping short row {row_idx}")
                            continue

                        # Extract date|time part - look for pattern "DD/MM/YYYY| HH:MM"
                        date_match = re.search(r'(\d{2}/\d{2}/\d{4})\|\s*(\d{2}:\d{2})', full_line)
                        if not date_match:
                            print(f"DEBUG: No date/time found in row {row_idx}: '{full_line}'")
                            continue

                        date_time_str = f"{date_match.group(1)}| {date_match.group(2)}"
                        date, time = parse_datetime(date_time_str, True)
                        if date is None:
                            print(f"DEBUG: Failed to parse date/time in row {row_idx}: '{date_time_str}'")
                            continue

                        # Extract description and amount - everything after the time
                        remaining = full_line[date_match.end():].strip()

                        # Look for amount pattern - "C AMOUNT l"
                        amount_match = re.search(r'\bC\s+([\d,]+\.?\d*)\s+l\b', remaining)

                        if not amount_match:
                            print(f"DEBUG: No amount found in row {row_idx}: '{remaining}'")
                            continue

                        amount_str = amount_match.group(1)
                        try:
                            amount = float(amount_str.replace(',', ''))
                        except ValueError:
                            print(f"DEBUG: Invalid amount in row {row_idx}: '{amount_str}'")
                            continue

                        # Extract description - everything before "C AMOUNT l"
                        # But remove reward indicators (patterns like "+ NUMBER")
                        description_text = remaining[:amount_match.start()].strip()

                        # Remove reward patterns like "+ 4", "+ 60", etc.
                        description = re.sub(r'\s*\+\s+\d+', '', description_text).strip()

                        print(f"DEBUG: Parsed - Date: {date}, Time: {time}, Desc: '{description}', Amount: {amount}")

                        # Create ExpenseItem with parsed data
                        expense = ExpenseItem(
                            date=date, time=time, description=description,
                            amount=amount, bank_name=bank_name
                        )
                        transactions.append(expense)

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

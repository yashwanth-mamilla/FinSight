import os
import csv
from datetime import datetime
from typing import List, Optional, Dict
import pdfplumber
from .models import ExpenseItem, clean_amount, parse_datetime

# Moved from a.py
def hdfc_cred_bill(pdf_path: str) -> List[ExpenseItem]:
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
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
                        amount=amount
                    )
                    transactions.append(expense)
                    # if expense.category == 'Uncategorized':
                    #     print(f"Uncategorized Expense: {expense}")

    return transactions

class HDFCStatementParser:
    def parse_file(self, file_path: str) -> List[ExpenseItem]:
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
                
                expense = ExpenseItem(date=date, time=time, description=description, amount=amount)
                expenses.append(expense)
        return expenses

class SBIStatementParser:
    def parse_file(self, file_path: str) -> List[ExpenseItem]:
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

                expense = ExpenseItem(date=date, time=time, description=description, amount=amount)
                expenses.append(expense)

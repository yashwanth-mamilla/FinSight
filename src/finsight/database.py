"""Database module for FinSight transaction storage and querying."""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
from .models import ExpenseItem

class FinSightDatabase:
    """SQLite database manager for transaction storage."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # Default to finsight.db in project root
            root_path = Path(__file__).parent.parent.parent
            db_path = str(root_path / 'finsight.db')

        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bank_name TEXT NOT NULL,
                    date DATE NOT NULL,
                    time TIME,
                    name TEXT,
                    description TEXT,
                    amount REAL NOT NULL,
                    category TEXT,
                    balance REAL,
                    reference_id TEXT UNIQUE,
                    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE(bank_name, reference_id) ON CONFLICT REPLACE
                )
            ''')

            # Add name column to existing tables if it doesn't exist
            try:
                conn.execute('ALTER TABLE transactions ADD COLUMN name TEXT')
            except sqlite3.OperationalError:
                # Column already exists
                pass

            conn.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bank_name TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    account_type TEXT,
                    account_number TEXT,
                    last_balance REAL,
                    last_import TIMESTAMP,

                    UNIQUE(bank_name, account_number) ON CONFLICT REPLACE
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    bank_name TEXT NOT NULL,
                    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    transaction_count INTEGER DEFAULT 0,
                    total_amount REAL DEFAULT 0.0
                )
            ''')

            conn.commit()

    def get_connection(self):
        """Get database connection."""
        return sqlite3.connect(self.db_path)

    def store_transactions(self, transactions: List[ExpenseItem], bank_name: str,
                          file_path: str = None) -> int:
        """Store transactions in database with duplicate prevention."""
        stored_count = 0
        import_date = datetime.now()

        with self.get_connection() as conn:
            for transaction in transactions:
                # Create a reference ID from key transaction details
                # This helps prevent duplicates during re-imports
                reference_id = f"{bank_name}_{transaction.date}_{transaction.description}_{transaction.amount}"

                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO transactions
                        (bank_name, date, time, name, description, amount, category, reference_id, import_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        bank_name,
                        transaction.date.isoformat() if transaction.date else None,
                        transaction.time.isoformat() if transaction.time else None,
                        transaction.name or '',
                        transaction.description,
                        transaction.amount,
                        getattr(transaction, 'category', None) or 'Uncategorized',
                        reference_id,
                        import_date
                    ))
                    stored_count += 1
                except sqlite3.IntegrityError:
                    # Duplicate transaction, skip silently
                    continue

            # Log the import
            if file_path:
                conn.execute('''
                    INSERT INTO imports (file_path, bank_name, transaction_count, total_amount)
                    VALUES (?, ?, ?, ?)
                ''', (
                    file_path,
                    bank_name,
                    stored_count,
                    sum(t.amount for t in transactions)
                ))

            conn.commit()

        return stored_count

    def query_transactions(self, filters: Dict[str, Any] = None,
                          limit: int = None, offset: int = 0) -> List[Dict]:
        """Query transactions with flexible filters."""
        conditions = []
        params = []

        query = """
            SELECT id, bank_name, date, time, name, description, amount, category, balance,
                   reference_id, import_date
            FROM transactions
            WHERE 1=1
        """

        if filters:
            if 'bank_name' in filters:
                conditions.append("bank_name = ?")
                params.append(filters['bank_name'])

            if 'date_from' in filters:
                conditions.append("date >= ?")
                params.append(filters['date_from'])

            if 'date_to' in filters:
                conditions.append("date <= ?")
                params.append(filters['date_to'])

            if 'category' in filters:
                conditions.append("category = ?")
                params.append(filters['category'])

            if 'description_like' in filters:
                conditions.append("description LIKE ?")
                params.append(f"%{filters['description_like']}%")

            if 'amount_min' in filters:
                conditions.append("amount >= ?")
                params.append(filters['amount_min'])

            if 'amount_max' in filters:
                conditions.append("amount <= ?")
                params.append(filters['amount_max'])

        if conditions:
            query += " AND " + " AND ".join(conditions)

        query += " ORDER BY date DESC, time DESC"

        if limit:
            query += f" LIMIT {limit}"
        if offset:
            if not limit:
                limit = -1  # SQLite unlimited
            query += f" OFFSET {offset}"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_spending_summary(self, bank_name: str = None, months: int = 3) -> Dict[str, Any]:
        """Get spending summary statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Date filters
            date_filter = ""
            params = []

            if months:
                from datetime import datetime, timedelta
                cutoff_date = (datetime.now() - timedelta(days=30*months)).date().isoformat()
                date_filter = "AND date >= ?"
                params.append(cutoff_date)

            bank_filter = ""
            if bank_name:
                bank_filter = "AND bank_name = ?"
                params.append(bank_name)

            # Total transactions and amounts
            cursor.execute(f'''
                SELECT COUNT(*), SUM(amount), AVG(amount)
                FROM transactions
                WHERE 1=1 {bank_filter} {date_filter}
            ''', params)

            total_count, total_amount, avg_amount = cursor.fetchone()

            # Category breakdown (top 5)
            cursor.execute(f'''
                SELECT category, COUNT(*), SUM(amount)
                FROM transactions
                WHERE amount < 0 {bank_filter} {date_filter}
                GROUP BY category
                ORDER BY ABS(SUM(amount)) DESC
                LIMIT 5
            ''', params)

            categories = []
            for row in cursor.fetchall():
                categories.append({
                    'category': row[0],
                    'count': row[1],
                    'total': row[2]
                })

            return {
                'total_transactions': total_count or 0,
                'total_amount': total_amount or 0.0,
                'average_transaction': avg_amount or 0.0,
                'time_period_months': months,
                'top_categories': categories,
                'bank_filter': bank_name
            }

    def export_to_csv(self, output_path: str, filters: Dict[str, Any] = None,
                     limit: int = None) -> str:
        """Export transactions to CSV file."""
        import pandas as pd

        # Query transactions using existing query method
        transactions = self.query_transactions(filters=filters, limit=limit)

        if not transactions:
            # Create empty CSV with proper headers
            df = pd.DataFrame(columns=['id', 'bank_name', 'date', 'time', 'name', 'description',
                                     'amount', 'category', 'balance', 'reference_id', 'import_date'])
        else:
            df = pd.DataFrame(transactions)

        # Ensure output path has .csv extension
        if not output_path.endswith('.csv'):
            output_path = f"{output_path}.csv"

        # Export to CSV
        df.to_csv(output_path, index=False)

        return output_path

    def get_db_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Transaction counts by bank
            cursor.execute('''
                SELECT bank_name, COUNT(*) as count, SUM(amount) as total
                FROM transactions
                GROUP BY bank_name
                ORDER BY count DESC
            ''')

            bank_stats = []
            for row in cursor.fetchall():
                bank_stats.append({
                    'bank': row[0],
                    'transactions': row[1],
                    'total_amount': row[2]
                })

            # Date range
            cursor.execute('SELECT MIN(date), MAX(date) FROM transactions')
            min_date, max_date = cursor.fetchone()

            return {
                'banks': bank_stats,
                'date_range': {
                    'from': min_date,
                    'to': max_date
                }
            }

# Global database instance
_db = None

def get_database(db_path: str = None) -> FinSightDatabase:
    """Get global database instance."""
    global _db
    if _db is None:
        _db = FinSightDatabase(db_path)
    return _db

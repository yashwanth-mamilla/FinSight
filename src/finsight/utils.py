def load_expenses_from_csv(csv_path):
    """Load ExpenseItems from unified CSV."""
    import csv
    from datetime import datetime
    from .models import ExpenseItem

    expenses = []
    with open(csv_path, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            try:
                date = datetime.strptime(row['Date'], '%Y-%m-%d').date()
                time = row.get('Time', '00:00:00') or '00:00:00'
                name = row.get('Name', '')
                description = row.get('Description', '')
                amount = float(row['Amount'])
                category = row.get('Category', 'Uncategorized')
                person_name = row.get('Person', None)
                if person_name == '':
                    person_name = None

                expense = ExpenseItem(
                    date=date, time=time, description=description, amount=amount,
                    category=category, person_name=person_name
                )
                expenses.append(expense)
            except ValueError as e:
                print(f"Skipping invalid row: {row}, error: {e}")
                continue
    return expenses

def write_expenses_convert(expense_items, name_or_path):
    """Write the list of ExpenseItems to CSV at the given path."""
    import pandas as pd

    # Convert the list of ExpenseItems to a list of dictionaries
    data = [{
        'Date': item.date.strftime('%Y-%m-%d'),
        'Time': item.time,
        'Name': item.name,
        'Description': item.description,
        'Amount': item.amount,
        'Category': item.category,
        'Person': item.person.name if item.person else '',
        'Split Details': str(item.split_details)
    } for item in expense_items]

    # Create a DataFrame
    df = pd.DataFrame(data)

    # Write to CSV
    output_path = name_or_path if name_or_path.endswith('.csv') else f"{name_or_path}.csv"
    df.to_csv(output_path, index=False)
    return output_path

def analyze_spending(expenses):
    """Analyzes and visualizes spending from ExpenseItem transactions, ignoring credits."""
    import pandas as pd
    import matplotlib.pyplot as plt

    # Convert ExpenseItem objects into a DataFrame
    data = [{
        "Date": expense.date,
        "Category": str(expense.category),
        "Merchant": expense.name,  
        "Amount": expense.amount,
    } for expense in expenses]

    df = pd.DataFrame(data)

    # Ensure Date column is in datetime format
    df["Date"] = pd.to_datetime(df["Date"])

    # Filter out credits (negative values)
    df = df[df["Amount"] > 0]

    if df.empty:
        print("No debit transactions to analyze.")
        return

    # Total spending per category
    category_spending = df.groupby("Category")["Amount"].sum().sort_values(ascending=False)

    # Top merchants by spending
    merchant_spending = df.groupby("Merchant")["Amount"].sum().sort_values(ascending=False).head(10)

    # Spending trend over time
    df["Month"] = df["Date"].dt.to_period("M")
    monthly_spending = df.groupby("Month")["Amount"].sum()

    # Display Data
    print("\n📊 Category-wise Spending (Debits Only):\n", category_spending.to_string())
    print("\n🏪 Top Merchants by Spending (Debits Only):\n", merchant_spending.to_string())
    print("\n📅 Monthly Spending Trend (Debits Only):\n", monthly_spending.to_string())

    # Visualizations (optional, show only if in interactive mode)
    try:
        # Spending by Category
        plt.figure(figsize=(10, 5))
        category_spending.plot(kind="bar", color='skyblue')
        plt.title("Total Spending Per Category (Debits Only)")
        plt.ylabel("Amount (₹)")
        plt.xlabel("Category")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()

        # Spending Trend Over Time
        plt.figure(figsize=(10, 5))
        monthly_spending.plot(kind="line", marker="o", color='green')
        plt.title("Spending Trend Over Time (Debits Only)")
        plt.ylabel("Amount (₹)")
        plt.xlabel("Month")
        plt.grid(True)
        plt.tight_layout()
        plt.show()

        # Top Merchants
        plt.figure(figsize=(10, 5))
        merchant_spending.plot(kind="bar", color='orange')
        plt.title("Top Merchants by Spending (Debits Only)")
        plt.ylabel("Amount (₹)")
        plt.xlabel("Merchant")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()
    except Exception as e:
        print(f"Could not display plots: {e}. Try running in interactive environment.")

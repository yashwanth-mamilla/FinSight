#!/usr/bin/env python3
"""
Test script for FinSight AI categorization functionality.
Tests both extract_name_ai() and categorize_transaction_with_ai() functions.

Run with: python -m pytest tests/test_ai_categorization.py -v
"""

import sys
import time
sys.path.insert(0, 'src')

def test_ai_categorization():
    """Test AI-enabled categorization vs rule-based categorization"""

    from finsight.models import extract_name_ai, categorize_transaction_with_ai, ENABLE_AI
    from finsight.config import MERCHANT_NAMES, CATEGORIES
    from finsight.models import extract_name, categorize_transaction

    test_transactions = [
        ("swiggy order at taj maral near mathikere bengaluru karnataka india", "Swiggy", "Food and groceries"),
        ("uber trip from koramangala to marathahalli via whitefield", "Uber", "Transport"),
        ("netflix subscription renewal bill", "Netflix", "Entertainment"),
        ("amazon.in order for wireless earbuds", "Amazon", "Shopping"),
        ("starbucks coffee at koramangala forum", "Starbucks", "Food and groceries"),
        ("zomato recharge via bottomsheet android app", "Zomato", "Food and groceries"),
        ("icici bank atm withdrawal at koramangala", "ICICI Bank", "Bank Fees"),
        ("swiggy instamart order vegetables and milk", "Swiggy", "Food and groceries"),
        ("ola cab ride to airport", "Ola", "Transport"),
        ("zepto delivery order", "", "Food and groceries"),  # Should extract merchant
        ("puma sports shoes online purchase", "Puma", "Shopping"),
        ("cult.fit premium membership renewal", "Cult.fit", "Healthcare"),
        ("openai chatgpt subscription", "OPENAI", "Education")
    ]

    print("🐧 FinSight AI Categorization Testing")
    print("=" * 60)
    print(f"ENABLE_AI = {ENABLE_AI}")
    print(f"Ollama model: llama3.2")
    print()

    results = []

    for i, (description, expected_merchant, expected_category) in enumerate(test_transactions, 1):
        print(f"🧪 Test {i:2d}: '{description[:50]}{'...' if len(description) > 50 else ''}'")

        # Rule-based categorization (fallback)
        rule_name = extract_name(description)
        rule_category = categorize_transaction(None, description)

        # AI categorization (if enabled)
        start_time = time.time()

        try:
            ai_name = extract_name_ai(description) if ENABLE_AI else rule_name
            ai_category = categorize_transaction_with_ai(ai_name, description) if ENABLE_AI else rule_category
            ai_time = time.time() - start_time
            ai_status = "✅"
        except Exception as e:
            ai_name = rule_name
            ai_category = rule_category
            ai_time = time.time() - start_time
            ai_status = f"❌ ({e})"
            print(f"      Error: {e}")

        results.append({
            'description': description,
            'expected_merchant': expected_merchant,
            'expected_category': expected_category,
            'rule_name': rule_name,
            'rule_category': rule_category,
            'ai_name': ai_name,
            'ai_category': ai_category,
            'ai_time': ai_time,
            'ai_status': ai_status
        })

        print(f"   Expected:  '{expected_merchant}' → {expected_category}")
        print(f"   Rule-based: '{rule_name}' → {rule_category}")
        print(f"   AI-powered:  '{ai_name}' → {ai_category} ({ai_time:.2f}s) {ai_status}")
        print()

    # Summary
    print("📊 SUMMARY REPORT")
    print("-" * 50)

    ai_categories = [r['ai_category'] for r in results if r['ai_status'] == "✅"]
    unique_categories = set(ai_categories)
    category_counts = {cat: ai_categories.count(cat) for cat in unique_categories}

    successful_tests = len([r for r in results if r['ai_status'] == "✅"])
    avg_time = sum(r['ai_time'] for r in results if r['ai_status'] == "✅") / max(successful_tests, 1)

    print(f"Total tests: {len(test_transactions)}")
    print(f"AI successful: {successful_tests}/{len(test_transactions)}")
    if ai_categories:
        print(f"Average time: {avg_time:.2f}s per transaction")
        print(f"Categories used: {len(unique_categories)}")
        print(f"Top categories: {sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]}")

    # Unique merchant names found
    unique_ai_names = set([r['ai_name'] for r in results if r['ai_name'] and r['ai_status'] == "✅"])
    print(f"Merchants identified: {len(unique_ai_names)}")

    return results

def test_ai_disabled():
    """Test that AI functions fall back when ENABLE_AI=False"""

    # Temporarily disable AI
    from finsight import config
    original_value = config.ENABLE_AI
    config.ENABLE_AI = False

    try:
        from finsight.models import extract_name_ai, categorize_transaction_with_ai

        # These should return fallback values or empty strings
        name = extract_name_ai("test transaction")
        category = categorize_transaction_with_ai("", "test transaction")

        print(f"AI Disabled Test - Name: '{name}', Category: '{category}'")
        assert name == "" or name is None  # Should return fallback
        assert category == "Uncategorized" or category is None

    finally:
        # Restore original value
        config.ENABLE_AI = original_value

if __name__ == "__main__":
    test_ai_categorization()
    print("\n" + "="*60)

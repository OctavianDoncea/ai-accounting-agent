from app.models.chart_of_accounts import AccountType, NormalBalance

CHART_OF_ACCOUNTS_SEED = [
    # Assets (debit normal balance)
    {'code': '1000', 'name': 'Cash', 'type': AccountType.ASSET, 'balance': NormalBalance.DEBIT, 'description': 'Cash on hand and in checking accounts'},
    {'code': '1010', 'name': 'Bank Account - Operating', 'type': AccountType.ASSET, 'balance': NormalBalance.DEBIT, 'description': 'Primary business operating account'},
    {'code': '1020', 'name': 'Bank Account - Savings', 'type': AccountType.ASSET, 'balance': NormalBalance.DEBIT, 'description': 'Business savings account'},
    {'code': '1100', 'name': 'Accounts Receivable', 'type': AccountType.ASSET, 'balance': NormalBalance.DEBIT, 'description': 'Money owed by customers'},
    {'code': '1200', 'name': 'Inventory', 'type': AccountType.ASSET, 'balance': NormalBalance.DEBIT, 'description': 'Goods held for sale'},
    {'code': '1300', 'name': 'Prepaid Expenses', 'type': AccountType.ASSET, 'balance': NormalBalance.DEBIT, 'description': 'Expenses paid in advance (insurance, rent, etc.)'},
    {'code': '1500', 'name': 'Office Equipment', 'type': AccountType.ASSET, 'balance': NormalBalance.DEBIT, 'description': 'Computers, furniture, office machines'},
    {'code': '1510', 'name': 'Accumulated Depreciation - Equipment', 'type': AccountType.ASSET, 'balance': NormalBalance.CREDIT, 'description': 'Contra-asset: accumulated depreciation'},

    # Liabilities (credit normal balance)
    {'code': '2000', 'name': 'Accounts Payable', 'type': AccountType.LIABILITY, 'balance': NormalBalance.CREDIT, 'description': 'Money owed to vendors and suppliers'},
    {'code': '2100', 'name': 'Credit Card Payable', 'type': AccountType.LIABILITY, 'balance': NormalBalance.CREDIT, 'description': 'Outstanding credit card balances'},
    {'code': '2200', 'name': 'Sales Tax Payable', 'type': AccountType.LIABILITY, 'balance': NormalBalance.CREDIT, 'description': 'Sales tax collected and owed to authorities'},
    {'code': '2300', 'name': 'Payroll liabilities', 'type': AccountType.LIABILITY, 'balance': NormalBalance.CREDIT, 'description': 'Wages, taxes, amd benefits owed to employees'},
    {'code': '2500', 'name': 'Short-Term Loans', 'type': AccountType.LIABILITY, 'balance': NormalBalance.CREDIT, 'description': 'Loans due within a year'},
    {'code': '2600', 'name': 'Long-Term Loans', 'type': AccountType.LIABILITY, 'balance': NormalBalance.CREDIT, 'description': 'Loans due after one year'},

    # Equity (credit normal balance)
    {'code': '3000', 'name': "Owner's Equity", 'type': AccountType.EQUITY, 'balance': NormalBalance.CREDIT, 'description': "Owner's invested capital"},
    {'code': '3100', 'name': 'Retained Earnings', 'type': AccountType.EQUITY, 'balance': NormalBalance.CREDIT, 'description': 'Accumulated profits not distributed to owners'},

    # Revenue (credit normal balance)
    {'code': '4000', 'name': 'Sales Revenue', 'type': AccountType.REVENUE, 'balance': NormalBalance.CREDIT, 'description': 'Income from sales of goods and services'},
    {'code': '4100', 'name': 'Service Revenue', 'type': AccountType.REVENUE, 'balance': NormalBalance.CREDIT, 'description': 'Income from service-based work'},
    {'code': '4200', 'name': 'Interest Income', 'type': AccountType.REVENUE, 'balance': NormalBalance.CREDIT, 'description': 'Interest earned on bank balances and investments'},
    {'code': '4900', 'name': 'Other Income', 'type': AccountType.REVENUE, 'balance': NormalBalance.CREDIT, 'description': 'Miscellaneous income'},

    # Cost of goods sold (debit normal balance)
    {'code': '5000', 'name': 'Cost of Goods Sold', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Direct costs of producing goods sold'},
    {'code': '5100', 'name': 'Purchases - Inventory', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Inventory purchases for resale'},

    # Operating expenses (debit normal balance)
    {'code': '6000', 'name': 'Rent Expense', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Rent for office space or facility'},
    {'code': '6010', 'name': 'Utilities expense', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Electricity, water, gas, internet'},
    {'code': '6020', 'name': 'Telephone Expense', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Phone and mobile services'},
    {'code': '6100', 'name': 'Salaries and Wages', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Employee compensation'},
    {'code': '6110', 'name': "payroll Taxes", 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Employer-pais payroll taxes'},
    {'code': '6200', 'name': 'Software Subscriptions', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'SaaS tools, cloud services, software licenses'},
    {'code': '6210', 'name': 'Cload Hosting', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'AWS, GCP, Azure, hosting providers'},
    {'code': '6300', 'name': 'Office Supplies', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Stationery, consumables'},
    {'code': '6400', 'name': 'Travel Expense', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Flights, hotels, ground transportation'},
    {'code': '6410', 'name': 'Meals and Entertainment', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Business meals and entertainment'},
    {'code': '6500', 'name': 'Marketing and Advertising', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Ads, campaigns, content'},
    {'code': '6600', 'name': 'Professional Fees', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Legal, accounting, consulting fees'},
    {'code': '6700', 'name': 'Insurance Expense', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Business, liability, health insurance'},
    {'code': '6800', 'name': 'Depreciation Expense', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Depreciation of long-term assets'},
    {'code': '6900', 'name': 'Bank Fees', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Bank charges, wire fees, merchant fees'},
    {'code': '6920', 'name': 'Sales Tax Expense', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Non-recoverable sales tax paid on purchases'},
    {'code': '7000', 'name': 'Repairs and Maintenance', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Repairs to equipment, building, or facilities'},
    {'code': '7100', 'name': 'Training and Education', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Courses, conferences, books'},
    {'code': '7900', 'name': 'Miscellaneous Expense', 'type': AccountType.EXPENSE, 'balance': NormalBalance.DEBIT, 'description': 'Uncategorized expoenses'},
]
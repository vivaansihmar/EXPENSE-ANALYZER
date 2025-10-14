# ml/finance_model.py
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import os
from datetime import datetime

def generate_finance_graphs(df=None, csv_path=None, static_path="static"):
    """
    Generates finance graphs.
    - Accepts either a Pandas DataFrame (df) or a CSV path.
    - Automatically saves graphs inside `static_path`.
    """

    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import os
    from sklearn.linear_model import LinearRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error

    
    # 1. LOAD DATA
    
    if df is None:
        if csv_path is None:
            raise ValueError("Please provide either a DataFrame or a CSV path.")
        df = pd.read_csv(csv_path)

    df.columns = [c.strip().lower() for c in df.columns]
    if 'date' not in df.columns:
        df['date'] = pd.to_datetime(df.get('created_at', datetime.utcnow()), errors='coerce')

    df = df.dropna(subset=['date'])
    df['amount'] = df['amount'].astype(float)
    df['type'] = df.get('type', 'expense').str.lower()
    df['category'] = df.get('category', df.get('title', 'Other'))
    df['month'] = df['date'].dt.to_period('M').astype(str)

    os.makedirs(static_path, exist_ok=True)

    
    #2. MONTHLY INCOME VS EXPENSE
    
    monthly_summary = df.groupby(['month', 'type'])['amount'].sum().unstack(fill_value=0)
    plt.figure(figsize=(10, 5))
    monthly_summary.plot(kind='bar', ax=plt.gca())
    plt.title("Monthly Income vs Expense")
    plt.ylabel("Amount (₹)")
    plt.xlabel("Month")
    plt.tight_layout()
    plt.savefig(f"{static_path}/monthly_income_expense.png")
    plt.close()


    # 3. CATEGORY PIE 

    expense_data = df[df['type'] == 'expense']
    if not expense_data.empty:
        cat_summary = expense_data.groupby('category')['amount'].sum().sort_values(ascending=False)
        plt.figure(figsize=(6, 6))
        cat_summary.plot.pie(autopct='%1.1f%%', startangle=90, shadow=True)
        plt.title("Category-wise Expense Distribution")
        plt.ylabel("")
        plt.tight_layout()
        plt.savefig(f"{static_path}/category_expense_pie.png")
        plt.close()


    if not expense_data.empty:
        expense_trend = expense_data.groupby('month')['amount'].sum().reset_index()
        expense_trend['month_num'] = np.arange(len(expense_trend))

        if len(expense_trend) > 2:
            X = expense_trend[['month_num']]
            y = expense_trend['amount']

            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
            model = LinearRegression()
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            mae = mean_absolute_error(y_test, y_pred)

            
            next_month = [[expense_trend['month_num'].max() + 1]]
            predicted_expense = model.predict(next_month)[0]

            plt.figure(figsize=(8, 5))
            plt.plot(expense_trend['month_num'], y, marker='o', label='Actual')
            plt.plot(expense_trend['month_num'], model.predict(X), '--', color='orange', label='Predicted')
            plt.scatter(next_month, predicted_expense, color='red', s=100, label='Next Month Forecast')
            plt.legend()
            plt.title("Expense Forecast using Linear Regression")
            plt.xlabel("Month Index")
            plt.ylabel("Expense (₹)")
            plt.grid(True)
            plt.tight_layout()
            plt.savefig(f"{static_path}/expense_forecast.png")
            plt.close()

    print("✅ Graphs generated successfully for user data!")
    return True


    
    # 6. SUMMARY
    
    summary = {
        "Mean Absolute Error": mae,
        "Predicted Next Month Expense (₹)": predicted_expense,
        "Graphs Saved In": os.path.abspath(static_path)
    }

    print("\n✅ Graphs generated successfully:")
    print(f"📊 Monthly Income vs Expense → {static_path}/monthly_income_expense.png")
    print(f"🥧 Category Expense Pie → {static_path}/category_expense_pie.png")
    print(f"📈 Expense Forecast → {static_path}/expense_forecast.png\n")

    return summary


if __name__ == "__main__":
    # Auto-detect correct base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_output = os.path.join(base_dir, "finance_graphs_output")

    # Run generator
    results = generate_finance_graphs(csv_path=None, static_path=static_output)
    print("\nSummary:\n", results)

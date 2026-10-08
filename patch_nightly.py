with open(r'backend\data\scheduler.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if i == 537 and 'tech_result  = analyze_technical(ohlcv_df)' in line:
        patch = """            from backend.data.nse_live import get_delivery_data
            delivery_data = await loop.run_in_executor(None, lambda: get_delivery_data(symbol))
            delivery_pct = None
            if delivery_data and delivery_data.get("delivery_pct"):
                try:
                    delivery_pct = float(delivery_data["delivery_pct"])
                except:
                    pass

            tech_result  = analyze_technical(ohlcv_df, delivery_pct=delivery_pct)
"""
        new_lines.append(patch)
    else:
        new_lines.append(line)

with open(r'backend\data\scheduler.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

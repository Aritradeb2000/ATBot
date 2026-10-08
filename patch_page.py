with open(r'frontend\src\app\stock\[symbol]\page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('import("@/components/charts/TradingViewChart")', 'import("@/components/charts/NativeChart").then(mod => ({ default: mod.NativeChart }))')
text = text.replace('const TradingViewChart = dynamic', 'const NativeChart = dynamic')
text = text.replace('<TradingViewChart ', '<NativeChart ')

with open(r'frontend\src\app\stock\[symbol]\page.tsx', 'w', encoding='utf-8') as f:
    f.write(text)

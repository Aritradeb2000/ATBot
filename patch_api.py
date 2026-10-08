with open(r'frontend\src\lib\api.ts', 'a', encoding='utf-8') as f:
    f.write("\nexport const marketApi = {\n  getOHLCV: async (symbol: string, period: string, interval: string) => {\n    const res = await api.get(`/api/ohlcv/${symbol.toUpperCase()}`, { params: { period, interval } });\n    return res.data;\n  }\n};\n")

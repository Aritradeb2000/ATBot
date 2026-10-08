import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import { marketApi } from '@/lib/api';

interface NativeChartProps {
    symbol: string;
}

export const NativeChart: React.FC<NativeChartProps> = ({ symbol }) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const [interval, setInterval] = useState<string>('1d');
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    const chartRef = useRef<IChartApi | null>(null);
    const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

    const [isDark, setIsDark] = useState<boolean>(false);

    useEffect(() => {
        if (typeof window !== 'undefined') {
            const checkDark = () => document.documentElement.classList.contains('dark') || window.matchMedia('(prefers-color-scheme: dark)').matches;
            setIsDark(checkDark());
            
            const observer = new MutationObserver(mutations => {
                mutations.forEach(mutation => {
                    if (mutation.attributeName === 'class') setIsDark(checkDark());
                });
            });
            observer.observe(document.documentElement, { attributes: true });
            return () => observer.disconnect();
        }
    }, []);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // Initialize Chart
        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: isDark ? '#D1D5DB' : '#374151',
            },
            grid: {
                vertLines: { color: isDark ? '#374151' : '#E5E7EB' },
                horzLines: { color: isDark ? '#374151' : '#E5E7EB' },
            },
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
            crosshair: {
                mode: 1, // Normal crosshair
            },
        });
        
        chartRef.current = chart;

        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });
        candlestickSeriesRef.current = candlestickSeries;

        const volumeSeries = chart.addSeries(HistogramSeries, {
            color: '#26a69a',
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '', // set as an overlay by setting a blank priceScaleId
            scaleMargins: {
                top: 0.8, // highest point of the series will be at 80% of the chart
                bottom: 0,
            },
        });
        volumeSeriesRef.current = volumeSeries;

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ 
                    width: chartContainerRef.current.clientWidth,
                    height: chartContainerRef.current.clientHeight
                });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, [isDark]);

    useEffect(() => {
        let isMounted = true;
        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                // Determine maximum period allowed by backend mapping
                let period = 'max';
                
                const response = await marketApi.getOHLCV(symbol, period, interval);
                
                if (isMounted && response && Array.isArray(response)) {
                    // Sort ascending by time
                    const sortedData = [...response].sort((a, b) => {
                        const timeA = typeof a.time === 'string' ? new Date(a.time).getTime() : a.time * 1000;
                        const timeB = typeof b.time === 'string' ? new Date(b.time).getTime() : b.time * 1000;
                        return timeA - timeB;
                    });

                    // Prepare volume data with correct color based on candlestick
                    const volumeData = sortedData.map(item => ({
                        time: item.time as Time,
                        value: item.volume,
                        color: item.close >= item.open ? '#26a69a80' : '#ef535080',
                    }));

                    candlestickSeriesRef.current?.setData(sortedData);
                    volumeSeriesRef.current?.setData(volumeData);
                    
                    // Fit content
                    chartRef.current?.timeScale().fitContent();
                }
            } catch (err) {
                console.error("Failed to fetch chart data:", err);
                if (isMounted) setError("Failed to load chart data");
            } finally {
                if (isMounted) setLoading(false);
            }
        };

        fetchData();

        return () => {
            isMounted = false;
        };
    }, [symbol, interval]);

    const intervals = [
        { label: '5m', value: '5m' },
        { label: '15m', value: '15m' },
        { label: '30m', value: '30m' },
        { label: '1H', value: '1h' },
        { label: '1D', value: '1d' },
        { label: '1W', value: '1wk' },
    ];

    return (
        <div className="relative w-full h-[500px] bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
                <div className="flex items-center space-x-4">
                    <h3 className="font-bold text-gray-900 dark:text-white text-lg">{symbol}</h3>
                    <div className="flex bg-gray-200 dark:bg-gray-700 rounded-md p-1">
                        {intervals.map((intv) => (
                            <button
                                key={intv.value}
                                onClick={() => setInterval(intv.value)}
                                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                                    interval === intv.value 
                                        ? 'bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 shadow-sm' 
                                        : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-300 dark:hover:bg-gray-600'
                                }`}
                            >
                                {intv.label}
                            </button>
                        ))}
                    </div>
                </div>
                {loading && (
                    <div className="text-xs text-gray-500 dark:text-gray-400 animate-pulse flex items-center">
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Loading...
                    </div>
                )}
            </div>
            <div className="relative flex-grow w-full">
                {error && (
                    <div className="absolute inset-0 flex items-center justify-center bg-gray-50/80 dark:bg-gray-900/80 z-10">
                        <div className="text-red-500 font-medium">{error}</div>
                    </div>
                )}
                <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />
            </div>
        </div>
    );
};

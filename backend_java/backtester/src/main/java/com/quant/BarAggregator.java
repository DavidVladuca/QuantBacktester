package com.quant;

import java.util.HashMap;
import java.util.Map;

public class BarAggregator {

    private static class PartialBar {
        String symbol;
        long bucketStart;
        double high;
        double low;
        double close;
        double volume;

        PartialBar(Main.MarketEvent event, long bucketStart) {
            this.symbol = event.getSymbol();
            this.bucketStart = bucketStart;

            double price = event.getPrice();
            double eventHigh = event.getHigh() > 0 ? event.getHigh() : price;
            double eventLow = event.getLow() > 0 ? event.getLow() : price;

            this.high = eventHigh;
            this.low = eventLow;
            this.close = price;
            this.volume = event.getVolume();
        }

        void update(Main.MarketEvent event) {
            double price = event.getPrice();
            double eventHigh = event.getHigh() > 0 ? event.getHigh() : price;
            double eventLow = event.getLow() > 0 ? event.getLow() : price;

            this.high = Math.max(this.high, eventHigh);
            this.low = Math.min(this.low, eventLow);
            this.close = price;
            this.volume += event.getVolume();
        }

        Main.MarketEvent toMarketEvent() {
            return new Main.MarketEvent(
                "MARKET_DATA",
                symbol,
                bucketStart,
                close,
                high,
                low,
                volume,
                0,
                0,
                0,
                0
            );
        }
    }

    private final long bucketSizeMs;
    private final Map<String, PartialBar> activeBars = new HashMap<>();

    public BarAggregator(int timeframeMinutes) {
        if (timeframeMinutes <= 0) {
            throw new IllegalArgumentException("timeframeMinutes must be > 0");
        }

        this.bucketSizeMs = timeframeMinutes * 60_000L;
    }

    public Main.MarketEvent update(Main.MarketEvent event) {
        if (!"MARKET_DATA".equals(event.getType())) {
            return null;
        }

        long bucketStart = (event.getTimestamp() / bucketSizeMs) * bucketSizeMs;
        String symbol = event.getSymbol();

        PartialBar currentBar = activeBars.get(symbol);

        if (currentBar == null) {
            activeBars.put(symbol, new PartialBar(event, bucketStart));
            return null;
        }

        if (currentBar.bucketStart == bucketStart) {
            currentBar.update(event);
            return null;
        }

        Main.MarketEvent completedBar = currentBar.toMarketEvent();
        activeBars.put(symbol, new PartialBar(event, bucketStart));

        return completedBar;
    }
}
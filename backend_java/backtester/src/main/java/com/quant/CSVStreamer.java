package com.quant;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.File;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.temporal.ChronoField;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.BlockingQueue;

public class CSVStreamer {

    private final BlockingQueue<Main.MarketEvent> eventQueue;
    private final String[] csvFiles;

    // date format (since format may vary)
    private static final DateTimeFormatter DATE_FORMATTER = new DateTimeFormatterBuilder()
            .appendPattern("yyyy-MM-dd HH:mm:ss")
            .optionalStart()
            .appendFraction(ChronoField.MICRO_OF_SECOND, 1, 6, true)
            .optionalEnd()
            .toFormatter();

    public CSVStreamer(BlockingQueue<Main.MarketEvent> eventQueue, String[] csvFiles) {
        this.eventQueue = eventQueue;
        this.csvFiles = csvFiles;
    }

    public void start() {
        List<Main.MarketEvent> historicalEvents = new ArrayList<>();

        try {
            for (String file : csvFiles) {
                System.out.println("[CSV STREAMER] Loading data from: " + file);
                
                String fileName = new File(file).getName();
                String symbol = fileName.split("[_\\.]")[0].toUpperCase();
                boolean isMicroQuote = fileName.contains("micro");

                BufferedReader br = new BufferedReader(new FileReader(file));
                String line;
                boolean isHeader = true;

                while ((line = br.readLine()) != null) {
                    if (isHeader) { isHeader = false; continue; }
                    
                    String[] values = line.split(",");

                    if (isMicroQuote && values.length < 5) continue; 
                    if (!isMicroQuote && values.length < 6) continue;
                    
                    long timestamp;
                    try {
                        LocalDateTime dateTime = LocalDateTime.parse(values[0], DATE_FORMATTER);
                        timestamp = dateTime.toInstant(ZoneOffset.UTC).toEpochMilli();
                    } catch (Exception e) {
                        continue; // skip lines with bad timestamps
                    }

                    if (isMicroQuote) {
                        // Quotes format -> timestamp, bid_price, bid_size, ask_price, ask_size
                        double bidPrice = Double.parseDouble(values[1]);
                        double bidSize = Double.parseDouble(values[2]);
                        double askPrice = Double.parseDouble(values[3]);
                        double askSize = Double.parseDouble(values[4]);
                        
                        // treat the mid-price as the "price" for standard execution logic
                        double midPrice = (bidPrice + askPrice) / 2.0;

                        historicalEvents.add(new Main.MarketEvent("MARKET_DATA", symbol, timestamp, midPrice, 0, 0, 0, bidPrice, askPrice, bidSize, askSize));
                    } else {
                        // Macro format -> timestamp, open, high, low, close, volume, trade_count, vwap
                        double high = Double.parseDouble(values[2]);
                        double low = Double.parseDouble(values[3]);
                        double close = Double.parseDouble(values[4]);
                        double volume = Double.parseDouble(values[5]);

                        historicalEvents.add(new Main.MarketEvent("MARKET_DATA", symbol, timestamp, close, high, low, volume, 0, 0, 0, 0));
                    }
                }
                br.close();
            }

            System.out.println("[CSV STREAMER] Sorting " + historicalEvents.size() + " total events chronologically...");
            historicalEvents.sort(Comparator.comparingLong(Main.MarketEvent::getTimestamp));

            for (Main.MarketEvent event : historicalEvents) {
                eventQueue.put(event);
            }

            eventQueue.put(new Main.MarketEvent("END_OF_STREAM", "SYSTEM", Long.MAX_VALUE, 0, 0, 0, 0, 0, 0, 0, 0));

        } catch (Exception e) {
            System.err.println("[ERROR] CSV Streamer failed: " + e.getMessage());
            e.printStackTrace();
        }
    }
}
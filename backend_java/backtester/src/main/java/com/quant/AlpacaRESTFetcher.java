package com.quant;

import com.google.gson.Gson;
import com.google.gson.annotations.SerializedName;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.BlockingQueue;

public class AlpacaRESTFetcher {

    private final BlockingQueue<Main.MarketEvent> eventQueue;
    private final String[] tickers;
    private final int limit;
    private final int timeframeMinutes;

    private final String apiKey;
    private final String apiSecret;
    
    // Alpaca Market Data endpoint 
    private static final String BASE_URL = "https://data.alpaca.markets/v2/stocks/bars";

    // for converting the JSON response into Java objects
    public static class AlpacaResponse {
        public Map<String, List<AlpacaBar>> bars;
    }

    public static class AlpacaBar {
        @SerializedName("t") public String t; // Timestamp 
        @SerializedName("o") public double o; // Open
        @SerializedName("h") public double h; // High
        @SerializedName("l") public double l; // Low
        @SerializedName("c") public double c; // Close
        @SerializedName("v") public double v; // Volume
    }

    public AlpacaRESTFetcher(BlockingQueue<Main.MarketEvent> eventQueue, String[] tickers, int limit, int timeframeMinutes) {
        this.eventQueue = eventQueue;
        this.tickers = tickers;
        this.limit = limit;
        this.timeframeMinutes = timeframeMinutes;

        // load the config.properties file
        try (java.io.FileInputStream fis = new java.io.FileInputStream("config.properties")) {
            java.util.Properties prop = new java.util.Properties();
            prop.load(fis);
            this.apiKey = prop.getProperty("alpaca.key");
            this.apiSecret = prop.getProperty("alpaca.secret");
        } catch (Exception e) {
            throw new RuntimeException("Could not load Alpaca API keys for REST hydration: " + e.getMessage());
        }
    }

    private String alpacaTimeframe() {
        if (timeframeMinutes % 60 == 0) {
            return (timeframeMinutes / 60) + "Hour";
        }

        return timeframeMinutes + "Min";
    }

    public void start() {
        try {
            HttpClient client = HttpClient.newHttpClient();
            Gson gson = new Gson();
            List<Main.MarketEvent> historicalEvents = new ArrayList<>();

            for (String ticker : tickers) {
                System.out.println("[REST FETCHER] Fetching warmup data for: " + ticker);
                
                String encodedTicker = java.net.URLEncoder.encode(ticker, java.nio.charset.StandardCharsets.UTF_8);
                String url = String.format(
                    "%s?symbols=%s&timeframe=%s&limit=%d",
                    BASE_URL,
                    encodedTicker,
                    alpacaTimeframe(),
                    limit
                );
                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(url))
                        .header("APCA-API-KEY-ID", apiKey)
                        .header("APCA-API-SECRET-KEY", apiSecret)
                        .GET().build();

                HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

                if (response.statusCode() == 200) {
                    AlpacaResponse alpacaData = gson.fromJson(response.body(), AlpacaResponse.class);
                    if (alpacaData.bars != null && alpacaData.bars.containsKey(ticker)) {
                        List<AlpacaBar> bars = alpacaData.bars.get(ticker);
                        System.out.println("[HYDRATOR] Found " + bars.size() + " bars for " + ticker);
                        
                        for (AlpacaBar bar : bars) {
                            long ts = java.time.Instant.parse(bar.t).toEpochMilli();

                            historicalEvents.add(new Main.MarketEvent(
                                "MARKET_DATA",
                                ticker,
                                ts,
                                bar.c,
                                bar.h,
                                bar.l,
                                bar.v,
                                0,
                                0,
                                0,
                                0
                            ));
                        }
                    }
                } else {
                    System.err.println("[ERROR] Failed fetch for " + ticker + " Code: " + response.statusCode());
                }
            }

            // chronologically sort the combined list so Python sees the market move in order
            historicalEvents.sort(java.util.Comparator.comparingLong(Main.MarketEvent::getTimestamp));

            for (Main.MarketEvent event : historicalEvents) {
                eventQueue.put(event);
            }

            System.out.println("[REST FETCHER] Total Hydration complete. Ingested " + historicalEvents.size() + " bars.");
            eventQueue.put(new Main.MarketEvent(
                "HYDRATION_COMPLETE",
                "SYSTEM",
                Long.MAX_VALUE,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0
            ));
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
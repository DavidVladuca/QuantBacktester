package com.quant; 

import java.net.URI; 
import java.net.http.HttpClient; 
import java.net.http.WebSocket; 
import java.util.concurrent.CompletionStage; 
import java.util.concurrent.BlockingQueue; 
import java.util.Properties; 
import java.io.FileInputStream; 
import com.google.gson.Gson; 
import com.google.gson.JsonArray; 
import com.google.gson.JsonElement; 
import com.google.gson.JsonObject; 
import java.time.Instant; 
import java.util.stream.Collectors;
import java.util.Arrays;

public class LiveMarketStreamer implements WebSocket.Listener { 
    private final BlockingQueue<Main.MarketEvent> eventQueue; 
    private final String[] tickers;
    private final Gson gson = new Gson(); 
    private String apiKey; 
    private String apiSecret; 
    private StringBuilder messageBuffer = new StringBuilder(); 

    public LiveMarketStreamer(BlockingQueue<Main.MarketEvent> eventQueue, String[] tickers) { 
        this.eventQueue = eventQueue; 
        this.tickers = tickers;
        try (FileInputStream fis = new FileInputStream("config.properties")) { 
            Properties prop = new Properties(); 
            prop.load(fis); 
            this.apiKey = prop.getProperty("alpaca.key"); 
            this.apiSecret = prop.getProperty("alpaca.secret"); 
        } catch (Exception e) { 
            System.err.println("CRITICAL: Could not load API keys for WebSocket!"); 
        } 
    } 

    public void start() { 
        HttpClient client = HttpClient.newHttpClient(); 
        client.newWebSocketBuilder() 
            .buildAsync(URI.create("wss://stream.data.alpaca.markets/v2/iex"), this)             
            .join(); 
    } 

    @Override 
    public void onOpen(WebSocket webSocket) { 
        System.out.println("  [WEBSOCKET] Connected to Alpaca Stock Market Data!");
        String authMsg = "{\"action\": \"auth\", \"key\": \"" + apiKey + "\", \"secret\": \"" + apiSecret + "\"}"; 
        webSocket.sendText(authMsg, true); 
        WebSocket.Listener.super.onOpen(webSocket); 
    } 

    @Override 
    public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) { 
        messageBuffer.append(data); 
        
        if (last) { 
            String message = messageBuffer.toString(); 
            messageBuffer.setLength(0); 
            
            try { 
                JsonArray jsonArray = gson.fromJson(message, JsonArray.class); 
                for (JsonElement element : jsonArray) { 
                    JsonObject obj = element.getAsJsonObject(); 
                    
                    if (obj.has("T") && obj.get("T").getAsString().equals("success") && obj.has("msg")) { 
                        if (obj.get("msg").getAsString().equals("authenticated")) { 
                            System.out.println("  [WEBSOCKET] Authenticated. Subscribing to Live Bars...");
                            
                            // dynamically build the subscription string for the tickers
                            String symbolsList = Arrays.stream(tickers)
                                                       .map(t -> "\"" + t + "\"")
                                                       .collect(Collectors.joining(","));
                            
                            String subMsg = "{\"action\": \"subscribe\", \"bars\": [" + symbolsList + "]}";  
                            webSocket.sendText(subMsg, true); 
                        } 
                    } 
                    
                    else if (obj.has("T") && obj.get("T").getAsString().equals("b")) { 
                        String symbol = obj.get("S").getAsString(); 
                        double price = obj.get("c").getAsDouble();
                        double high = obj.get("h").getAsDouble();
                        double low = obj.get("l").getAsDouble();
                        double volume = obj.get("v").getAsDouble();

                        long timestamp = Instant.parse(obj.get("t").getAsString()).toEpochMilli(); 

                        Main.MarketEvent event = new Main.MarketEvent(
                            "MARKET_DATA",
                            symbol,
                            timestamp,
                            price,
                            high,
                            low,
                            volume,
                            0,
                            0,
                            0,
                            0
                        );

                        System.out.println(
                            "[ALPACA BAR] " + symbol +
                            " | price=" + price +
                            " | high=" + high +
                            " | low=" + low +
                            " | volume=" + volume
                        );

                        eventQueue.put(event);
                    }
                } 
            } catch (Exception e) { 
                System.err.println("[WEBSOCKET PARSE ERROR] " + e.getMessage());
                System.err.println("[RAW MESSAGE] " + message);
            } 
        } 
        return WebSocket.Listener.super.onText(webSocket, data, last); 
    } 

    @Override 
    public void onError(WebSocket webSocket, Throwable error) { 
        System.err.println("  [WEBSOCKET ERROR] " + error.getMessage()); 
        WebSocket.Listener.super.onError(webSocket, error); 
    } 
}
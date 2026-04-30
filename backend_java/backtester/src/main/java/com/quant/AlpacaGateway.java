package com.quant; 

import com.google.gson.Gson; 
import java.net.URI; 
import java.net.http.HttpClient; 
import java.net.http.HttpRequest; 
import java.net.http.HttpResponse; 
import java.util.HashMap; 
import java.util.Map; 
import java.util.Properties; 
import java.io.FileInputStream; 

public class AlpacaGateway implements ExecutionGateway { 
    private final String apiKey; 
    private final String apiSecret; 
    private final String baseUrl; 
    private final HttpClient httpClient; 
    private final Gson gson; 

    public AlpacaGateway() { 
        this.httpClient = HttpClient.newHttpClient(); 
        this.gson = new Gson(); 
        
        // load keys from config.properties file
        Properties prop = new Properties(); 
        try (FileInputStream fis = new FileInputStream("config.properties")) { 
            prop.load(fis); 
        } catch (Exception e) { 
            throw new RuntimeException("CRITICAL: Could not load config.properties file! " + e.getMessage()); 
        } 
        
        this.apiKey = prop.getProperty("alpaca.key"); 
        this.apiSecret = prop.getProperty("alpaca.secret"); 
        this.baseUrl = prop.getProperty("alpaca.url"); 
    } 

    @Override 
    public void execute(Order order, Main.MarketEvent currentMarket) { 
        try { 
            // map Order to Alpaca's JSON format
            Map<String, Object> orderData = new HashMap<>(); 
            orderData.put("symbol", order.getSymbol()); 
            orderData.put("qty", String.valueOf((int)order.getQuantity())); 
            orderData.put("side", order.getSide().toString().toLowerCase()); 
            orderData.put("type", order.getType().toString().toLowerCase()); 
            orderData.put("time_in_force", "day"); 

            String jsonBody = gson.toJson(orderData); 

            // HTTP request 
            HttpRequest request = HttpRequest.newBuilder() 
                .uri(URI.create(baseUrl + "/orders")) 
                .header("APCA-API-KEY-ID", apiKey) 
                .header("APCA-API-SECRET-KEY", apiSecret) 
                .header("Content-Type", "application/json") 
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody)) 
                .build(); 

            // send request + get response
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString()); 

            if (response.statusCode() == 200 || response.statusCode() == 201) { 
                order.addFill(order.getQuantity()); 
                System.out.println("  [ALPACA] Live Order Accepted: " + order.getSide() + " " + order.getSymbol()); 
            } else { 
                System.err.println("  [ALPACA] ORDER REJECTED: " + response.body()); 
            } 

        } catch (Exception e) { 
            System.err.println("  [ALPACA] Network Connection Failed: " + e.getMessage()); 
        } 
    } 
}
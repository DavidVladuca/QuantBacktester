package com.quant; 

public interface ExecutionGateway { 
    // take order and processes it against current market data
    void execute(Order order, Main.MarketEvent currentMarket); 
} 
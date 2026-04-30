package com.quant; 

public class SimulatedGateway implements ExecutionGateway { 

    @Override 
    public void execute(Order order, Main.MarketEvent currentMarket) { 
        // for backtesting, we simulate an instant perfect fill
        
        if (order.getStatus() == Order.Status.NEW) { 
            order.addFill(order.getQuantity()); 
            
            System.out.println("  [GATEWAY] Executed " + order.getSide() + " " + 
                               order.getFilledQuantity() + " shares of " + order.getSymbol() + 
                               " @ $" + order.getLimitPrice()); 
        } 
    } 
} 
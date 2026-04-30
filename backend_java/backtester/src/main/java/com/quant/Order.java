package com.quant;

public class Order {
    public enum Type { MARKET, LIMIT }
    public enum Side { BUY, SELL }
    public enum Status { NEW, PARTIALLY_FILLED, FILLED, CANCELED }

    private String id;
    private String symbol;
    private Side side;
    private Type type;
    private double quantity;
    private double filledQuantity;
    private double limitPrice;

    private double executionPrice;
    private double feesPaid;

    private Status status;

    public Order(String id, String symbol, Side side, Type type, double quantity, double limitPrice) {
        this.id = id;
        this.symbol = symbol;
        this.side = side;
        this.type = type;
        this.quantity = quantity;
        this.limitPrice = limitPrice;
        this.filledQuantity = 0.0;
        this.executionPrice = 0.0;
        this.feesPaid = 0.0;
        this.status = Status.NEW;
    }

    public String getId() { return id; }
    public String getSymbol() { return symbol; }
    public Side getSide() { return side; }
    public Type getType() { return type; }
    public double getQuantity() { return quantity; }
    public double getFilledQuantity() { return filledQuantity; }
    public double getLimitPrice() { return limitPrice; }
    public Status getStatus() { return status; }
    public double getExecutionPrice() { return executionPrice; }
    public double getFeesPaid() { return feesPaid; }

    public void addFill(double qty) {
        this.filledQuantity += qty;
        if (this.filledQuantity >= this.quantity) {
            this.status = Status.FILLED;
        } else {
            this.status = Status.PARTIALLY_FILLED;
        }
    }
    
    // allows Gateway/Portfolio to attach the final math to the receipt
    public void setExecutionData(double finalPrice, double fee) {
        this.executionPrice = finalPrice;
        this.feesPaid = fee;
    }
}
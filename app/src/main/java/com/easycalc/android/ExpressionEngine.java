package com.easycalc.android;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** Recursive-descent expression engine for the first Android port milestone. */
public final class ExpressionEngine {
    private final Map<String, Double> variables = new HashMap<>();
    private String input;
    private int pos;
    private double ans;
    private boolean degrees;

    public ExpressionEngine() {
        variables.put("pi", Math.PI);
        variables.put("e", Math.E);
    }

    public void setDegrees(boolean degrees) { this.degrees = degrees; }

    public double evaluate(String expression) {
        input = expression.trim().replace('×', '*').replace('÷', '/');
        pos = 0;
        double value = assignment();
        skipSpace();
        if (pos != input.length()) throw error("Unexpected '" + input.charAt(pos) + "'");
        if (!Double.isFinite(value)) throw error("Result is not finite");
        ans = value;
        variables.put("ans", ans);
        return value;
    }

    private double assignment() {
        int start = pos;
        skipSpace();
        if (pos < input.length() && Character.isLetter(input.charAt(pos))) {
            String name = identifier();
            skipSpace();
            if (eat('=')) {
                if (name.equals("pi") || name.equals("e")) throw error("Constant cannot be reassigned");
                double value = assignment();
                variables.put(name, value);
                return value;
            }
        }
        pos = start;
        return expression();
    }

    private double expression() {
        double value = term();
        while (true) {
            if (eat('+')) value += term();
            else if (eat('-')) value -= term();
            else return value;
        }
    }

    private double term() {
        double value = power();
        while (true) {
            if (eat('*')) value *= power();
            else if (eat('/')) value /= power();
            else if (eat('%')) value %= power();
            else return value;
        }
    }

    private double power() {
        double value = unary();
        if (eat('^')) value = Math.pow(value, power());
        return value;
    }

    private double unary() {
        if (eat('+')) return unary();
        if (eat('-')) return -unary();
        return postfix();
    }

    private double postfix() {
        double value = primary();
        while (eat('!')) value = factorial(value);
        return value;
    }

    private double primary() {
        skipSpace();
        if (eat('(')) {
            double value = assignment();
            require(')');
            return value;
        }
        if (pos < input.length() && (Character.isDigit(input.charAt(pos)) || input.charAt(pos) == '.')) return number();
        if (pos < input.length() && Character.isLetter(input.charAt(pos))) {
            String name = identifier();
            if (eat('(')) {
                double value = assignment();
                require(')');
                return function(name, value);
            }
            Double value = variables.get(name);
            if (value == null) throw error("Unknown variable: " + name);
            return value;
        }
        throw error("Number, function or '(' expected");
    }

    private double number() {
        int start = pos;
        while (pos < input.length() && (Character.isDigit(input.charAt(pos)) || input.charAt(pos) == '.')) pos++;
        if (pos < input.length() && (input.charAt(pos) == 'e' || input.charAt(pos) == 'E')) {
            pos++;
            if (pos < input.length() && (input.charAt(pos) == '+' || input.charAt(pos) == '-')) pos++;
            while (pos < input.length() && Character.isDigit(input.charAt(pos))) pos++;
        }
        double value;
        try { value = Double.parseDouble(input.substring(start, pos)); }
        catch (NumberFormatException ex) { throw error("Invalid number"); }
        if (pos < input.length()) {
            switch (input.charAt(pos)) {
                case 'n': value *= 1e-9; pos++; break;
                case 'u':
                case 'µ': value *= 1e-6; pos++; break;
                case 'm': value *= 1e-3; pos++; break;
                case 'k': value *= 1e3; pos++; break;
                case 'M': value *= 1e6; pos++; break;
                case 'G': value *= 1e9; pos++; break;
                default: break;
            }
        }
        return value;
    }

    private String identifier() {
        skipSpace();
        int start = pos;
        while (pos < input.length() && (Character.isLetterOrDigit(input.charAt(pos)) || input.charAt(pos) == '_')) pos++;
        return input.substring(start, pos).toLowerCase(Locale.ROOT);
    }

    private double function(String name, double x) {
        switch (name) {
            case "sin": return Math.sin(angle(x));
            case "cos": return Math.cos(angle(x));
            case "tan": return Math.tan(angle(x));
            case "asin": return unangle(Math.asin(x));
            case "acos": return unangle(Math.acos(x));
            case "atan": return unangle(Math.atan(x));
            case "sqrt": return Math.sqrt(x);
            case "cbrt": return Math.cbrt(x);
            case "ln": return Math.log(x);
            case "log": return Math.log10(x);
            case "exp": return Math.exp(x);
            case "abs": return Math.abs(x);
            case "floor": return Math.floor(x);
            case "ceil": return Math.ceil(x);
            case "round": return Math.rint(x);
            case "sinh": return Math.sinh(x);
            case "cosh": return Math.cosh(x);
            case "tanh": return Math.tanh(x);
            default: throw error("Unknown function: " + name);
        }
    }

    private double angle(double x) { return degrees ? Math.toRadians(x) : x; }
    private double unangle(double x) { return degrees ? Math.toDegrees(x) : x; }

    private double factorial(double x) {
        if (x < 0 || x != Math.rint(x) || x > 170) throw error("Factorial requires an integer from 0 to 170");
        double result = 1;
        for (int i = 2; i <= (int)x; i++) result *= i;
        return result;
    }

    private boolean eat(char c) {
        skipSpace();
        if (pos < input.length() && input.charAt(pos) == c) { pos++; return true; }
        return false;
    }

    private void require(char c) { if (!eat(c)) throw error("Expected '" + c + "'"); }
    private void skipSpace() { while (pos < input.length() && Character.isWhitespace(input.charAt(pos))) pos++; }
    private IllegalArgumentException error(String text) { return new IllegalArgumentException(text + " at position " + (pos + 1)); }
}

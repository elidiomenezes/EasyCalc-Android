package com.easycalc.android;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

/** Recursive-descent expression engine for the first Android port milestone. */
public final class ExpressionEngine {
    private final Map<String, Double> variables = new HashMap<>();
    private final Map<String, UserFunction> functions = new HashMap<>();
    private String input;
    private int pos;
    private double ans;
    private boolean degrees;
    private boolean definition;
    private String definitionText;
    private int recursionDepth;

    private static final class UserFunction {
        final String parameter;
        final String expression;
        UserFunction(String parameter, String expression) {
            this.parameter = parameter;
            this.expression = expression;
        }
    }

    public ExpressionEngine() {
        variables.put("pi", Math.PI);
        variables.put("e", Math.E);
    }

    public void setDegrees(boolean degrees) { this.degrees = degrees; }

    public boolean lastEvaluationWasDefinition() { return definition; }
    public String getDefinitionText() { return definitionText; }

    public String serializeFunctions() {
        StringBuilder result = new StringBuilder();
        for (Map.Entry<String, UserFunction> entry : new TreeMap<>(functions).entrySet()) {
            UserFunction function = entry.getValue();
            result.append(entry.getKey()).append('\t').append(function.parameter).append('\t')
                    .append(function.expression).append('\n');
        }
        return result.toString();
    }

    public void loadFunctions(String serialized) {
        functions.clear();
        if (serialized == null || serialized.isEmpty()) return;
        for (String line : serialized.split("\\n")) {
            String[] fields = line.split("\\t", 3);
            if (fields.length == 3) functions.put(fields[0], new UserFunction(fields[1], fields[2]));
        }
    }

    public double evaluate(String expression) {
        definition = false;
        definitionText = null;
        if (defineFunction(expression)) return ans;
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

    private boolean defineFunction(String source) {
        int equals = source.indexOf('=');
        if (equals < 0) return false;
        String left = source.substring(0, equals).trim();
        String body = source.substring(equals + 1).trim();
        int open = left.indexOf('(');
        int close = left.lastIndexOf(')');
        if (open <= 0 || close != left.length() - 1 || body.isEmpty()) return false;
        String name = normalizeName(left.substring(0, open).trim());
        String parameter = normalizeName(left.substring(open + 1, close).trim());
        if (!validName(name) || !validName(parameter)) throw error("Invalid function definition");
        if (name.equals("pi") || name.equals("e") || isBuiltIn(name))
            throw error("Reserved function name: " + name);
        functions.put(name, new UserFunction(parameter, body));
        definition = true;
        definitionText = name + "(" + parameter + ")";
        return true;
    }

    private boolean validName(String name) {
        if (name.isEmpty() || !Character.isLetter(name.charAt(0))) return false;
        for (int i = 1; i < name.length(); i++) {
            char c = name.charAt(i);
            if (!Character.isLetterOrDigit(c) && c != '_') return false;
        }
        return true;
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
        return normalizeName(input.substring(start, pos));
    }

    private String normalizeName(String name) { return name.toLowerCase(Locale.ROOT); }

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
            default: return userFunction(name, x);
        }
    }

    private boolean isBuiltIn(String name) {
        switch (name) {
            case "sin": case "cos": case "tan": case "asin": case "acos": case "atan":
            case "sqrt": case "cbrt": case "ln": case "log": case "exp": case "abs":
            case "floor": case "ceil": case "round": case "sinh": case "cosh": case "tanh":
                return true;
            default: return false;
        }
    }

    private double userFunction(String name, double argument) {
        UserFunction function = functions.get(name);
        if (function == null) throw error("Unknown function: " + name);
        if (recursionDepth >= 32) throw error("Function recursion limit exceeded");
        boolean hadOldValue = variables.containsKey(function.parameter);
        Double oldValue = variables.get(function.parameter);
        String oldInput = input;
        int oldPos = pos;
        try {
            recursionDepth++;
            variables.put(function.parameter, argument);
            input = function.expression.trim().replace('×', '*').replace('÷', '/');
            pos = 0;
            double value = assignment();
            skipSpace();
            if (pos != input.length()) throw error("Unexpected '" + input.charAt(pos) + "'");
            return value;
        } finally {
            recursionDepth--;
            input = oldInput;
            pos = oldPos;
            if (hadOldValue) variables.put(function.parameter, oldValue);
            else variables.remove(function.parameter);
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

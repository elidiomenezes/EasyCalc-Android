package com.easycalc.android;

import java.util.HashMap;
import java.util.ArrayList;
import java.util.List;
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
    private boolean deletion;
    private String deletionText;
    private int recursionDepth;

    private static final class UserFunction {
        final String[] parameters;
        final String expression;
        UserFunction(String[] parameters, String expression) {
            this.parameters = parameters;
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
    public boolean lastEvaluationWasDeletion() { return deletion; }
    public String getDeletionText() { return deletionText; }

    public String serializeFunctions() {
        StringBuilder result = new StringBuilder();
        for (Map.Entry<String, UserFunction> entry : new TreeMap<>(functions).entrySet()) {
            UserFunction function = entry.getValue();
            result.append(entry.getKey()).append('\t').append(String.join(",", function.parameters)).append('\t')
                    .append(function.expression).append('\n');
        }
        return result.toString();
    }

    public void loadFunctions(String serialized) {
        functions.clear();
        if (serialized == null || serialized.isEmpty()) return;
        for (String line : serialized.split("\\n")) {
            String[] fields = line.split("\\t", 3);
            if (fields.length == 3) functions.put(fields[0],
                    new UserFunction(fields[1].split(",", -1), fields[2]));
        }
    }

    public double evaluate(String expression) {
        definition = false;
        definitionText = null;
        deletion = false;
        deletionText = null;
        if (deleteFunction(expression)) return ans;
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

    private boolean deleteFunction(String source) {
        String trimmed = source.trim();
        if (!trimmed.toLowerCase(Locale.ROOT).startsWith("undef(")) return false;
        if (!trimmed.endsWith(")")) throw error("Expected ')' after function name");
        String name = normalizeName(trimmed.substring(6, trimmed.length() - 1).trim());
        if (!validName(name)) throw error("Invalid function name");
        UserFunction removed = functions.remove(name);
        if (removed == null) throw error("Unknown function: " + name);
        deletion = true;
        deletionText = name + "(" + String.join(",", removed.parameters) + ")";
        return true;
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
        String parameterText = left.substring(open + 1, close).trim();
        if (parameterText.isEmpty()) throw error("Invalid function definition");
        String[] parameters = parameterText.split("[,;:]", -1);
        for (int i = 0; i < parameters.length; i++) {
            parameters[i] = normalizeName(parameters[i].trim());
            if (!validName(parameters[i])) throw error("Invalid function definition");
            for (int j = 0; j < i; j++)
                if (parameters[i].equals(parameters[j])) throw error("Duplicate function parameter");
        }
        if (!validName(name)) throw error("Invalid function definition");
        if (name.equals("pi") || name.equals("e") || isBuiltIn(name))
            throw error("Reserved function name: " + name);
        functions.put(name, new UserFunction(parameters, body));
        definition = true;
        definitionText = name + "(" + String.join(",", parameters) + ")";
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
                List<Double> arguments = new ArrayList<>();
                skipSpace();
                if (!eat(')')) {
                    do {
                        arguments.add(assignment());
                        skipSpace();
                    } while (eat(',') || eat(':'));
                    require(')');
                }
                double[] values = new double[arguments.size()];
                for (int i = 0; i < values.length; i++) values[i] = arguments.get(i);
                return function(name, values);
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

    private double function(String name, double[] a) {
        switch (name) {
            case "sin": return Math.sin(angle(one(name, a)));
            case "cos": return Math.cos(angle(one(name, a)));
            case "tan": return Math.tan(angle(one(name, a)));
            case "asin": return unangle(Math.asin(one(name, a)));
            case "acos": return unangle(Math.acos(one(name, a)));
            case "atan": return unangle(Math.atan(one(name, a)));
            case "sinh": return Math.sinh(one(name, a));
            case "cosh": return Math.cosh(one(name, a));
            case "tanh": return Math.tanh(one(name, a));
            case "asinh": { double x=one(name,a); return Math.log(x+Math.sqrt(x*x+1)); }
            case "acosh": { double x=one(name,a); return Math.log(x+Math.sqrt(x*x-1)); }
            case "atanh": { double x=one(name,a); return 0.5*Math.log((1+x)/(1-x)); }
            case "sqrt": return Math.sqrt(one(name, a));
            case "cbrt": return Math.cbrt(one(name, a));
            case "ln": return Math.log(one(name, a));
            case "log": return Math.log10(one(name, a));
            case "log2": return Math.log(one(name, a)) / Math.log(2);
            case "exp": return Math.exp(one(name, a));
            case "abs": return Math.abs(one(name, a));
            case "floor": return Math.floor(one(name, a));
            case "ceil": return Math.ceil(one(name, a));
            case "round": return rounded(name, a, true);
            case "trunc": return rounded(name, a, false);
            case "ipart": return truncate(one(name, a));
            case "fpart": { double x=one(name,a); return x-truncate(x); }
            case "sign": return Math.signum(one(name, a));
            case "fact": return factorial(one(name, a));
            case "gamma": return gamma(one(name, a));
            case "hypot": case "rtopr": exact(name,a,2); return Math.hypot(a[0],a[1]);
            case "atan2": exact(name,a,2); return unangle(Math.atan2(a[0],a[1]));
            case "rtopd": exact(name,a,2); return unangle(Math.atan2(a[1],a[0]));
            case "ptorx": exact(name,a,2); return a[0]*Math.cos(angle(a[1]));
            case "ptory": exact(name,a,2); return a[0]*Math.sin(angle(a[1]));
            case "npr": exact(name,a,2); return permutation(integer(a[0]),integer(a[1]),false);
            case "ncr": exact(name,a,2); return permutation(integer(a[0]),integer(a[1]),true);
            case "gcd": return gcdAll(name,a,false);
            case "lcm": return gcdAll(name,a,true);
            case "modinv": exact(name,a,2); return modInverse(integer(a[0]),integer(a[1]));
            case "modpow": exact(name,a,3); return modPow(integer(a[0]),integer(a[1]),integer(a[2]));
            case "phi": return phi(integer(one(name,a)));
            case "isprime": return isPrime(integer(one(name,a))) ? 1 : 0;
            case "nextprime": return adjacentPrime(integer(one(name,a)),1);
            case "prevprime": return adjacentPrime(integer(one(name,a)),-1);
            case "if": exact(name,a,3); return a[0] != 0 ? a[1] : a[2];
            default: return userFunction(name, a);
        }
    }

    private boolean isBuiltIn(String name) {
        switch (name) {
            case "sin": case "cos": case "tan": case "asin": case "acos": case "atan":
            case "sqrt": case "cbrt": case "ln": case "log": case "exp": case "abs":
            case "floor": case "ceil": case "round": case "sinh": case "cosh": case "tanh":
            case "asinh": case "acosh": case "atanh": case "log2": case "trunc":
            case "ipart": case "fpart": case "sign": case "fact": case "gamma":
            case "hypot": case "rtopr": case "rtopd": case "ptorx": case "ptory":
            case "atan2": case "npr": case "ncr": case "gcd": case "lcm": case "modinv":
            case "modpow": case "phi": case "isprime": case "nextprime": case "prevprime":
            case "if":
                return true;
            default: return false;
        }
    }

    private double userFunction(String name, double[] arguments) {
        UserFunction function = functions.get(name);
        if (function == null) throw error("Unknown function: " + name);
        if (arguments.length != function.parameters.length)
            throw error(name + " expects " + function.parameters.length + " argument(s), got " + arguments.length);
        if (recursionDepth >= 32) throw error("Function recursion limit exceeded");
        boolean[] hadOldValue = new boolean[function.parameters.length];
        Double[] oldValue = new Double[function.parameters.length];
        String oldInput = input;
        int oldPos = pos;
        try {
            recursionDepth++;
            for (int i = 0; i < function.parameters.length; i++) {
                hadOldValue[i] = variables.containsKey(function.parameters[i]);
                oldValue[i] = variables.get(function.parameters[i]);
                variables.put(function.parameters[i], arguments[i]);
            }
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
            for (int i = 0; i < function.parameters.length; i++) {
                if (hadOldValue[i]) variables.put(function.parameters[i], oldValue[i]);
                else variables.remove(function.parameters[i]);
            }
        }
    }

    private double one(String name, double[] arguments) {
        exact(name, arguments, 1);
        return arguments[0];
    }

    private void exact(String name, double[] arguments, int count) {
        if (arguments.length != count)
            throw error(name + " expects " + count + " argument(s), got " + arguments.length);
    }

    private double rounded(String name, double[] arguments, boolean nearest) {
        if (arguments.length < 1 || arguments.length > 2)
            throw error(name + " expects 1 or 2 arguments, got " + arguments.length);
        int precision = arguments.length == 2 ? (int) integer(arguments[1]) : 0;
        double scale = Math.pow(10, precision);
        double scaled = arguments[0] * scale;
        // EasyCalc follows C round(): halves go away from zero.
        double result = nearest
                ? (scaled < 0 ? Math.ceil(scaled - 0.5) : Math.floor(scaled + 0.5))
                : truncate(scaled);
        return result / scale;
    }

    private double truncate(double value) {
        return value < 0 ? Math.ceil(value) : Math.floor(value);
    }

    private long integer(double value) {
        if (!Double.isFinite(value) || value != Math.rint(value) || Math.abs(value) > 9007199254740991L)
            throw error("Integer argument required");
        return (long) value;
    }

    private double permutation(long n, long r, boolean combination) {
        if (n < 0 || r < 0 || r > n) throw error("Expected integers with 0 <= r <= n");
        if (combination) r = Math.min(r, n - r);
        double result = 1;
        for (long i = 0; i < r; i++) {
            result *= n - i;
            if (combination) result /= i + 1;
        }
        return result;
    }

    private double gcdAll(String name, double[] arguments, boolean lcm) {
        if (arguments.length == 0) throw error(name + " expects at least 1 argument");
        long result = Math.abs(integer(arguments[0]));
        for (int i = 1; i < arguments.length; i++) {
            long value = Math.abs(integer(arguments[i]));
            long divisor = gcd(result, value);
            result = lcm ? (divisor == 0 ? 0 : Math.multiplyExact(result / divisor, value)) : divisor;
        }
        return result;
    }

    private long gcd(long a, long b) {
        while (b != 0) { long next = a % b; a = b; b = next; }
        return Math.abs(a);
    }

    private long modInverse(long value, long modulus) {
        if (modulus <= 1) throw error("Modulus must be greater than 1");
        long oldR = Math.floorMod(value, modulus), r = modulus;
        long oldS = 1, s = 0;
        while (r != 0) {
            long q = oldR / r;
            long nr = oldR - q * r; oldR = r; r = nr;
            long ns = oldS - q * s; oldS = s; s = ns;
        }
        if (oldR != 1) throw error("Modular inverse does not exist");
        return Math.floorMod(oldS, modulus);
    }

    private long modPow(long base, long exponent, long modulus) {
        if (exponent < 0 || modulus <= 0) throw error("Expected non-negative exponent and positive modulus");
        long result = 1 % modulus;
        base = Math.floorMod(base, modulus);
        while (exponent != 0) {
            if ((exponent & 1) != 0) result = multiplyMod(result, base, modulus);
            base = multiplyMod(base, base, modulus);
            exponent >>>= 1;
        }
        return result;
    }

    private long multiplyMod(long a, long b, long modulus) {
        long result = 0;
        while (b > 0) {
            if ((b & 1) != 0) result = addMod(result, a, modulus);
            a = addMod(a, a, modulus);
            b >>>= 1;
        }
        return result;
    }

    private long addMod(long a, long b, long modulus) {
        return a >= modulus - b ? a - (modulus - b) : a + b;
    }

    private long phi(long value) {
        if (value < 0) throw error("phi expects a non-negative integer");
        if (value == 0) return 0;
        long result = value;
        long n = value;
        for (long p = 2; p <= n / p; p++) {
            if (n % p == 0) {
                while (n % p == 0) n /= p;
                result -= result / p;
            }
        }
        if (n > 1) result -= result / n;
        return result;
    }

    private boolean isPrime(long value) {
        if (value < 2) return false;
        if ((value & 1) == 0) return value == 2;
        for (long divisor = 3; divisor <= value / divisor; divisor += 2)
            if (value % divisor == 0) return false;
        return true;
    }

    private long adjacentPrime(long value, int direction) {
        if (direction < 0 && value < 2) throw error("No previous prime");
        long candidate = value;
        while (!isPrime(candidate)) {
            if ((direction > 0 && candidate == Long.MAX_VALUE) || (direction < 0 && candidate <= 2))
                throw error("Prime search out of range");
            candidate += direction;
        }
        return candidate;
    }

    // Lanczos approximation, accurate to roughly 14 decimal digits for real inputs.
    private double gamma(double value) {
        if (value <= 0 && value == Math.rint(value)) throw error("Gamma pole");
        if (value < 0.5) return Math.PI / (Math.sin(Math.PI * value) * gamma(1 - value));
        double[] coefficients = {676.5203681218851, -1259.1392167224028,
                771.32342877765313, -176.61502916214059, 12.507343278686905,
                -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7};
        double z = value - 1;
        double sum = 0.99999999999980993;
        for (int i = 0; i < coefficients.length; i++) sum += coefficients[i] / (z + i + 1);
        double t = z + coefficients.length - 0.5;
        return Math.sqrt(2 * Math.PI) * Math.pow(t, z + 0.5) * Math.exp(-t) * sum;
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

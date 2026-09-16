import com.easycalc.android.ExpressionEngine;

import java.util.ArrayList;
import java.util.List;

/**
 * Dependency-free regression suite for the expression engine.
 *
 * Keeping this runner independent from Android and JUnit lets CI exercise the
 * parser before Gradle downloads the Android toolchain. Each assertion is
 * counted and failures are reported together so one bug does not hide others.
 */
public final class EngineTestSuite {
    private static final double EPSILON = 1e-10;
    private static final List<String> failures = new ArrayList<>();
    private static int assertions;

    public static void main(String[] args) {
        arithmetic();
        powersAndFactorials();
        constantsAndVariables();
        scientificNotationAndPrefixes();
        builtInFunctionsRadians();
        degreeMode();
        customFunctions();
        persistenceAndDeletion();
        unicodeAndWhitespace();
        invalidExpressions();
        domainAndLimitErrors();

        if (!failures.isEmpty()) {
            System.err.println(failures.size() + " of " + assertions + " assertions failed:");
            for (String failure : failures) System.err.println(" - " + failure);
            throw new AssertionError("ExpressionEngine regression suite failed");
        }
        System.out.println("ExpressionEngine regression suite passed: " + assertions + " assertions");
    }

    private static void arithmetic() {
        ExpressionEngine e = new ExpressionEngine();
        values(e, new Object[][] {
                {"0", 0.0}, {"42", 42.0}, {".5", 0.5}, {"5.", 5.0},
                {"2+3", 5.0}, {"8-3", 5.0}, {"6*7", 42.0}, {"8/4", 2.0},
                {"7%4", 3.0}, {"2+3*4", 14.0}, {"(2+3)*4", 20.0},
                {"20/5*2", 8.0}, {"20/(5*2)", 2.0}, {"10-3-2", 5.0},
                {"1+2+3+4", 10.0}, {"+7", 7.0}, {"-7", -7.0},
                {"--7", 7.0}, {"-(2+3)", -5.0}, {"(-2)*(-3)", 6.0},
                {"1/4", 0.25}, {"5%2+10", 11.0}, {"18/3/2", 3.0}
        });
    }

    private static void powersAndFactorials() {
        ExpressionEngine e = new ExpressionEngine();
        values(e, new Object[][] {
                {"2^3", 8.0}, {"2^3^2", 512.0}, {"(2^3)^2", 64.0},
                {"9^0.5", 3.0}, {"4^-1", 0.25}, {"0!", 1.0}, {"1!", 1.0},
                {"5!", 120.0}, {"3!!", 720.0}, {"2*3!", 12.0},
                {"(2+3)!", 120.0}, {"10!", 3628800.0}
        });
    }

    private static void constantsAndVariables() {
        ExpressionEngine e = new ExpressionEngine();
        near("pi", Math.PI, e.evaluate("pi"));
        near("e", Math.E, e.evaluate("e"));
        near("assignment", 2.5, e.evaluate("rate=2.5"));
        near("variable lookup", 25, e.evaluate("rate*10"));
        near("case-insensitive variable", 2.5, e.evaluate("RATE"));
        near("underscore assignment", 12, e.evaluate("value_2=12"));
        near("underscore lookup", 14, e.evaluate("value_2+2"));
        near("chained assignment result", 9, e.evaluate("a=b=9"));
        near("chained assignment a", 9, e.evaluate("a"));
        near("chained assignment b", 9, e.evaluate("b"));
        near("ans stores result", 10, e.evaluate("ans+1"));
        near("ans updates", 20, e.evaluate("ans*2"));
    }

    private static void scientificNotationAndPrefixes() {
        ExpressionEngine e = new ExpressionEngine();
        values(e, new Object[][] {
                {"1e3", 1e3}, {"1E3", 1e3}, {"1e+3", 1e3}, {"1e-3", 1e-3},
                {"2.5e2", 250.0}, {"1n", 1e-9}, {"4.7u", 4.7e-6},
                {"4.7µ", 4.7e-6}, {"2.2m", 2.2e-3}, {"2.2k", 2.2e3},
                {"2.2M", 2.2e6}, {"2.2G", 2.2e9}, {"2.2E3k", 2.2e6},
                {"1k+500", 1500.0}, {"1M/1k", 1000.0}, {"1m*1k", 1.0}
        });
    }

    private static void builtInFunctionsRadians() {
        ExpressionEngine e = new ExpressionEngine();
        Object[][] cases = {
                {"sin(0)", 0.0}, {"sin(pi/6)", 0.5}, {"cos(0)", 1.0},
                {"cos(pi)", -1.0}, {"tan(pi/4)", 1.0}, {"asin(0.5)", Math.asin(0.5)},
                {"acos(0.5)", Math.acos(0.5)}, {"atan(1)", Math.atan(1)},
                {"sqrt(0)", 0.0}, {"sqrt(81)", 9.0}, {"cbrt(27)", 3.0},
                {"cbrt(-8)", -2.0}, {"ln(e)", 1.0}, {"log(1000)", 3.0},
                {"exp(0)", 1.0}, {"exp(1)", Math.E}, {"abs(-4.5)", 4.5},
                {"floor(2.9)", 2.0}, {"floor(-2.1)", -3.0}, {"ceil(2.1)", 3.0},
                {"ceil(-2.9)", -2.0}, {"round(2.5)", 2.0}, {"round(3.5)", 4.0},
                {"sinh(0)", 0.0}, {"cosh(0)", 1.0}, {"tanh(0)", 0.0}
        };
        values(e, cases);

        for (double x : new double[] {-2, -1, -0.5, 0, 0.5, 1, 2}) {
            near("sinh(" + x + ")", Math.sinh(x), e.evaluate("sinh(" + x + ")"));
            near("cosh(" + x + ")", Math.cosh(x), e.evaluate("cosh(" + x + ")"));
            near("tanh(" + x + ")", Math.tanh(x), e.evaluate("tanh(" + x + ")"));
        }
    }

    private static void degreeMode() {
        ExpressionEngine e = new ExpressionEngine();
        e.setDegrees(true);
        values(e, new Object[][] {
                {"sin(0)", 0.0}, {"sin(30)", 0.5}, {"sin(90)", 1.0},
                {"cos(60)", 0.5}, {"cos(180)", -1.0}, {"tan(45)", 1.0},
                {"asin(0.5)", 30.0}, {"acos(0.5)", 60.0}, {"atan(1)", 45.0}
        });
        e.setDegrees(false);
        near("switch back to radians", 1, e.evaluate("sin(pi/2)"));
    }

    private static void customFunctions() {
        ExpressionEngine e = new ExpressionEngine();
        e.evaluate("square(x)=x^2");
        truth("definition flag", e.lastEvaluationWasDefinition());
        text("definition text", "square(x)", e.getDefinitionText());
        near("custom function", 25, e.evaluate("square(5)"));
        truth("definition flag resets", !e.lastEvaluationWasDefinition());

        e.evaluate("square(x)=x^3");
        near("function redefinition", 125, e.evaluate("square(5)"));
        e.evaluate("quad(x)=square(x)+2*x+1");
        near("nested function", 34, e.evaluate("quad(3)"));
        e.evaluate("mixedCase(Value)=Value+1");
        near("normalized function and parameter", 10, e.evaluate("MIXEDCASE(9)"));

        e.evaluate("outer=100");
        e.evaluate("uses_outer(x)=x+outer");
        near("function reads global", 105, e.evaluate("uses_outer(5)"));
        e.evaluate("shadow(outer)=outer*2");
        near("parameter shadows global", 14, e.evaluate("shadow(7)"));
        near("global restored after function", 100, e.evaluate("outer"));

        e.evaluate("f(x)=x+1");
        e.evaluate("g(x)=f(x)*2");
        e.evaluate("h(x)=g(x)+f(x)");
        near("three-level composition", 12, e.evaluate("h(3)"));
    }

    private static void persistenceAndDeletion() {
        ExpressionEngine original = new ExpressionEngine();
        original.evaluate("zeta(z)=z+26");
        original.evaluate("alpha(a)=a+1");
        String serialized = original.serializeFunctions();
        truth("serialization sorted", serialized.indexOf("alpha\t") < serialized.indexOf("zeta\t"));

        ExpressionEngine restored = new ExpressionEngine();
        restored.loadFunctions(serialized);
        near("restored alpha", 11, restored.evaluate("alpha(10)"));
        near("restored zeta", 36, restored.evaluate("zeta(10)"));
        restored.evaluate("undef(alpha)");
        truth("deletion flag", restored.lastEvaluationWasDeletion());
        text("deletion text", "alpha(a)", restored.getDeletionText());
        truth("definition removed from serialization", !restored.serializeFunctions().contains("alpha\t"));
        error(restored, "alpha(1)", "Unknown function");
        truth("deletion flag resets", !restored.lastEvaluationWasDeletion());

        restored.loadFunctions(null);
        error(restored, "zeta(1)", "Unknown function");
        restored.loadFunctions("");
        error(restored, "zeta(1)", "Unknown function");
        restored.loadFunctions("broken\nvalid\tx\tx+1\n");
        near("malformed persistence line ignored", 3, restored.evaluate("valid(2)"));
    }

    private static void unicodeAndWhitespace() {
        ExpressionEngine e = new ExpressionEngine();
        values(e, new Object[][] {
                {"  2 + 3  ", 5.0}, {"2\t*\n3", 6.0}, {"6×7", 42.0},
                {"8÷4", 2.0}, {"sqrt ( 16 )", 4.0}, {"( 1 + 2 ) * 3", 9.0}
        });
    }

    private static void invalidExpressions() {
        ExpressionEngine e = new ExpressionEngine();
        errors(e, new Object[][] {
                {"", "Number, function or '(' expected"},
                {"1+", "Number, function or '(' expected"},
                {"*2", "Number, function or '(' expected"},
                {"(1+2", "Expected ')'"},
                {"1+2)", "Unexpected ')'"},
                {"1 2", "Unexpected '2'"},
                {"unknown", "Unknown variable"},
                {"unknown(1)", "Unknown function"},
                {"1..2", "Invalid number"},
                {"1e", "Invalid number"},
                {"1e+", "Invalid number"},
                {"pi=3", "Constant cannot be reassigned"},
                {"e=3", "Constant cannot be reassigned"},
                {"sin(x)=x", "Reserved function name"},
                {"pi(x)=x", "Reserved function name"},
                {"1bad(x)=x", "Invalid function definition"},
                {"bad(1x)=x", "Invalid function definition"},
                {"empty(x)=", "Unknown variable"},
                {"undef(missing)", "Unknown function"},
                {"undef(", "Expected ')'"},
                {"undef(1bad)", "Invalid function name"}
        });
    }

    private static void domainAndLimitErrors() {
        ExpressionEngine e = new ExpressionEngine();
        errors(e, new Object[][] {
                {"1/0", "Result is not finite"}, {"0/0", "Result is not finite"},
                {"sqrt(-1)", "Result is not finite"}, {"ln(0)", "Result is not finite"},
                {"log(-1)", "Result is not finite"}, {"asin(2)", "Result is not finite"},
                {"(-1)!", "Factorial requires an integer"}, {"1.5!", "Factorial requires an integer"},
                {"171!", "Factorial requires an integer"}
        });

        e.evaluate("loop(x)=loop(x)");
        error(e, "loop(1)", "Function recursion limit exceeded");
        e.evaluate("good(x)=x+1");
        near("engine recovers after recursion error", 2, e.evaluate("good(1)"));
    }

    private static void values(ExpressionEngine engine, Object[][] cases) {
        for (Object[] test : cases) {
            String expression = (String) test[0];
            near(expression, (Double) test[1], evaluate(engine, expression));
        }
    }

    private static void errors(ExpressionEngine engine, Object[][] cases) {
        for (Object[] test : cases) error(engine, (String) test[0], (String) test[1]);
    }

    private static double evaluate(ExpressionEngine engine, String expression) {
        try {
            return engine.evaluate(expression);
        } catch (RuntimeException ex) {
            failures.add(expression + " unexpectedly threw: " + ex.getMessage());
            return Double.NaN;
        }
    }

    private static void near(String label, double expected, double actual) {
        assertions++;
        double scale = Math.max(1.0, Math.max(Math.abs(expected), Math.abs(actual)));
        if (!Double.isFinite(actual) || Math.abs(expected - actual) > EPSILON * scale) {
            failures.add(label + ": expected " + expected + ", got " + actual);
        }
    }

    private static void truth(String label, boolean condition) {
        assertions++;
        if (!condition) failures.add(label + ": condition was false");
    }

    private static void text(String label, String expected, String actual) {
        assertions++;
        if (!expected.equals(actual)) failures.add(label + ": expected '" + expected + "', got '" + actual + "'");
    }

    private static void error(ExpressionEngine engine, String expression, String messageFragment) {
        assertions++;
        try {
            engine.evaluate(expression);
            failures.add(expression + ": expected an error containing '" + messageFragment + "'");
        } catch (IllegalArgumentException ex) {
            if (!ex.getMessage().contains(messageFragment)) {
                failures.add(expression + ": expected error containing '" + messageFragment
                        + "', got '" + ex.getMessage() + "'");
            }
        } catch (RuntimeException ex) {
            failures.add(expression + ": wrong exception type " + ex.getClass().getSimpleName());
        }
    }
}

import com.easycalc.android.Value;

import java.util.ArrayList;
import java.util.List;

public final class ValueTestSuite {
    private static final double EPSILON = 1e-10;
    private static final List<String> failures = new ArrayList<>();
    private static int assertions;

    public static void main(String[] args) {
        construction();
        arithmetic();
        polarAndPowers();
        elementaryFunctions();
        identities();
        errors();

        if (!failures.isEmpty()) {
            for (String failure : failures) System.err.println(" - " + failure);
            throw new AssertionError(failures.size() + " of " + assertions + " Value assertions failed");
        }
        System.out.println("Value regression suite passed: " + assertions + " assertions");
    }

    private static void construction() {
        value("real", Value.real(3), 3, 0);
        value("complex", Value.complex(3, 4), 3, 4);
        truth("real detection", Value.real(3).isReal());
        truth("complex detection", !Value.complex(3, 4).isReal());
        near("real conversion", 3, Value.real(3).asReal());
        text("real format", "3", Value.real(3).toString());
        text("positive complex format", "3 + 4i", Value.complex(3, 4).toString());
        text("negative complex format", "3 - 4i", Value.complex(3, -4).toString());
        text("pure imaginary format", "2i", Value.complex(0, 2).toString());
        truth("negative zero normalized", Value.complex(-0.0, -0.0).equals(Value.ZERO));
    }

    private static void arithmetic() {
        Value a = Value.complex(3, 4);
        Value b = Value.complex(1, -2);
        value("addition", a.add(b), 4, 2);
        value("subtraction", a.subtract(b), 2, 6);
        value("negation", a.negate(), -3, -4);
        value("multiplication", a.multiply(b), 11, -2);
        value("division", a.divide(b), -1, 2);
        value("conjugate", a.conjugate(), 3, -4);
        value("reciprocal", a.reciprocal(), .12, -.16);
        near("magnitude", 5, a.magnitude());
        near("angle", Math.atan2(4, 3), a.angle());
        value("i squared", Value.I.multiply(Value.I), -1, 0);
        value("identity add", a.add(Value.ZERO), 3, 4);
        value("identity multiply", a.multiply(Value.ONE), 3, 4);
    }

    private static void polarAndPowers() {
        value("polar", Value.polar(2, Math.PI / 2), 0, 2);
        value("sqrt positive", Value.real(9).sqrt(), 3, 0);
        value("sqrt negative", Value.real(-9).sqrt(), 0, 3);
        value("sqrt complex", Value.complex(3, 4).sqrt(), 2, 1);
        value("integer power", Value.complex(1, 1).pow(Value.real(2)), 0, 2);
        value("zero positive power", Value.ZERO.pow(Value.real(2)), 0, 0);
        value("zero power zero", Value.ZERO.pow(Value.ZERO), 1, 0);
        value("Euler identity", Value.I.multiply(Value.real(Math.PI)).exp(), -1, 0);
        value("exp log inverse", Value.complex(2, 3).log().exp(), 2, 3);
    }

    private static void elementaryFunctions() {
        value("exp real", Value.real(1).exp(), Math.E, 0);
        value("log negative", Value.real(-1).log(), 0, Math.PI);
        value("sin real", Value.real(Math.PI / 2).sin(), 1, 0);
        value("cos real", Value.real(Math.PI).cos(), -1, 0);
        value("tan real", Value.real(Math.PI / 4).tan(), 1, 0);
        value("sinh real", Value.real(1).sinh(), Math.sinh(1), 0);
        value("cosh real", Value.real(1).cosh(), Math.cosh(1), 0);
        value("tanh real", Value.real(1).tanh(), Math.tanh(1), 0);
        value("sin imaginary", Value.I.sin(), 0, Math.sinh(1));
        value("cos imaginary", Value.I.cos(), Math.cosh(1), 0);
    }

    private static void identities() {
        Value[] samples = {Value.complex(1, 2), Value.complex(-3, .5), Value.complex(.25, -4)};
        for (Value z : samples) {
            value("z+(-z)", z.add(z.negate()), 0, 0);
            value("z/z", z.divide(z), 1, 0);
            value("sqrt(z)^2", z.sqrt().multiply(z.sqrt()), z.realPart(), z.imaginaryPart());
            value("sin²+cos²", z.sin().multiply(z.sin()).add(z.cos().multiply(z.cos())), 1, 0);
            near("conjugate magnitude", z.magnitude(), z.conjugate().magnitude());
        }
    }

    private static void errors() {
        error("complex as real", () -> Value.I.asReal(), "Real value required");
        error("division by zero", () -> Value.ONE.divide(Value.ZERO), "Division by zero");
        error("log zero", () -> Value.ZERO.log(), "Logarithm of zero");
        error("zero negative power", () -> Value.ZERO.pow(Value.real(-1)), "Undefined zero power");
        error("non-finite real", () -> Value.real(Double.NaN), "not finite");
        error("non-finite complex", () -> Value.complex(1, Double.POSITIVE_INFINITY), "not finite");
    }

    private static void value(String label, Value actual, double real, double imaginary) {
        near(label + " real", real, actual.realPart());
        near(label + " imaginary", imaginary, actual.imaginaryPart());
    }

    private static void near(String label, double expected, double actual) {
        assertions++;
        double scale = Math.max(1, Math.max(Math.abs(expected), Math.abs(actual)));
        if (!Double.isFinite(actual) || Math.abs(expected - actual) > EPSILON * scale)
            failures.add(label + ": expected " + expected + ", got " + actual);
    }

    private static void truth(String label, boolean condition) {
        assertions++;
        if (!condition) failures.add(label);
    }

    private static void text(String label, String expected, String actual) {
        assertions++;
        if (!expected.equals(actual)) failures.add(label + ": expected '" + expected + "', got '" + actual + "'");
    }

    private static void error(String label, Runnable operation, String fragment) {
        assertions++;
        try {
            operation.run();
            failures.add(label + ": expected error");
        } catch (ArithmeticException ex) {
            if (!ex.getMessage().contains(fragment)) failures.add(label + ": " + ex.getMessage());
        }
    }
}

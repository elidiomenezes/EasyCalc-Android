package com.easycalc.android;

import java.util.Locale;

/** Immutable scalar value. Complex support is the base for future list/matrix values. */
public final class Value {
    public static final Value ZERO = new Value(0, 0);
    public static final Value ONE = new Value(1, 0);
    public static final Value I = new Value(0, 1);

    private final double real;
    private final double imaginary;

    private Value(double real, double imaginary) {
        if (!Double.isFinite(real) || !Double.isFinite(imaginary))
            throw new ArithmeticException("Value is not finite");
        this.real = real == 0 ? 0 : real;
        this.imaginary = imaginary == 0 ? 0 : imaginary;
    }

    public static Value real(double value) { return new Value(value, 0); }
    public static Value complex(double real, double imaginary) { return new Value(real, imaginary); }
    public static Value polar(double radius, double angle) {
        return new Value(radius * Math.cos(angle), radius * Math.sin(angle));
    }

    public double realPart() { return real; }
    public double imaginaryPart() { return imaginary; }
    public boolean isReal() { return imaginary == 0; }
    public double asReal() {
        if (!isReal()) throw new ArithmeticException("Real value required");
        return real;
    }

    public Value add(Value other) {
        return complex(real + other.real, imaginary + other.imaginary);
    }

    public Value subtract(Value other) {
        return complex(real - other.real, imaginary - other.imaginary);
    }

    public Value negate() { return complex(-real, -imaginary); }

    public Value multiply(Value other) {
        return complex(real * other.real - imaginary * other.imaginary,
                real * other.imaginary + imaginary * other.real);
    }

    public Value divide(Value other) {
        if (other.real == 0 && other.imaginary == 0) throw new ArithmeticException("Division by zero");
        // Smith's method avoids unnecessary overflow in the denominator.
        if (Math.abs(other.real) >= Math.abs(other.imaginary)) {
            double ratio = other.imaginary / other.real;
            double denominator = other.real + other.imaginary * ratio;
            return complex((real + imaginary * ratio) / denominator,
                    (imaginary - real * ratio) / denominator);
        }
        double ratio = other.real / other.imaginary;
        double denominator = other.real * ratio + other.imaginary;
        return complex((real * ratio + imaginary) / denominator,
                (imaginary * ratio - real) / denominator);
    }

    public Value reciprocal() { return ONE.divide(this); }
    public Value conjugate() { return complex(real, -imaginary); }
    public double magnitude() { return Math.hypot(real, imaginary); }
    public double angle() { return Math.atan2(imaginary, real); }

    public Value exp() {
        double scale = Math.exp(real);
        return complex(scale * Math.cos(imaginary), scale * Math.sin(imaginary));
    }

    public Value log() {
        if (real == 0 && imaginary == 0) throw new ArithmeticException("Logarithm of zero");
        return complex(Math.log(magnitude()), angle());
    }

    public Value pow(Value exponent) {
        if (real == 0 && imaginary == 0) {
            if (exponent.imaginary == 0 && exponent.real > 0) return ZERO;
            if (exponent.imaginary == 0 && exponent.real == 0) return ONE;
            throw new ArithmeticException("Undefined zero power");
        }
        return log().multiply(exponent).exp();
    }

    public Value sqrt() {
        if (imaginary == 0) {
            if (real >= 0) return real(Math.sqrt(real));
            return complex(0, Math.sqrt(-real));
        }
        double magnitude = magnitude();
        double realRoot = Math.sqrt((magnitude + real) / 2);
        double imaginaryRoot = Math.copySign(Math.sqrt((magnitude - real) / 2), imaginary);
        return complex(realRoot, imaginaryRoot);
    }

    public Value sin() {
        return complex(Math.sin(real) * Math.cosh(imaginary),
                Math.cos(real) * Math.sinh(imaginary));
    }

    public Value cos() {
        return complex(Math.cos(real) * Math.cosh(imaginary),
                -Math.sin(real) * Math.sinh(imaginary));
    }

    public Value tan() { return sin().divide(cos()); }

    public Value sinh() {
        return complex(Math.sinh(real) * Math.cos(imaginary),
                Math.cosh(real) * Math.sin(imaginary));
    }

    public Value cosh() {
        return complex(Math.cosh(real) * Math.cos(imaginary),
                Math.sinh(real) * Math.sin(imaginary));
    }

    public Value tanh() { return sinh().divide(cosh()); }

    @Override public boolean equals(Object object) {
        if (!(object instanceof Value)) return false;
        Value other = (Value) object;
        return Double.doubleToLongBits(real) == Double.doubleToLongBits(other.real)
                && Double.doubleToLongBits(imaginary) == Double.doubleToLongBits(other.imaginary);
    }

    @Override public int hashCode() {
        long r = Double.doubleToLongBits(real);
        long i = Double.doubleToLongBits(imaginary);
        return 31 * Long.hashCode(r) + Long.hashCode(i);
    }

    @Override public String toString() {
        if (imaginary == 0) return number(real);
        if (real == 0) return number(imaginary) + "i";
        return number(real) + (imaginary < 0 ? " - " : " + ") + number(Math.abs(imaginary)) + "i";
    }

    private static String number(double value) {
        if (value == Math.rint(value) && Math.abs(value) < 1e16)
            return String.format(Locale.ROOT, "%.0f", value);
        return Double.toString(value);
    }
}

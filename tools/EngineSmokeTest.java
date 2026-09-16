import com.easycalc.android.ExpressionEngine;

public final class EngineSmokeTest {
    private static void assertNear(double expected, double actual) {
        if (Math.abs(expected - actual) > 1e-10) {
            throw new AssertionError("Expected " + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) {
        ExpressionEngine e = new ExpressionEngine();
        assertNear(14, e.evaluate("2+3*4"));
        assertNear(512, e.evaluate("2^3^2"));
        assertNear(120, e.evaluate("5!"));
        assertNear(0.5, e.evaluate("sin(pi/6)"));
        assertNear(2.5, e.evaluate("rate=2.5"));
        assertNear(25, e.evaluate("rate*10"));
        e.setDegrees(true);
        assertNear(1, e.evaluate("sin(90)"));
        System.out.println("ExpressionEngine smoke tests passed");
    }
}

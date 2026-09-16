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
        assertNear(1e-9, e.evaluate("1n"));
        assertNear(4.7e-6, e.evaluate("4.7u"));
        assertNear(4.7e-6, e.evaluate("4.7µ"));
        assertNear(0.0022, e.evaluate("2.2m"));
        assertNear(2200, e.evaluate("2.2k"));
        assertNear(2.2e6, e.evaluate("2.2M"));
        assertNear(2.2e9, e.evaluate("2.2G"));
        assertNear(2.2e6, e.evaluate("2.2E3k"));
        e.setDegrees(true);
        assertNear(1, e.evaluate("sin(90)"));
        System.out.println("ExpressionEngine smoke tests passed");
    }
}

package com.easycalc.android;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.text.DecimalFormat;

public final class MainActivity extends Activity {
    private static final int BG = Color.rgb(16, 20, 24);
    private static final int PANEL = Color.rgb(31, 38, 44);
    private static final int TEXT = Color.rgb(232, 238, 242);
    private static final int ACCENT = Color.rgb(128, 203, 196);
    private final ExpressionEngine engine = new ExpressionEngine();
    private final DecimalFormat format = new DecimalFormat("0.###############E0");
    private EditText input;
    private TextView result;
    private TextView history;
    private Button angleMode;
    private boolean degrees;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        engine.loadFunctions(getPreferences(MODE_PRIVATE).getString("functions", ""));
        setContentView(buildUi());
    }

    private View buildUi() {
        LinearLayout root = column();
        root.setPadding(dp(12), dp(12), dp(12), dp(12));
        root.setBackgroundColor(BG);

        TextView title = text("EasyCalc", 24, ACCENT);
        title.setTypeface(null, 1);
        root.addView(title);

        ScrollView historyScroll = new ScrollView(this);
        history = text("EasyCalc 1.25 Android port\n", 14, Color.LTGRAY);
        history.setGravity(Gravity.BOTTOM);
        historyScroll.addView(history);
        root.addView(historyScroll, new LinearLayout.LayoutParams(-1, 0, 1));

        input = new EditText(this);
        input.setTextColor(TEXT);
        input.setHintTextColor(Color.GRAY);
        input.setHint("Expression, e.g. sin(pi/4)^2");
        input.setSingleLine(true);
        input.setTextSize(19);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        input.setBackgroundColor(PANEL);
        input.setPadding(dp(10), 0, dp(10), 0);
        input.setOnEditorActionListener((v, id, event) -> { evaluate(); return true; });
        root.addView(input, new LinearLayout.LayoutParams(-1, dp(54)));

        result = text("0", 30, TEXT);
        result.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        root.addView(result, new LinearLayout.LayoutParams(-1, dp(58)));

        LinearLayout modes = row();
        angleMode = key("RAD", v -> toggleAngle());
        modes.addView(angleMode, weighted());
        modes.addView(key("f(x)", v -> insert("sin(")), weighted());
        modes.addView(key("π", v -> insert("pi")), weighted());
        modes.addView(key("ANS", v -> insert("ans")), weighted());
        root.addView(modes, rowParams());

        String[][] keys = {
                {"sin(", "cos(", "tan(", "⌫"},
                {"7", "8", "9", "÷"},
                {"4", "5", "6", "×"},
                {"1", "2", "3", "-"},
                {"0", ".", "^", "+"},
                {"(", ")", "C", "="}
        };
        for (String[] labels : keys) {
            LinearLayout row = row();
            for (String label : labels) row.addView(key(label, v -> press(label)), weighted());
            root.addView(row, rowParams());
        }
        return root;
    }

    private void press(String key) {
        if (key.equals("=")) {
            String expression = input.getText().toString();
            if (!expression.contains("=") && expression.trim().matches(
                    "[A-Za-z][A-Za-z0-9_]*\\s*\\(\\s*[A-Za-z][A-Za-z0-9_]*\\s*\\)")) {
                insert("=");
            } else {
                evaluate();
            }
        }
        else if (key.equals("C")) { input.setText(""); result.setText("0"); }
        else if (key.equals("⌫")) {
            int start = input.getSelectionStart();
            if (start > 0) input.getText().delete(start - 1, start);
        } else insert(key);
    }

    private void insert(String value) {
        int start = Math.max(0, input.getSelectionStart());
        input.getText().insert(start, value);
        input.requestFocus();
    }

    private void evaluate() {
        String expression = input.getText().toString();
        if (expression.trim().isEmpty()) return;
        try {
            double value = engine.evaluate(expression);
            if (engine.lastEvaluationWasDefinition()) {
                String rendered = "Defined " + engine.getDefinitionText();
                result.setText(rendered);
                history.append("\n" + expression + "\n  " + rendered + "\n");
                getPreferences(MODE_PRIVATE).edit()
                        .putString("functions", engine.serializeFunctions()).apply();
                return;
            }
            String rendered = render(value);
            result.setText(rendered);
            history.append("\n" + expression + "\n  = " + rendered + "\n");
        } catch (IllegalArgumentException ex) {
            result.setText("Error");
            Toast.makeText(this, ex.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    private String render(double value) {
        if (value == Math.rint(value) && Math.abs(value) < 1e15) return Long.toString((long)value);
        return format.format(value).replace("E0", "");
    }

    private void toggleAngle() {
        degrees = !degrees;
        engine.setDegrees(degrees);
        angleMode.setText(degrees ? "DEG" : "RAD");
    }

    private Button key(String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextColor(TEXT);
        button.setTextSize(16);
        button.setBackgroundColor(PANEL);
        button.setPadding(0, 0, 0, 0);
        button.setOnClickListener(listener);
        return button;
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value); view.setTextSize(size); view.setTextColor(color);
        return view;
    }
    private LinearLayout column() { LinearLayout l = new LinearLayout(this); l.setOrientation(LinearLayout.VERTICAL); return l; }
    private LinearLayout row() { LinearLayout l = new LinearLayout(this); l.setOrientation(LinearLayout.HORIZONTAL); return l; }
    private LinearLayout.LayoutParams weighted() { LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, -1, 1); p.setMargins(dp(2), dp(2), dp(2), dp(2)); return p; }
    private LinearLayout.LayoutParams rowParams() { return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)); }
    private int dp(int n) { return Math.round(n * getResources().getDisplayMetrics().density); }
}

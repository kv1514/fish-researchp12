package com.fishengine.fish;

import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;

import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import com.getcapacitor.BridgeActivity;

/**
 * The app is one web view. Android 15 and later draw every app edge to edge,
 * under the status bar, the navigation bar and the keyboard, so this keeps
 * the game clear of all three on every Android version: the page sits between
 * the bars, and above the keyboard while one is open (so a sign-in field is
 * never hidden behind it). The bars themselves show the app's dark
 * background with light icons.
 */
public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        WindowInsetsControllerCompat bars =
                WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        bars.setAppearanceLightStatusBars(false);
        bars.setAppearanceLightNavigationBars(false);

        View web = getBridge().getWebView();
        ViewCompat.setOnApplyWindowInsetsListener(web, (v, insets) -> {
            Insets sys = insets.getInsets(WindowInsetsCompat.Type.systemBars()
                    | WindowInsetsCompat.Type.displayCutout());
            Insets ime = insets.getInsets(WindowInsetsCompat.Type.ime());
            ViewGroup.MarginLayoutParams m = (ViewGroup.MarginLayoutParams) v.getLayoutParams();
            m.leftMargin = sys.left;
            m.topMargin = sys.top;
            m.rightMargin = sys.right;
            m.bottomMargin = Math.max(sys.bottom, ime.bottom);
            v.setLayoutParams(m);
            return WindowInsetsCompat.CONSUMED;
        });
    }
}

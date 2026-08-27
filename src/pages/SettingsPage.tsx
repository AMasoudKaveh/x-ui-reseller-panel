import { Check, CircleHelp, Laptop, Moon, Palette, Sun } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  type AccentColor,
  type UiMode,
  useThemeSettings
} from "../theme/ThemeProvider";

const modes: Array<{
  id: UiMode;
  title: string;
  description: string;
  icon: typeof Sun;
}> = [
  { id: "light", title: "Light", description: "Bright and clean", icon: Sun },
  { id: "dark", title: "Dark", description: "Easy on the eyes", icon: Moon },
  { id: "system", title: "System", description: "Matches your device", icon: Laptop }
];

const colors: Array<{
  id: AccentColor;
  title: string;
  swatch: string;
}> = [
  { id: "default", title: "Default", swatch: "#4d82cf" },
  { id: "red", title: "Red", swatch: "#ef4444" },
  { id: "rose", title: "Rose", swatch: "#f43f5e" },
  { id: "orange", title: "Orange", swatch: "#f97316" },
  { id: "green", title: "Green", swatch: "#22c55e" },
  { id: "blue", title: "Blue", swatch: "#3b82f6" },
  { id: "yellow", title: "Yellow", swatch: "#eab308" },
  { id: "violet", title: "Violet", swatch: "#8b5cf6" }
];

export default function SettingsPage() {
  const { mode, accent, setMode, setAccent } = useThemeSettings();
  const [showToast, setShowToast] = useState(false);
  const firstRender = useRef(true);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }

    setShowToast(true);
    const timeout = window.setTimeout(() => setShowToast(false), 1600);
    return () => window.clearTimeout(timeout);
  }, [mode, accent]);

  return (
    <>
      <header className="page-header settings-header">
        <div>
          <div className="page-title-row">
            <h1>Theme</h1>
            <span className="help-chip">?</span>
          </div>
          <p>Manage interface appearance</p>
        </div>
      </header>

      <main className="settings-page">
        <div className="settings-tab-row">
          <div className="settings-tab active">
            <Palette size={17} strokeWidth={1.8} />
            <span>Theme</span>
          </div>
        </div>

        <section className="settings-section">
          <div className="settings-section-title">
            <Sun size={18} strokeWidth={1.8} />
            <div>
              <h2>Mode</h2>
              <p>Choose how the interface should appear</p>
            </div>
          </div>

          <div className="mode-grid">
            {modes.map((item) => {
              const Icon = item.icon;
              const selected = item.id === mode;

              return (
                <button
                  key={item.id}
                  className={`mode-card ${selected ? "selected" : ""}`}
                  type="button"
                  onClick={() => setMode(item.id)}
                >
                  <div className="mode-icon">
                    <Icon size={19} strokeWidth={1.8} />
                  </div>

                  <div className="mode-copy">
                    <strong>{item.title}</strong>
                    <span>{item.description}</span>
                  </div>

                  {selected ? (
                    <span className="settings-check">
                      <Check size={12} strokeWidth={2.4} />
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </section>

        <section className="settings-section settings-color-section">
          <div className="settings-section-title">
            <Palette size={18} strokeWidth={1.8} />
            <div>
              <h2>Color</h2>
              <p>Select your preferred color scheme</p>
            </div>
          </div>

          <div className="color-grid">
            {colors.map((item) => {
              const selected = item.id === accent;

              return (
                <button
                  key={item.id}
                  className={`color-card ${selected ? "selected" : ""}`}
                  type="button"
                  onClick={() => setAccent(item.id)}
                >
                  <span
                    className="color-swatch"
                    style={{ backgroundColor: item.swatch }}
                  />

                  <strong>{item.title}</strong>

                  {selected ? (
                    <span className="settings-check">
                      <Check size={12} strokeWidth={2.4} />
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </section>

        <div className="settings-note">
          <CircleHelp size={17} strokeWidth={1.8} />
          <span>
            Accent color is applied across buttons, selected items, progress indicators,
            switches, links and interactive UI elements.
          </span>
        </div>
      </main>

      {showToast ? (
        <div className="theme-toast">
          <span className="theme-toast-icon">
            <Check size={13} strokeWidth={2.4} />
          </span>
          <div>
            <strong>Success</strong>
            <span>Theme changed successfully</span>
          </div>
        </div>
      ) : null}
    </>
  );
}

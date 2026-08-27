import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";

export type UiMode = "light" | "dark" | "system";
export type AccentColor =
  | "default"
  | "red"
  | "rose"
  | "orange"
  | "green"
  | "blue"
  | "yellow"
  | "violet";

type ThemeContextValue = {
  mode: UiMode;
  accent: AccentColor;
  resolvedMode: "light" | "dark";
  setMode: (mode: UiMode) => void;
  setAccent: (accent: AccentColor) => void;
  toggleQuickMode: () => void;
};

const STORAGE_MODE = "xui-ui-mode";
const STORAGE_ACCENT = "xui-accent-color";

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getSystemMode(): "light" | "dark" {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function isMode(value: string | null): value is UiMode {
  return value === "light" || value === "dark" || value === "system";
}

function isAccent(value: string | null): value is AccentColor {
  return [
    "default",
    "red",
    "rose",
    "orange",
    "green",
    "blue",
    "yellow",
    "violet"
  ].includes(value ?? "");
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<UiMode>(() => {
    const saved = localStorage.getItem(STORAGE_MODE);
    return isMode(saved) ? saved : "dark";
  });

  const [accent, setAccentState] = useState<AccentColor>(() => {
    const saved = localStorage.getItem(STORAGE_ACCENT);
    return isAccent(saved) ? saved : "default";
  });

  const [systemMode, setSystemMode] = useState<"light" | "dark">(getSystemMode);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => setSystemMode(media.matches ? "light" : "dark");
    onChange();
    media.addEventListener?.("change", onChange);
    return () => media.removeEventListener?.("change", onChange);
  }, []);

  const resolvedMode = mode === "system" ? systemMode : mode;

  useEffect(() => {
    const html = document.documentElement;
    html.dataset.uiMode = resolvedMode;
    html.dataset.accent = accent;
    html.style.colorScheme = resolvedMode;
  }, [resolvedMode, accent]);

  const setMode = useCallback((nextMode: UiMode) => {
    localStorage.setItem(STORAGE_MODE, nextMode);
    setModeState(nextMode);
  }, []);

  const setAccent = useCallback((nextAccent: AccentColor) => {
    localStorage.setItem(STORAGE_ACCENT, nextAccent);
    setAccentState(nextAccent);
  }, []);

  const toggleQuickMode = useCallback(() => {
    const next = resolvedMode === "dark" ? "light" : "dark";
    setMode(next);
  }, [resolvedMode, setMode]);

  const value = useMemo(
    () => ({
      mode,
      accent,
      resolvedMode,
      setMode,
      setAccent,
      toggleQuickMode
    }),
    [mode, accent, resolvedMode, setMode, setAccent, toggleQuickMode]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemeSettings() {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error("useThemeSettings must be used inside ThemeProvider");
  }
  return value;
}

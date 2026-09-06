export type Theme = "dark" | "light";

export interface ThemeColors {
  primary: string;
  secondary: string;
  success: string;
  warning: string;
  error: string;
  muted: string;
  border: string;
  background: string;
  foreground: string;
}

const DARK_THEME: ThemeColors = {
  primary: "cyan",
  secondary: "blue",
  success: "green",
  warning: "yellow",
  error: "red",
  muted: "gray",
  border: "gray",
  background: "black",
  foreground: "white",
};

const LIGHT_THEME: ThemeColors = {
  primary: "blue",
  secondary: "magenta",
  success: "green",
  warning: "yellow",
  error: "red",
  muted: "gray",
  border: "gray",
  background: "white",
  foreground: "black",
};

function getBackgroundColor(): number | null {
  const colorfgbg = process.env.COLORFGBG;
  if (colorfgbg) {
    const parts = colorfgbg.split(";");
    const bg = parseInt(parts[parts.length - 1], 10);
    if (!isNaN(bg)) return bg;
  }
  return null;
}

export function detectTheme(): Theme {
  // 1. Check explicit env var
  if (process.env.FENRYS_THEME === "light") return "light";
  if (process.env.FENRYS_THEME === "dark") return "dark";

  // 2. Check COLORFGBG (vim-style)
  const bg = getBackgroundColor();
  if (bg !== null) {
    return bg > 12 ? "light" : "dark";
  }

  // 3. Check TERM_PROGRAM for known light themes
  const termProgram = process.env.TERM_PROGRAM || "";
  if (termProgram.includes("light") || process.env.THEME === "light") {
    return "light";
  }

  // 4. Default to dark (hacker aesthetic)
  return "dark";
}

export function getThemeColors(theme: Theme): ThemeColors {
  return theme === "dark" ? DARK_THEME : LIGHT_THEME;
}

export function getTheme(): { theme: Theme; colors: ThemeColors } {
  const theme = detectTheme();
  return { theme, colors: getThemeColors(theme) };
}

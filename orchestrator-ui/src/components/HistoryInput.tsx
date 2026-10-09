import { TextField } from "@mui/material";
import { makeStyles } from "@griffel/react";
/**
 * Input with autocomplete suggestions from form history.
 * Fetches previously used values from the backend and shows them as you type.
 */

import { useState, useEffect, useRef } from "react";

import { getHistory, addToHistory } from "../formHistory";

const useStyles = makeStyles({
    wrapper: {
        position: "relative" as const,
    },
    suggestions: {
        position: "absolute" as const,
        top: "100%",
        left: 0,
        right: 0,
        zIndex: 1000,
        backgroundColor: "var(--m3-colorNeutralBackground1)",
        border: `1px solid ${"var(--m3-colorNeutralStroke1)"}`,
        borderRadius: "16px",
        boxShadow: "0 8px 24px #00000022",
        maxHeight: "200px",
        overflowY: "auto" as const,
        marginTop: "2px",
    },
    suggestion: {
        padding: `${"12px"} ${"24px"}`,
        cursor: "pointer",
        fontSize: "14px",
        fontFamily: "'Segoe UI', sans-serif",
        color: "var(--m3-colorNeutralForeground1)",
        borderBottom: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        transition: "background-color 0.1s ease",
        ":hover": {
            backgroundColor: "var(--m3-colorBrandBackground2)",
        },
    },
    suggestionActive: {
        backgroundColor: "var(--m3-colorBrandBackground2)",
    },
    suggestionIcon: {
        marginRight: "12px",
        color: "var(--m3-colorNeutralForeground3)",
        fontSize: "12px",
    },
});

interface HistoryInputProps {
  field: string;
  id?: string;
  value: string;
  onChange: (value: string) => void;
  onCommit?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  type?: "text" | "email" | "url" | "tel" | "search" | "password";
  /** Extra suggestions shown below history (e.g. AHDS-supported regions). */
  suggestions?: string[];
  /** Label shown above the extra suggestions section. */
  suggestionsLabel?: string;
}

export function HistoryInput({ id, field, value, onChange, onCommit, placeholder, disabled, type, suggestions, suggestionsLabel, }: HistoryInputProps) {
    const styles = useStyles();
    const [history, setHistory] = useState<string[]>([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [activeIndex, setActiveIndex] = useState(-1);
    const wrapperRef = useRef<HTMLDivElement>(null);
    // Fetch history on mount
    useEffect(() => {
        getHistory(field).then(setHistory).catch(() => { });
    }, [field]);
    // Close on outside click
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
                setShowSuggestions(false);
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);
    // Filter history based on current input
    const filtered = value
        ? history.filter((h) => h.toLowerCase().includes(value.toLowerCase()) && h !== value)
        : history.filter((h) => h !== value);
    // Filter external suggestions (exclude history items to avoid dupes)
    const historySet = new Set(history.map((h) => h.toLowerCase()));
    const filteredSuggestions = (suggestions ?? []).filter((s) => s !== value &&
        !historySet.has(s.toLowerCase()) &&
        (!value || s.toLowerCase().includes(value.toLowerCase())));
    const hasDropdownItems = filtered.length > 0 || filteredSuggestions.length > 0;
    const handleSelect = (suggestion: string) => {
        onChange(suggestion);
        setShowSuggestions(false);
        setActiveIndex(-1);
        onCommit?.(suggestion);
    };
    const handleBlur = () => {
        // Save to history on blur if value is non-empty
        if (value.trim()) {
            addToHistory(field, value.trim());
            // Refresh history
            getHistory(field).then(setHistory).catch(() => { });
        }
        // Delay hiding to allow click on suggestion
        setTimeout(() => setShowSuggestions(false), 200);
    };
    const handleKeyDown = (e: React.KeyboardEvent) => {
        const totalItems = filtered.length + filteredSuggestions.length;
        if (!showSuggestions || totalItems === 0)
            return;
        if (e.key === "ArrowDown") {
            e.preventDefault();
            setActiveIndex((i) => Math.min(i + 1, totalItems - 1));
        }
        else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActiveIndex((i) => Math.max(i - 1, 0));
        }
        else if (e.key === "Enter" && activeIndex >= 0) {
            e.preventDefault();
            const all = [...filtered, ...filteredSuggestions];
            handleSelect(all[activeIndex]);
        }
        else if (e.key === "Escape") {
            setShowSuggestions(false);
        }
    };
    return (<div ref={wrapperRef} className={styles.wrapper}>
      <TextField id={id} value={value} onChange={(event) => {
            const d = { value: event.target.value };
            onChange(d.value);
            setShowSuggestions(true);
            setActiveIndex(-1);
        }} onFocus={() => setShowSuggestions(true)} onBlur={handleBlur} onKeyDown={handleKeyDown} placeholder={placeholder} type={type} disabled={disabled} fullWidth size="small"/>
      {showSuggestions && hasDropdownItems && !disabled && (<div className={styles.suggestions}>
          {filtered.map((s, i) => (<div key={s} className={`${styles.suggestion} ${i === activeIndex ? styles.suggestionActive : ""}`} onMouseDown={() => handleSelect(s)}>
              <span className={styles.suggestionIcon}>&#x1F552;</span>
              {s}
            </div>))}
          {filteredSuggestions.length > 0 && (<>
              {(filtered.length > 0 || suggestionsLabel) && (<div style={{
                        padding: `${"8px"} ${"24px"}`,
                        fontSize: "12px",
                        color: "var(--m3-colorNeutralForeground3)",
                        fontWeight: 600,
                        borderTop: filtered.length > 0 ? `1px solid ${"var(--m3-colorNeutralStroke2)"}` : undefined,
                    }}>
                  {suggestionsLabel ?? "Suggestions"}
                </div>)}
              {filteredSuggestions.map((s, i) => {
                    const idx = filtered.length + i;
                    return (<div key={s} className={`${styles.suggestion} ${idx === activeIndex ? styles.suggestionActive : ""}`} onMouseDown={() => handleSelect(s)}>
                    {s}
                  </div>);
                })}
            </>)}
        </div>)}
    </div>);
}

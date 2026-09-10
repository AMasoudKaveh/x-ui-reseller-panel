import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";

import {
  translations,
  type Language,
  type TranslationKey
} from "./translations";

import {
  installUiTranslation
} from "./domTranslate";

type LanguageContextValue = {
  language: Language;
  isRtl: boolean;
  setLanguage: (language: Language) => void;
  t: (key: TranslationKey) => string;
};

const STORAGE_KEY = "xui-language";

const LanguageContext =
  createContext<LanguageContextValue | null>(null);

function isLanguage(value: string | null): value is Language {
  return value === "en" || value === "fa";
}

export function LanguageProvider({
  children
}: {
  children: ReactNode;
}) {

  const [language, setLanguageState] =
    useState<Language>(() => {

      if (typeof window === "undefined") {
        return "en";
      }

      const saved =
        localStorage.getItem(STORAGE_KEY);

      return isLanguage(saved)
        ? saved
        : "en";
    });


  const isRtl =
    language === "fa";


  useEffect(() => {

    const html =
      document.documentElement;

    html.lang = language;

    html.dir =
      isRtl
        ? "rtl"
        : "ltr";

    html.dataset.language =
      language;

  }, [
    language,
    isRtl
  ]);


  useEffect(() => {

    return installUiTranslation(
      language
    );

  }, [language]);


  const setLanguage =
    useCallback(
      (nextLanguage: Language) => {

        localStorage.setItem(
          STORAGE_KEY,
          nextLanguage
        );

        setLanguageState(
          nextLanguage
        );

      },
      []
    );


  const t =
    useCallback(
      (key: TranslationKey) =>
        translations[language][key],
      [language]
    );


  const value =
    useMemo(
      () => ({
        language,
        isRtl,
        setLanguage,
        t
      }),
      [
        language,
        isRtl,
        setLanguage,
        t
      ]
    );


  return (
    <LanguageContext.Provider
      value={value}
    >
      {children}
    </LanguageContext.Provider>
  );
}


export function useLanguage() {

  const value =
    useContext(
      LanguageContext
    );

  if (!value) {

    throw new Error(
      "useLanguage must be used inside LanguageProvider"
    );
  }

  return value;
}

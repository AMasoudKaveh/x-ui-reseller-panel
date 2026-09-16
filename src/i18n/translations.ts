export type Language = "en" | "fa";

const en = {
  "language.label": "Language",
  "language.english": "English",
  "language.persian": "Persian",

  "sidebar.resellerPanel": "Reseller Panel",
  "sidebar.adminPanel": "Admin Panel",
  "sidebar.platform": "Platform",

  "nav.dashboard": "Dashboard",
  "nav.users": "Users",
  "nav.api": "API",
  "nav.settings": "Settings",
  "nav.representatives": "Representatives",
  "nav.clients": "Clients",
  "nav.inbounds": "Inbounds",

  "sidebar.supportUs": "Support Us",
  "sidebar.githubProject": "GitHub Project",
  "sidebar.telegramChannel": "Open Source Lab",

  "sidebar.switchLight": "Switch to light mode",
  "sidebar.switchDark": "Switch to dark mode",
  "sidebar.toggleColor": "Toggle color mode",
  "sidebar.collapse": "Collapse sidebar",

  "sidebar.usage": "Usage",
  "sidebar.remaining": "Remaining",
  "sidebar.totalUsage": "Total Usage",
  "sidebar.totalUsers": "Total Users",
  "sidebar.loadingProfile": "Loading profile...",
  "sidebar.loading": "Loading...",
  "sidebar.profileUnavailable": "Profile unavailable",
  "sidebar.logout": "Log out",
  "sidebar.operator": "Operator",

  "sidebar.superAdmin": "Super Admin",
  "sidebar.superAdministrator": "Super Administrator",
  "sidebar.fullManagement": "Full management access",
  "sidebar.allInbounds": "All inbounds visible",
  "sidebar.allRepresentativesClients": "All representatives & clients"
} as const;

export type TranslationKey = keyof typeof en;

const fa: Record<TranslationKey, string> = {
  "language.label": "زبان",
  "language.english": "انگلیسی",
  "language.persian": "فارسی",

  "sidebar.resellerPanel": "پنل نماینده",
  "sidebar.adminPanel": "پنل مدیریت",
  "sidebar.platform": "پنل",

  "nav.dashboard": "داشبورد",
  "nav.users": "کاربران",
  "nav.api": "API",
  "nav.settings": "تنظیمات",
  "nav.representatives": "نمایندگان",
  "nav.clients": "کاربران",
  "nav.inbounds": "اینباندها",

  "sidebar.supportUs": "پشتیبانی",
  "sidebar.githubProject": "پروژه GitHub",
  "sidebar.telegramChannel": "کانال Open Source Lab",

  "sidebar.switchLight": "تغییر به حالت روشن",
  "sidebar.switchDark": "تغییر به حالت تاریک",
  "sidebar.toggleColor": "تغییر حالت نمایش",
  "sidebar.collapse": "جمع کردن منو",

  "sidebar.usage": "مصرف",
  "sidebar.remaining": "باقی‌مانده",
  "sidebar.totalUsage": "مصرف کل",
  "sidebar.totalUsers": "تعداد کاربران",
  "sidebar.loadingProfile": "در حال دریافت اطلاعات...",
  "sidebar.loading": "در حال بارگذاری...",
  "sidebar.profileUnavailable": "اطلاعات حساب در دسترس نیست",
  "sidebar.logout": "خروج",
  "sidebar.operator": "اپراتور",

  "sidebar.superAdmin": "مدیر کل",
  "sidebar.superAdministrator": "مدیر کل سیستم",
  "sidebar.fullManagement": "دسترسی کامل مدیریتی",
  "sidebar.allInbounds": "دسترسی به همه اینباندها",
  "sidebar.allRepresentativesClients": "دسترسی به همه نمایندگان و کاربران"
};

export const translations: Record<
  Language,
  Record<TranslationKey, string>
> = {
  en,
  fa
};

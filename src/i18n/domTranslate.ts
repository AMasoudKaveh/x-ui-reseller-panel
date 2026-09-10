import type {
  Language
} from "./translations";


const EXACT_FA: Record<string, string> = {

  /* COMMON */
  "Dashboard": "داشبورد",
  "Users": "کاربران",
  "Clients": "کاربران",
  "Representatives": "نمایندگان",
  "Representative": "نماینده",
  "Inbounds": "اینباندها",
  "Inbound": "اینباند",
  "Settings": "تنظیمات",
  "Theme": "پوسته",
  "API": "API",

  "Active": "فعال",
  "Online": "آنلاین",
  "Offline": "آفلاین",
  "Enabled": "فعال",
  "Disabled": "غیرفعال",
  "Suspended": "تعلیق‌شده",
  "Expired": "منقضی",
  "Revoked": "لغوشده",
  "Unlimited": "نامحدود",

  "Status": "وضعیت",
  "Usage": "مصرف",
  "Traffic": "ترافیک",
  "Data Usage": "مصرف دیتا",
  "Traffic Usage": "مصرف ترافیک",
  "Consumed Traffic": "ترافیک مصرفی",
  "Total Traffic": "ترافیک کل",
  "Remaining": "باقی‌مانده",
  "Total": "کل",
  "Total:": "کل:",

  "Search": "جستجو",
  "Refresh": "بروزرسانی",
  "Save": "ذخیره",
  "Cancel": "انصراف",
  "Close": "بستن",
  "Remove": "حذف",
  "Modify": "ویرایش",
  "Delete": "حذف",
  "Copy": "کپی",
  "Copied": "کپی شد",
  "Revoke": "لغو",
  "Success": "موفق",

  "Previous": "قبلی",
  "Next": "بعدی",
  "Items per page": "تعداد در هر صفحه",
  "View all": "مشاهده همه",
  "Sort Options": "گزینه‌های مرتب‌سازی",
  "Sorted by": "مرتب‌شده بر اساس",
  "Newest": "جدیدترین",
  "Oldest": "قدیمی‌ترین",

  "Username": "نام کاربری",
  "Password": "رمز عبور",
  "Current Password": "رمز عبور فعلی",
  "New Password": "رمز عبور جدید",
  "Confirm New Password": "تکرار رمز عبور جدید",
  "Created at": "تاریخ ساخت",
  "Edited at": "آخرین ویرایش",
  "Expire Date": "تاریخ انقضا",
  "Last Online": "آخرین آنلاین",
  "No expiry": "بدون انقضا",

  "Loading...": "در حال بارگذاری...",
  "Loading settings...": "در حال بارگذاری تنظیمات...",
  "Loading users...": "در حال بارگذاری کاربران...",
  "Loading representatives...": "در حال بارگذاری نمایندگان...",
  "No users found": "کاربری پیدا نشد",
  "No clients found.": "کاربری پیدا نشد.",
  "No inbounds found": "اینباندی پیدا نشد",


  /* ADMIN DASHBOARD */
  "Super Admin Management Dashboard":
    "داشبورد مدیریت ادمین",

  "Allocated Traffic":
    "حجم اختصاص داده‌شده",

  "Current active connections":
    "اتصال‌های فعال فعلی",

  "Across all representatives":
    "در بین همه نمایندگان",

  "Representative Traffic":
    "ترافیک نمایندگان",

  "Consumed traffic compared with allocated quota":
    "مقایسه ترافیک مصرفی با حجم اختصاص داده‌شده",

  "Quota, usage and current status":
    "سهمیه، مصرف و وضعیت فعلی",

  "Inbound Health":
    "وضعیت اینباندها",

  "Read-only live infrastructure overview":
    "نمای زنده و فقط‌خواندنی زیرساخت",

  "Traffic Trend":
    "روند ترافیک",

  "Representative usage during the last 7 days":
    "مصرف نمایندگان در ۷ روز اخیر",

  "7 days": "۷ روز",


  /* REPRESENTATIVES */
  "Manage reseller accounts, quota and inbound access":
    "مدیریت حساب نمایندگان، سهمیه و دسترسی اینباند",

  "Create Representative":
    "ساخت نماینده جدید",

  "Modify Representative":
    "ویرایش نماینده",

  "Search representatives":
    "جستجوی نماینده",

  "Allowed Inbounds":
    "اینباندهای مجاز",

  "assigned":
    "اختصاص داده‌شده",

  "Create panel credentials and assign traffic quota.":
    "اطلاعات ورود نماینده و سهمیه ترافیک را تعیین کنید.",

  "Representative username":
    "نام کاربری نماینده",

  "Password *":
    "رمز عبور *",

  "Login password":
    "رمز عبور ورود",

  "Leave empty to keep current":
    "برای حفظ مقدار فعلی خالی بگذارید",

  "Traffic Quota (GB)":
    "سهمیه ترافیک (GB)",

  "Representative quota is based on real traffic usage, not the sum of client limits.":
    "سهمیه نماینده بر اساس مصرف واقعی ترافیک است، نه مجموع محدودیت کاربران.",

  "Select all":
    "انتخاب همه",

  "Search inbounds":
    "جستجوی اینباند",

  "Representative usage and account overview":
    "نمای کلی حساب و مصرف نماینده",

  "Traffic Consumption":
    "مصرف ترافیک",

  "Representative Activated":
    "نماینده فعال شد",

  "Representative Suspended":
    "نماینده تعلیق شد",

  "Representative Removed":
    "نماینده حذف شد",

  "Representative Created":
    "نماینده ساخته شد",

  "Representative Updated":
    "نماینده بروزرسانی شد",

  "Usage Reset":
    "مصرف ریست شد",

  "Reset Usage":
    "ریست مصرف",

  "Suspend":
    "تعلیق",

  "Activate":
    "فعال‌سازی",


  /* CLIENTS */
  "View all clients created by representatives":
    "مشاهده همه کاربران ساخته‌شده توسط نمایندگان",

  "Search client, representative or inbound":
    "جستجوی کاربر، نماینده یا اینباند",

  "Owner":
    "نماینده",

  "Client":
    "کاربر",

  "Status / Expire":
    "وضعیت / انقضا",

  "Copy Subscription":
    "کپی اشتراک",

  "Copy Subscription Link":
    "کپی لینک اشتراک",

  "Copy Configs":
    "کپی کانفیگ‌ها",

  "QR Code":
    "کد QR",

  "Revoke Subscription":
    "لغو اشتراک",

  "Client Disabled":
    "کاربر غیرفعال شد",

  "Client Enabled":
    "کاربر فعال شد",

  "Subscription Revoked":
    "اشتراک لغو شد",

  "Client Removed":
    "کاربر حذف شد",

  "Subscription Link Copied":
    "لینک اشتراک کپی شد",

  "All Links Copied":
    "همه لینک‌ها کپی شدند",


  /* INBOUNDS */
  "Live read-only inbound monitoring":
    "مانیتورینگ زنده و فقط‌خواندنی اینباندها",

  "Search inbound":
    "جستجوی اینباند",

  "Node":
    "نود",

  "Port":
    "پورت",

  "Protocol":
    "پروتکل",

  "Clients / Online":
    "کاربران / آنلاین",

  "Speed":
    "سرعت",

  "Local panel":
    "پنل محلی",

  "Inbound configuration is intentionally read-only in this panel. Changes remain in the primary x-ui panel.":
    "تنظیمات اینباند در این پنل فقط‌خواندنی است و تغییرات باید در پنل اصلی x-ui انجام شوند.",


  /* API */
  "Manage API access for external integrations":
    "مدیریت دسترسی API برای سرویس‌های خارجی",

  "Manage administrator API access for external integrations":
    "مدیریت دسترسی API ادمین برای سرویس‌های خارجی",

  "API key created":
    "کلید API ساخته شد",

  "Copy this token now. It will not be shown again.":
    "این توکن را همین حالا کپی کنید؛ دوباره نمایش داده نمی‌شود.",

  "Create API Key":
    "ساخت کلید API",

  "Generate API Key":
    "ساخت کلید API",

  "Generate a key for bots, websites or other integrations":
    "ساخت کلید برای ربات، وب‌سایت یا سایر سرویس‌ها",

  "Key name":
    "نام کلید",

  "Expiration":
    "انقضا",

  "Never expires":
    "بدون انقضا",

  "Never":
    "هرگز",

  "30 days":
    "۳۰ روز",

  "90 days":
    "۹۰ روز",

  "1 year":
    "۱ سال",

  "Permissions":
    "دسترسی‌ها",

  "Choose what this API key can access":
    "دسترسی‌های این کلید API را انتخاب کنید",

  "API keys inherit the permissions selected above.":
    "کلید API فقط دسترسی‌های انتخاب‌شده بالا را خواهد داشت.",

  "API Keys":
    "کلیدهای API",

  "Existing keys for this reseller account":
    "کلیدهای موجود برای این حساب نماینده",

  "Existing keys for this administrator account":
    "کلیدهای موجود برای حساب ادمین",

  "Loading API keys...":
    "در حال بارگذاری کلیدهای API...",

  "No API keys created yet.":
    "هنوز کلید API ساخته نشده است.",

  "Creating...":
    "در حال ساخت...",

  "Revoking...":
    "در حال لغو...",

  "View reseller profile":
    "مشاهده پروفایل نماینده",

  "View allowed inbounds":
    "مشاهده اینباندهای مجاز",

  "View users and online status":
    "مشاهده کاربران و وضعیت آنلاین",

  "Create users":
    "ساخت کاربران",

  "Modify, enable and disable users":
    "ویرایش، فعال و غیرفعال کردن کاربران",

  "Reset user traffic":
    "ریست ترافیک کاربر",

  "Revoke subscriptions":
    "لغو اشتراک‌ها",

  "Delete users":
    "حذف کاربران",

  "View administrator profile":
    "مشاهده پروفایل ادمین",

  "View representatives and usage":
    "مشاهده نمایندگان و مصرف",

  "Create representatives":
    "ساخت نمایندگان",

  "Modify representatives":
    "ویرایش نمایندگان",

  "View all inbounds":
    "مشاهده همه اینباندها",


  /* SETTINGS */
  "Manage interface appearance":
    "مدیریت ظاهر پنل",

  "Mode":
    "حالت نمایش",

  "Choose how the interface should appear":
    "نحوه نمایش پنل را انتخاب کنید",

  "Light":
    "روشن",

  "Bright and clean":
    "روشن و ساده",

  "Dark":
    "تاریک",

  "Easy on the eyes":
    "مناسب برای محیط تاریک",

  "System":
    "سیستم",

  "Matches your device":
    "هماهنگ با تنظیمات دستگاه",

  "Color":
    "رنگ",

  "Select your preferred color scheme":
    "رنگ دلخواه پنل را انتخاب کنید",

  "Default":
    "پیش‌فرض",

  "Red":
    "قرمز",

  "Rose":
    "صورتی",

  "Orange":
    "نارنجی",

  "Green":
    "سبز",

  "Blue":
    "آبی",

  "Yellow":
    "زرد",

  "Violet":
    "بنفش",

  "Theme changed successfully":
    "پوسته با موفقیت تغییر کرد",

  "Admin-only panel settings and generated-link controls":
    "تنظیمات مخصوص ادمین و کنترل لینک‌های ساخته‌شده",

  "External Proxy":
    "پروکسی خارجی",

  "Backup":
    "پشتیبان‌گیری",

  "Admin Account":
    "حساب ادمین",

  "Configuration External Proxy":
    "پروکسی خارجی کانفیگ",

  "External Host":
    "هاست خارجی",

  "External Port":
    "پورت خارجی",

  "Save External Proxy":
    "ذخیره پروکسی خارجی",

  "Subscription External Proxy":
    "پروکسی خارجی اشتراک",

  "Subscription Host":
    "هاست اشتراک",

  "Subscription Port":
    "پورت اشتراک",

  "Save Subscription Proxy":
    "ذخیره پروکسی اشتراک",

  "Backup & Restore":
    "پشتیبان‌گیری و بازیابی",

  "Create Backup":
    "ساخت فایل پشتیبان",

  "Download Backup":
    "دانلود فایل پشتیبان",

  "Restore Backup":
    "بازیابی فایل پشتیبان",

  "Choose backup file":
    "انتخاب فایل پشتیبان",

  "Admin Credentials":
    "اطلاعات ورود ادمین",

  "Change the Super Admin username or password.":
    "نام کاربری یا رمز عبور مدیر کل را تغییر دهید.",

  "Save Credentials":
    "ذخیره اطلاعات ورود",


  /* RESELLER DASHBOARD */
  "Reseller Management Dashboard":
    "داشبورد مدیریت نماینده",

  "CPU Usage":
    "مصرف CPU",

  "RAM Usage":
    "مصرف RAM",

  "Disk Usage":
    "مصرف دیسک",

  "Uptime":
    "مدت فعالیت",

  "Active Users":
    "کاربران فعال",

  "Online Users":
    "کاربران آنلاین",

  "x-ui reseller interface":
    "پنل نمایندگی x-ui",


  /* RESELLER USERS */
  "Control, update, and manage reseller users":
    "مدیریت و ویرایش کاربران نماینده",

  "Create User":
    "ساخت کاربر",

  "Modify User":
    "ویرایش کاربر",

  "Save Changes":
    "ذخیره تغییرات",

  "Subscription copied":
    "لینک اشتراک کپی شد",

  "Configs copied":
    "کانفیگ‌ها کپی شدند",

  "Subscription revoked":
    "اشتراک لغو شد",

  "Usage reset":
    "مصرف ریست شد",

  "User enabled":
    "کاربر فعال شد",

  "User disabled":
    "کاربر غیرفعال شد",

  "User removed":
    "کاربر حذف شد",


  /* CREATE USER */
  "Create a new x-ui client":
    "ساخت کاربر جدید در x-ui",

  "Traffic Limit (GB)":
    "محدودیت حجم (GB)",

  "Expiry":
    "انقضا",

  "Comment":
    "توضیحات",

  "Advanced Options":
    "تنظیمات پیشرفته",

  "IP Limit":
    "محدودیت IP",

  "Telegram User ID":
    "شناسه کاربر تلگرام",

  "Start After First Use":
    "شروع پس از اولین استفاده",

  "Off":
    "خاموش",

  "On":
    "روشن",

  "Expiry timer starts after first traffic.":
    "زمان انقضا پس از اولین مصرف ترافیک شروع می‌شود.",

  "Duration (days)":
    "مدت (روز)",

  "Auto Renew":
    "تمدید خودکار",

  "UUID, password and subscription ID will be generated automatically.":
    "UUID، رمز و شناسه اشتراک به‌صورت خودکار ساخته می‌شوند.",

  "Attached Inbounds":
    "اینباندهای متصل",

  "Select at least one inbound":
    "حداقل یک اینباند انتخاب کنید",

  "Username is required":
    "نام کاربری الزامی است",

  "Enter username":
    "نام کاربری را وارد کنید",

  "Generate username":
    "ساخت نام کاربری",

  "Optional":
    "اختیاری",

  "Optional note for this user ...":
    "توضیحات اختیاری برای این کاربر...",

  "0 = unlimited":
    "0 = نامحدود",


  /* LOGIN */
  "Login to your account":
    "ورود به حساب کاربری",

  "Welcome back, please enter your details":
    "خوش آمدید، اطلاعات ورود خود را وارد کنید",

  "Admin Login":
    "ورود ادمین",

  "Super Admin":
    "مدیر کل",

  "Sign in to manage representatives and infrastructure":
    "برای مدیریت نمایندگان و زیرساخت وارد شوید",

  "Login":
    "ورود",

  "Checking...":
    "در حال بررسی...",

  "x-ui admin interface":
    "پنل مدیریت x-ui"
};


const ATTRIBUTES = [
  "placeholder",
  "title",
  "aria-label"
] as const;


const PROTECTED_SELECTOR = [
  "code",
  "pre",
  ".brand-name",
  ".account-name",
  ".account-popover-title-row strong",
  ".up-username-line strong",
  ".rp-name strong",
  ".ac-owner-chip",
  ".ac-inbound",
  ".ib-name strong",
  ".ib-protocol",
  ".api-key-name-row strong",
  ".api-key-prefix",
  ".cu-inbound-copy strong",
  ".cu-inbound-id",
  ".sq-config-copy strong"
].join(",");


const originalText =
  new WeakMap<Text, string>();


const originalAttributes =
  new WeakMap<
    Element,
    Map<string, string>
  >();


function normalize(
  value: string
): string {

  return value
    .replace(/\s+/g, " ")
    .trim();
}


function faDuration(
  value: string
): string {

  return value

    .replace(
      /(\d+)\s*days?/gi,
      "$1 روز"
    )

    .replace(
      /(\d+)\s*hours?/gi,
      "$1 ساعت"
    )

    .replace(
      /(\d+)\s*hrs?/gi,
      "$1 ساعت"
    )

    .replace(
      /(\d+)\s*mins?/gi,
      "$1 دقیقه"
    )

    .replace(
      /(\d+)\s*d\b/gi,
      "$1 روز"
    )

    .replace(
      /(\d+)\s*h\b/gi,
      "$1 ساعت"
    )

    .replace(
      /(\d+)\s*m\b/gi,
      "$1 دقیقه"
    );
}


export function translateUiText(
  source: string
): string {

  const text =
    normalize(source);


  if (!text) {
    return source;
  }


  if (
    Object.prototype
      .hasOwnProperty.call(
        EXACT_FA,
        text
      )
  ) {

    return EXACT_FA[text];
  }


  let match:
    RegExpMatchArray | null;


  match = text.match(
    /^(\d+)\s+active\s*[·•]\s*(\d+)\s+suspended$/i
  );

  if (match) {

    return (
      `${match[1]} فعال · `
      +
      `${match[2]} تعلیق‌شده`
    );
  }


  match = text.match(
    /^(\d+)\s+users?\s*[·•]\s*(\d+)\s+online$/i
  );

  if (match) {

    return (
      `${match[1]} کاربر · `
      +
      `${match[2]} آنلاین`
    );
  }


  match = text.match(
    /^(\d+)\s+online$/i
  );

  if (match) {

    return `${match[1]} آنلاین`;
  }


  match = text.match(
    /^(\d+)\s+available$/i
  );

  if (match) {

    return `${match[1]} در دسترس`;
  }


  match = text.match(
    /^(\d+)\s+selected$/i
  );

  if (match) {

    return `${match[1]} انتخاب‌شده`;
  }


  match = text.match(
    /^([\d.]+)%\s+used$/i
  );

  if (match) {

    return `${match[1]}% مصرف‌شده`;
  }


  match = text.match(
    /^(.+?)\s+remaining across accounts$/i
  );

  if (match) {

    return (
      `باقی‌مانده در حساب‌ها: `
      +
      match[1]
    );
  }


  match = text.match(
    /^(.+?\b(?:B|KB|MB|GB|TB|PB))\s+consumed$/i
  );

  if (match) {

    return (
      `مصرف‌شده: `
      +
      match[1]
    );
  }


  match = text.match(
    /^Expires in\s+(.+)$/i
  );

  if (match) {

    return (
      `مانده تا انقضا: `
      +
      faDuration(match[1])
    );
  }


  match = text.match(
    /^After first use(?:\s*[·•-]\s*(.+))?$/i
  );

  if (match) {

    return match[1]

      ? (
          `پس از اولین استفاده · `
          +
          faDuration(match[1])
        )

      : "پس از اولین استفاده";
  }


  match = text.match(
    /^Used\s+(.+)$/i
  );

  if (match) {

    return `مصرف‌شده: ${match[1]}`;
  }


  match = text.match(
    /^Remaining\s+(.+)$/i
  );

  if (match) {

    return `باقی‌مانده: ${match[1]}`;
  }


  match = text.match(
    /^Created:\s*(.+)$/i
  );

  if (match) {

    return `ساخته‌شده: ${match[1]}`;
  }


  match = text.match(
    /^Last used:\s*(.+)$/i
  );

  if (match) {

    return `آخرین استفاده: ${match[1]}`;
  }


  match = text.match(
    /^Expires:\s*(.+)$/i
  );

  if (match) {

    return `انقضا: ${match[1]}`;
  }


  match = text.match(
    /^Inbound #(\d+)$/i
  );

  if (match) {

    return `اینباند #${match[1]}`;
  }


  match = text.match(
    /^(\d+)\s+cores$/i
  );

  if (match) {

    return `${match[1]} هسته`;
  }


  match = text.match(
    /^(.+)\s+created successfully$/i
  );

  if (match) {

    return (
      `${match[1]} `
      +
      "با موفقیت ساخته شد"
    );
  }


  return source;
}


function isProtected(
  node: Text
): boolean {

  const parent =
    node.parentElement;


  return Boolean(
    parent
    &&
    parent.closest(
      PROTECTED_SELECTOR
    )
  );
}


function translateTextNode(
  node: Text
) {

  if (
    isProtected(node)
  ) {
    return;
  }


  const current =
    node.nodeValue ?? "";


  const stored =
    originalText.get(node);


  if (
    stored !== undefined
  ) {

    const expected =
      translateUiText(
        stored
      );


    if (
      current === expected
    ) {
      return;
    }
  }


  const translated =
    translateUiText(
      current
    );


  if (
    translated !== current
  ) {

    if (
      stored === undefined
    ) {

      originalText.set(
        node,
        current
      );
    }


    node.nodeValue =
      translated;
  }
}


function translateAttributes(
  element: Element
) {

  for (
    const attribute
    of ATTRIBUTES
  ) {

    if (
      !element.hasAttribute(
        attribute
      )
    ) {
      continue;
    }


    const current =
      element.getAttribute(
        attribute
      )
      ?? "";


    const translated =
      translateUiText(
        current
      );


    if (
      translated === current
    ) {
      continue;
    }


    let map =
      originalAttributes.get(
        element
      );


    if (!map) {

      map = new Map();

      originalAttributes.set(
        element,
        map
      );
    }


    if (
      !map.has(attribute)
    ) {

      map.set(
        attribute,
        current
      );
    }


    element.setAttribute(
      attribute,
      translated
    );
  }
}


function translateTree(
  root: Node
) {

  if (
    root.nodeType
    ===
    Node.TEXT_NODE
  ) {

    translateTextNode(
      root as Text
    );

    return;
  }


  if (
    root instanceof Element
  ) {

    translateAttributes(root);
  }


  const walker =
    document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT
    );


  let node =
    walker.nextNode();


  while (node) {

    translateTextNode(
      node as Text
    );

    node =
      walker.nextNode();
  }


  if (
    root instanceof Element
    ||
    root instanceof Document
    ||
    root instanceof DocumentFragment
  ) {

    root
      .querySelectorAll?.(
        "[placeholder],[title],[aria-label]"
      )
      .forEach(
        translateAttributes
      );
  }
}


function restoreTree(
  root: Node
) {

  const restoreText =
    (node: Text) => {

      const original =
        originalText.get(
          node
        );


      if (
        original === undefined
      ) {
        return;
      }


      node.nodeValue =
        original;


      originalText.delete(
        node
      );
    };


  if (
    root.nodeType
    ===
    Node.TEXT_NODE
  ) {

    restoreText(
      root as Text
    );

    return;
  }


  const walker =
    document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT
    );


  let node =
    walker.nextNode();


  while (node) {

    restoreText(
      node as Text
    );

    node =
      walker.nextNode();
  }


  if (
    root instanceof Element
    ||
    root instanceof Document
    ||
    root instanceof DocumentFragment
  ) {

    root
      .querySelectorAll?.(
        "[placeholder],[title],[aria-label]"
      )
      .forEach(
        element => {

          const map =
            originalAttributes.get(
              element
            );


          if (!map) {
            return;
          }


          map.forEach(
            (
              value,
              key
            ) => {

              element.setAttribute(
                key,
                value
              );
            }
          );


          originalAttributes.delete(
            element
          );
        }
      );
  }
}


export function installUiTranslation(
  language: Language
): () => void {

  const root =
    document.body;


  if (!root) {

    return () => {};
  }


  if (
    language === "en"
  ) {

    restoreTree(root);

    return () => {};
  }


  translateTree(root);


  const observer =
    new MutationObserver(
      mutations => {

        for (
          const mutation
          of mutations
        ) {

          if (
            mutation.type
            ===
            "characterData"
          ) {

            translateTree(
              mutation.target
            );

            continue;
          }


          if (
            mutation.type
            ===
            "attributes"
          ) {

            translateTree(
              mutation.target
            );

            continue;
          }


          mutation
            .addedNodes
            .forEach(
              translateTree
            );
        }
      }
    );


  observer.observe(
    root,
    {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: [
        "placeholder",
        "title",
        "aria-label"
      ]
    }
  );


  const originalConfirm =
    window.confirm;


  const translatedConfirm =
    (
      message?: string
    ) => {

      return originalConfirm.call(
        window,
        translateUiText(
          String(
            message ?? ""
          )
        )
      );
    };


  window.confirm =
    translatedConfirm;


  return () => {

    observer.disconnect();


    if (
      window.confirm
      ===
      translatedConfirm
    ) {

      window.confirm =
        originalConfirm;
    }
  };
}

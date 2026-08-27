import {
  ChevronDown,
  ChevronLeft,
  CircleHelp,
  LayoutGrid,
  LogOut,
  Moon,
  Settings2,
  Sun,
  UserRound,
  UsersRound
} from "lucide-react";

import {
  useEffect,
  useRef,
  useState
} from "react";

import type {
  AppPage
} from "../App";

import {
  getResellerProfile,
  type ResellerProfile
} from "../api/reseller";

import {
  formatBytes
} from "../utils/formatBytes";

import {
  useThemeSettings
} from "../theme/ThemeProvider";


type Props = {

  page: AppPage;

  setPage:
    (page: AppPage) => void;

  username?: string;

  onLogout?: () => void;
};


const nav = [

  {
    icon: LayoutGrid,
    label: "Dashboard",
    page: "dashboard" as AppPage
  },

  {
    icon: UsersRound,
    label: "Users",
    page: "users" as AppPage
  },

  {
    icon: Settings2,
    label: "Settings",
    page: "settings" as AppPage
  }

];


export default function Sidebar({

  page,
  setPage,
  username,
  onLogout

}: Props) {

  const {
    resolvedMode,
    toggleQuickMode
  } = useThemeSettings();


  const [
    accountOpen,
    setAccountOpen
  ] = useState(false);


  const [
    profile,
    setProfile
  ] = useState<
    ResellerProfile | null
  >(null);


  const [
    profileLoading,
    setProfileLoading
  ] = useState(true);


  const [
    profileError,
    setProfileError
  ] = useState("");


  const accountRef =
    useRef<HTMLDivElement>(
      null
    );


  useEffect(() => {

    let active = true;


    getResellerProfile()

      .then((result) => {

        if (!active) {
          return;
        }

        setProfile(
          result
        );

        setProfileError("");

      })

      .catch((error) => {

        if (!active) {
          return;
        }

        setProfileError(
          error instanceof Error
            ? error.message
            : "Profile unavailable"
        );

      })

      .finally(() => {

        if (active) {

          setProfileLoading(
            false
          );
        }
      });


    return () => {

      active = false;
    };

  }, []);


  useEffect(() => {

    const onPointerDown =
      (
        event: MouseEvent
      ) => {

        if (
          !accountRef.current
            ?.contains(
              event.target as Node
            )
        ) {

          setAccountOpen(
            false
          );
        }
      };


    document.addEventListener(
      "mousedown",
      onPointerDown
    );


    return () => {

      document.removeEventListener(
        "mousedown",
        onPointerDown
      );
    };

  }, []);


  const handleLogout = () => {

    setAccountOpen(
      false
    );

    onLogout?.();
  };


  const shownUsername =
    profile?.username
    ||
    username
    ||
    "Reseller";


  const usedText =
    profile
      ? formatBytes(
          profile.used_bytes
        )
      : "—";


  const quotaText =
    profile
      ? formatBytes(
          profile.quota_bytes
        )
      : "—";


  const remainingText =
    profile
      ? formatBytes(
          profile.remaining_bytes
        )
      : "—";


  const usagePercent =
    profile
      ? Math.min(
          100,
          Math.max(
            0,
            profile.usage_percent
          )
        )
      : 0;


  const progressStyle = {

    width:
      `${usagePercent}%`,

    minWidth:
      profile
      &&
      profile.used_bytes > 0
        ? "2px"
        : "0px"

  };


  return (

    <aside className="sidebar">

      <div className="brand-row">

        <div className="brand-mark">
          X
        </div>


        <div className="brand-copy">

          <div className="brand-name">
            x-ui
          </div>

          <div className="brand-version">
            Reseller Panel
          </div>

        </div>


        <button
          className="
            icon-button
            brand-collapse
          "
          type="button"
          aria-label="Collapse sidebar"
        >

          <ChevronLeft
            size={18}
            strokeWidth={1.8}
          />

        </button>

      </div>


      <div className="nav-section-label">
        Platform
      </div>


      <nav className="nav-list">

        {
          nav.map(
            (item) => {

              const Icon =
                item.icon;

              const active =
                item.page === page;


              return (

                <button
                  className={
                    `nav-item ${
                      active
                        ? "active"
                        : ""
                    }`
                  }
                  key={item.label}
                  type="button"
                  onClick={() =>
                    setPage(
                      item.page
                    )
                  }
                >

                  <Icon
                    size={18}
                    strokeWidth={1.8}
                  />

                  <span>
                    {item.label}
                  </span>

                </button>
              );
            }
          )
        }

      </nav>


      <div className="sidebar-spacer" />


      <div className="sidebar-support">

        <div className="support-row">

          <CircleHelp
            size={18}
            strokeWidth={1.7}
          />

          <span>
            Support Us
          </span>

        </div>


        <div className="sidebar-utility-row">

          <button
            className="mini-button"
            type="button"
            onClick={
              toggleQuickMode
            }
            title={
              resolvedMode === "dark"
                ? "Switch to light mode"
                : "Switch to dark mode"
            }
            aria-label="Toggle color mode"
          >

            {
              resolvedMode === "dark"
                ? (
                  <Sun
                    size={16}
                    strokeWidth={1.8}
                  />
                )
                : (
                  <Moon
                    size={16}
                    strokeWidth={1.8}
                  />
                )
            }

          </button>

        </div>

      </div>


      <div
        className="account-menu-wrap"
        ref={accountRef}
      >

        {
          accountOpen
          ? (

            <div className="account-popover">

              <div className="account-popover-main">

                <div className="account-popover-title-row">

                  <strong>
                    {shownUsername}
                  </strong>


                  <span className="account-role-chip">

                    <UserRound
                      size={14}
                      strokeWidth={1.8}
                    />

                    {
                      profile
                        ?.display_role
                      ||
                      "operator"
                    }

                  </span>

                </div>


                <div className="account-popover-stat">

                  <span>◷</span>

                  <span>
                    Usage:
                    {" "}
                    {usedText}
                    {" / "}
                    {quotaText}
                  </span>

                </div>


                <div className="account-popover-progress">

                  <div
                    className="account-popover-progress-fill"
                    style={
                      progressStyle
                    }
                  />

                </div>


                <div className="account-popover-stat">

                  <span>◫</span>

                  <span>
                    Remaining:
                    {" "}
                    {remainingText}
                  </span>

                </div>


                <div className="account-popover-stat">

                  <span>▥</span>

                  <span>
                    Total Usage:
                    {" "}
                    {usedText}
                  </span>

                </div>


                <div className="account-popover-stat">

                  <UsersRound
                    size={15}
                    strokeWidth={1.7}
                  />

                  <span>
                    Total Users:
                    {" "}
                    {
                      profile
                        ?.total_users
                      ??
                      "—"
                    }
                  </span>

                </div>


                {
                  profileLoading
                  ? (

                    <div className="muted">
                      Loading profile...
                    </div>

                  )
                  : null
                }


                {
                  profileError
                  ? (

                    <div
                      className="muted"
                      style={{
                        color:
                          "#ef7676"
                      }}
                    >

                      {profileError}

                    </div>

                  )
                  : null
                }

              </div>


              <button
                className="account-logout-button"
                type="button"
                onClick={
                  handleLogout
                }
              >

                <LogOut
                  size={19}
                  strokeWidth={1.8}
                />

                <span>
                  Log out
                </span>

              </button>

            </div>

          )
          : null
        }


        <button
          className={
            `account-panel account-panel-button ${
              accountOpen
                ? "open"
                : ""
            }`
          }
          type="button"
          onClick={() =>
            setAccountOpen(
              (prev) => !prev
            )
          }
          aria-expanded={
            accountOpen
          }
        >

          <div className="account-main-row">

            <div>

              <div className="account-name">

                {shownUsername}

              </div>


              <div className="account-usage">

                {
                  profile
                    ? (
                      <>
                        {usedText}
                        {" / "}
                        {quotaText}
                      </>
                    )
                    : profileLoading
                      ? "Loading..."
                      : "Profile unavailable"
                }

              </div>

            </div>


            <ChevronDown
              className="account-chevron"
              size={17}
              strokeWidth={1.8}
            />

          </div>


          <div className="quota-track">

            <div
              className="quota-fill"
              style={
                progressStyle
              }
            />

          </div>

        </button>

      </div>

    </aside>
  );
}

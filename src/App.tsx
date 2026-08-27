import {
  useEffect,
  useState,
} from "react";

import Sidebar
  from "./components/Sidebar";

import DashboardPage
  from "./pages/DashboardPage";

import UsersPage
  from "./pages/UsersPage";

import SettingsPage
  from "./pages/SettingsPage";

import LoginPage
  from "./pages/LoginPage";

import AdminLoginPage
  from "./pages/admin/AdminLoginPage";

import AdminShell
  from "./shell/AdminShell";

import {
  getCurrentUser,
  logout,
  type AuthUser,
} from "./api/auth";

import {
  ThemeProvider,
} from "./theme/ThemeProvider";


export type AppPage =
  | "dashboard"
  | "users"
  | "settings";


type Portal =
  | "admin"
  | "reseller";


function getPortalFromHash():
Portal {

  return window.location.hash
    .startsWith("#/admin")
      ? "admin"
      : "reseller";
}


function getResellerPageFromHash():
AppPage {

  const hash =
    window.location.hash;


  if (
    hash.startsWith(
      "#/reseller/users"
    )
  ) {

    return "users";
  }


  if (
    hash.startsWith(
      "#/reseller/settings"
    )
  ) {

    return "settings";
  }


  return "dashboard";
}


function ResellerPanel({

  username,
  onLogout,

}: {

  username: string;
  onLogout: () => void;

}) {

  const [page, setPage] =
    useState<AppPage>(
      getResellerPageFromHash
    );


  useEffect(() => {

    const syncPageFromHash =
      () => {

        setPage(
          getResellerPageFromHash()
        );
      };


    window.addEventListener(
      "hashchange",
      syncPageFromHash
    );


    syncPageFromHash();


    return () => {

      window.removeEventListener(
        "hashchange",
        syncPageFromHash
      );
    };

  }, []);


  const navigatePage =
    (
      nextPage: AppPage
    ) => {

      const nextHash =
        `#/reseller/${nextPage}`;


      setPage(
        nextPage
      );


      if (
        window.location.hash
        !==
        nextHash
      ) {

        window.location.hash =
          nextHash;
      }
    };


  return (

    <div className="app-shell">

      <Sidebar
        page={page}
        setPage={navigatePage}
        username={username}
        onLogout={onLogout}
      />


      <div className="content-shell">

        {
          page === "dashboard"
          &&
          <DashboardPage />
        }


        {
          page === "users"
          &&
          <UsersPage />
        }


        {
          page === "settings"
          &&
          <SettingsPage />
        }

      </div>

    </div>
  );
}


function AppShell() {

  const [portal, setPortal] =
    useState<Portal>(
      getPortalFromHash
    );


  const [authUser, setAuthUser] =
    useState<AuthUser | null>(
      null
    );


  const [
    checkingSession,
    setCheckingSession
  ] = useState(true);


  useEffect(() => {

    if (!window.location.hash) {

      window.location.hash =
        "#/reseller/login";
    }


    const onHashChange = () => {

      setPortal(
        getPortalFromHash()
      );
    };


    window.addEventListener(
      "hashchange",
      onHashChange
    );


    getCurrentUser()

      .then(
        setAuthUser
      )

      .finally(() => {

        setCheckingSession(false);
      });


    return () => {

      window.removeEventListener(
        "hashchange",
        onHashChange
      );
    };

  }, []);


  const doLogout =
    async (
      target: Portal
    ) => {

      await logout();

      setAuthUser(null);

      window.location.hash =
        `#/${target}/login`;
    };


  if (checkingSession) {

    return (

      <main className="login-page">

        <section className="login-card">

          <div className="login-logo">

            <div className="login-logo-mark">
              X
            </div>

            <div className="login-logo-word">
              x-ui
            </div>

          </div>


          <div className="login-heading">

            <p>
              Checking session...
            </p>

          </div>

        </section>

      </main>
    );
  }


  /*
   * ADMIN
   */

  if (portal === "admin") {

    if (
      !authUser ||
      authUser.role !== "admin"
    ) {

      return (

        <AdminLoginPage

          onLogin={(user) => {

            setAuthUser(user);

            window.location.hash =
              "#/admin/dashboard";
          }}

        />
      );
    }


    return (

      <AdminShell

        username={
          authUser.username
        }

        onLogout={() =>
          void doLogout("admin")
        }

      />
    );
  }


  /*
   * RESELLER
   */

  if (
    !authUser ||
    authUser.role !== "reseller"
  ) {

    return (

      <LoginPage

        onLogin={(user) => {

          setAuthUser(user);

          window.location.hash =
            "#/reseller/dashboard";
        }}

      />
    );
  }


  return (

    <ResellerPanel

      username={
        authUser.username
      }

      onLogout={() =>
        void doLogout(
          "reseller"
        )
      }

    />
  );
}


export default function App() {

  return (

    <ThemeProvider>

      <AppShell />

    </ThemeProvider>
  );
}

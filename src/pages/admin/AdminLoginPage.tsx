import {
  LogIn,
  Moon,
  ShieldCheck,
  Sun,
} from "lucide-react";

import {
  FormEvent,
  useState,
} from "react";

import {
  loginAdmin,
  type AuthUser,
} from "../../api/auth";

import {
  useThemeSettings,
} from "../../theme/ThemeProvider";


type Props = {

  onLogin:
    (user: AuthUser) => void;
};


export default function AdminLoginPage({
  onLogin,
}: Props) {

  const {
    resolvedMode,
    toggleQuickMode,
  } = useThemeSettings();


  const [username, setUsername] =
    useState("");

  const [password, setPassword] =
    useState("");

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState("");


  const submit =
    async (
      event: FormEvent
    ) => {

      event.preventDefault();


      if (
        !username.trim() ||
        !password.trim() ||
        loading
      ) {
        return;
      }


      setLoading(true);

      setError("");


      try {

        const user =
          await loginAdmin(
            username.trim(),
            password,
          );


        onLogin(user);

      } catch (err) {

        setError(
          err instanceof Error
            ? err.message
            : "Login failed"
        );

      } finally {

        setLoading(false);
      }
    };


  return (

    <main
      className="
        login-page
        admin-login-page
      "
    >

      <div className="login-top-actions">

        <div />


        <button
          className="login-top-button"
          type="button"
          onClick={toggleQuickMode}
          aria-label="Toggle theme"
        >

          {
            resolvedMode === "dark"
              ? <Sun size={17} />
              : <Moon size={17} />
          }

        </button>

      </div>


      <section className="login-card">

        <div className="login-logo">

          <div className="login-logo-mark">
            X
          </div>

          <div className="login-logo-word">
            x-ui
          </div>

        </div>


        <div className="admin-login-badge">

          <ShieldCheck size={15} />

          Super Admin

        </div>


        <div className="login-heading">

          <h1>
            Admin Login
          </h1>

          <p>
            Sign in to manage
            representatives and infrastructure
          </p>

        </div>


        <form
          className="login-form"
          onSubmit={submit}
        >

          <label className="login-field">

            <span>Username</span>

            <input
              autoComplete="username"
              value={username}
              onChange={(e) =>
                setUsername(
                  e.target.value
                )
              }
              placeholder="Username"
              disabled={loading}
            />

          </label>


          <label className="login-field">

            <span>Password</span>

            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) =>
                setPassword(
                  e.target.value
                )
              }
              placeholder="Password"
              disabled={loading}
            />

          </label>


          {
            error && (

              <div className="login-error">

                {error}

              </div>
            )
          }


          <button
            className="login-submit"
            type="submit"
            disabled={
              !username.trim() ||
              !password.trim() ||
              loading
            }
          >

            <LogIn size={18} />

            <span>

              {
                loading
                  ? "Checking..."
                  : "Login"
              }

            </span>

          </button>

        </form>

      </section>


      <footer className="login-footer">

        x-ui admin interface

      </footer>

    </main>
  );
}

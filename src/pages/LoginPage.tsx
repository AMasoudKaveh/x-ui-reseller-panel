import {
  LogIn,
  Moon,
  Sun,
} from "lucide-react";

import {
  FormEvent,
  useState,
} from "react";

import {
  loginReseller,
  type AuthUser,
} from "../api/auth";

import {
  useThemeSettings,
} from "../theme/ThemeProvider";


type Props = {

  onLogin:
    (user: AuthUser) => void;
};


export default function LoginPage({
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
          await loginReseller(
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

    <main className="login-page">

      <div className="login-top-actions">

        <div />


        <button
          className="login-top-button"
          type="button"
          onClick={toggleQuickMode}
          aria-label="Toggle theme"
          title={
            resolvedMode === "dark"
              ? "Light mode"
              : "Dark mode"
          }
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


        <div className="login-heading">

          <h1>
            Login to your account
          </h1>

          <p>
            Welcome back,
            please enter your details
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
              onChange={(event) =>
                setUsername(
                  event.target.value
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
              onChange={(event) =>
                setPassword(
                  event.target.value
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

        x-ui reseller interface

      </footer>

    </main>
  );
}

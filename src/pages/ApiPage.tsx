import {
  Check,
  Copy,
  KeyRound,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2
} from "lucide-react";

import {
  useEffect,
  useState,
  type FormEvent
} from "react";

import {
  createApiKey,
  listApiKeys,
  revokeApiKey,
  type ApiKeyItem
} from "../api/apiKeys";

import { copyTextToClipboard } from "../utils/clipboard";

import "../api-page.css";


const scopeLabels: Record<string, string> = {
  "profile:read": "View reseller profile",
  "inbounds:read": "View allowed inbounds",
  "users:read": "View users and online status",
  "users:create": "Create users",
  "users:update": "Modify, enable and disable users",
  "users:reset": "Reset user traffic",
  "users:revoke": "Revoke subscriptions",
  "users:delete": "Delete users"
};


function formatTimestamp(
  value: number | null
) {
  if (!value) {
    return "Never";
  }

  return new Date(
    value * 1000
  ).toLocaleString();
}


export default function ApiPage() {

  const [
    keys,
    setKeys
  ] = useState<ApiKeyItem[]>([]);

  const [
    availableScopes,
    setAvailableScopes
  ] = useState<string[]>([]);

  const [
    selectedScopes,
    setSelectedScopes
  ] = useState<string[]>([]);

  const [
    name,
    setName
  ] = useState("");

  const [
    expiresDays,
    setExpiresDays
  ] = useState("");

  const [
    createdToken,
    setCreatedToken
  ] = useState("");

  const [
    loading,
    setLoading
  ] = useState(true);

  const [
    creating,
    setCreating
  ] = useState(false);

  const [
    revokingId,
    setRevokingId
  ] = useState<number | null>(
    null
  );

  const [
    copied,
    setCopied
  ] = useState(false);

  const [
    error,
    setError
  ] = useState("");


  const loadKeys = async (
    preserveScopes = false
  ) => {

    setLoading(true);
    setError("");

    try {

      const result =
        await listApiKeys();

      setKeys(
        result.keys
      );

      setAvailableScopes(
        result.available_scopes
      );

      if (!preserveScopes) {
        setSelectedScopes(
          result.available_scopes
        );
      }

    } catch (err) {

      setError(
        err instanceof Error
          ? err.message
          : "Unable to load API keys"
      );

    } finally {

      setLoading(false);
    }
  };


  useEffect(() => {
    void loadKeys();
  }, []);


  const toggleScope = (
    scope: string
  ) => {

    setSelectedScopes(
      (current) => {

        if (
          current.includes(scope)
        ) {
          return current.filter(
            (item) =>
              item !== scope
          );
        }

        return [
          ...current,
          scope
        ];
      }
    );
  };


  const handleCreate = async (
    event: FormEvent<HTMLFormElement>
  ) => {

    event.preventDefault();

    const cleanName =
      name.trim();

    if (!cleanName) {
      setError(
        "API key name is required"
      );
      return;
    }

    if (
      selectedScopes.length === 0
    ) {
      setError(
        "Select at least one permission"
      );
      return;
    }

    setCreating(true);
    setError("");
    setCreatedToken("");
    setCopied(false);

    try {

      const result =
        await createApiKey({
          name: cleanName,

          scopes:
            selectedScopes,

          ...(expiresDays
            ? {
                expires_in_days:
                  Number(expiresDays)
              }
            : {})
        });

      setCreatedToken(
        result.api_key.token
      );

      setName("");
      setExpiresDays("");

      await loadKeys(true);

    } catch (err) {

      setError(
        err instanceof Error
          ? err.message
          : "Unable to create API key"
      );

    } finally {

      setCreating(false);
    }
  };


  const copyToken = async () => {

    if (!createdToken) {
      return;
    }

    const copiedSuccessfully =
      await copyTextToClipboard(
        createdToken
      );

    if (!copiedSuccessfully) {
      return;
    }

    setCopied(true);

    window.setTimeout(
      () => setCopied(false),
      1600
    );
  };


  const handleRevoke = async (
    item: ApiKeyItem
  ) => {

    const confirmed =
      window.confirm(
        `Revoke API key "${item.name}"?`
      );

    if (!confirmed) {
      return;
    }

    setRevokingId(
      item.id
    );

    setError("");

    try {

      await revokeApiKey(
        item.id
      );

      await loadKeys(true);

    } catch (err) {

      setError(
        err instanceof Error
          ? err.message
          : "Unable to revoke API key"
      );

    } finally {

      setRevokingId(null);
    }
  };


  return (
    <>
      <header className="page-header api-page-header">
        <div>
          <div className="page-title-row">
            <h1>API</h1>

            <span className="help-chip">
              ?
            </span>
          </div>

          <p>
            Manage API access for external integrations
          </p>
        </div>
      </header>


      <main className="api-page">

        {
          error
          ? (
            <div className="api-error">
              {error}
            </div>
          )
          : null
        }


        {
          createdToken
          ? (
            <section className="api-token-card">

              <div className="api-token-heading">

                <div className="api-token-icon">
                  <Check
                    size={17}
                    strokeWidth={2}
                  />
                </div>

                <div>
                  <strong>
                    API key created
                  </strong>

                  <span>
                    Copy this token now. It will not be shown again.
                  </span>
                </div>

              </div>


              <div className="api-token-value">

                <code>
                  {createdToken}
                </code>

                <button
                  type="button"
                  onClick={() =>
                    void copyToken()
                  }
                >
                  {
                    copied
                      ? (
                          <Check
                            size={16}
                          />
                        )
                      : (
                          <Copy
                            size={16}
                          />
                        )
                  }

                  {
                    copied
                      ? "Copied"
                      : "Copy"
                  }
                </button>

              </div>

            </section>
          )
          : null
        }


        <section className="api-card">

          <div className="api-section-heading">

            <div className="api-section-icon">
              <Plus
                size={18}
                strokeWidth={1.8}
              />
            </div>

            <div>
              <h2>
                Create API Key
              </h2>

              <p>
                Generate a key for bots, websites or other integrations
              </p>
            </div>

          </div>


          <form
            className="api-create-form"
            onSubmit={
              (event) =>
                void handleCreate(
                  event
                )
            }
          >

            <div className="api-form-grid">

              <label className="api-field">

                <span>
                  Key name
                </span>

                <input
                  type="text"
                  maxLength={64}
                  value={name}
                  placeholder="Example: Telegram Bot"
                  onChange={
                    (event) =>
                      setName(
                        event.target.value
                      )
                  }
                />

              </label>


              <label className="api-field">

                <span>
                  Expiration
                </span>

                <select
                  value={expiresDays}
                  onChange={
                    (event) =>
                      setExpiresDays(
                        event.target.value
                      )
                  }
                >
                  <option value="">
                    Never expires
                  </option>

                  <option value="30">
                    30 days
                  </option>

                  <option value="90">
                    90 days
                  </option>

                  <option value="365">
                    1 year
                  </option>
                </select>

              </label>

            </div>


            <div className="api-permissions-title">

              <ShieldCheck
                size={17}
                strokeWidth={1.8}
              />

              <div>
                <strong>
                  Permissions
                </strong>

                <span>
                  Choose what this API key can access
                </span>
              </div>

            </div>


            <div className="api-scope-grid">

              {
                availableScopes.map(
                  (scope) => {

                    const selected =
                      selectedScopes
                        .includes(
                          scope
                        );

                    return (
                      <button
                        key={scope}
                        type="button"
                        className={
                          `api-scope ${
                            selected
                              ? "selected"
                              : ""
                          }`
                        }
                        onClick={() =>
                          toggleScope(
                            scope
                          )
                        }
                      >

                        <span className="api-scope-check">
                          {
                            selected
                              ? (
                                  <Check
                                    size={12}
                                    strokeWidth={2.5}
                                  />
                                )
                              : null
                          }
                        </span>

                        <span className="api-scope-copy">

                          <strong>
                            {scope}
                          </strong>

                          <small>
                            {
                              scopeLabels[
                                scope
                              ]
                              ||
                              scope
                            }
                          </small>

                        </span>

                      </button>
                    );
                  }
                )
              }

            </div>


            <div className="api-create-footer">

              <span>
                API keys inherit the permissions selected above.
              </span>

              <button
                className="api-primary-button"
                type="submit"
                disabled={creating}
              >
                <KeyRound
                  size={17}
                  strokeWidth={1.8}
                />

                {
                  creating
                    ? "Creating..."
                    : "Generate API Key"
                }
              </button>

            </div>

          </form>

        </section>


        <section className="api-card">

          <div className="api-keys-header">

            <div className="api-section-heading api-section-heading-no-margin">

              <div className="api-section-icon">
                <KeyRound
                  size={18}
                  strokeWidth={1.8}
                />
              </div>

              <div>
                <h2>
                  API Keys
                </h2>

                <p>
                  Existing keys for this reseller account
                </p>
              </div>

            </div>


            <button
              className="api-refresh-button"
              type="button"
              disabled={loading}
              onClick={() =>
                void loadKeys(true)
              }
            >
              <RefreshCw
                size={16}
                className={
                  loading
                    ? "api-spin"
                    : ""
                }
              />

              Refresh
            </button>

          </div>


          <div className="api-key-list">

            {
              loading
              ? (
                <div className="api-empty">
                  Loading API keys...
                </div>
              )
              : keys.length === 0
                ? (
                    <div className="api-empty">
                      No API keys created yet.
                    </div>
                  )
                : (
                    keys.map(
                      (item) => (
                        <div
                          className="api-key-row"
                          key={item.id}
                        >

                          <div className="api-key-main">

                            <div className="api-key-name-row">

                              <strong>
                                {item.name}
                              </strong>

                              <span
                                className={
                                  item.active
                                    ? "api-status active"
                                    : "api-status revoked"
                                }
                              >
                                {
                                  item.active
                                    ? "Active"
                                    : "Revoked"
                                }
                              </span>

                            </div>


                            <code className="api-key-prefix">
                              {item.key_prefix}••••••••
                            </code>


                            <div className="api-key-meta">

                              <span>
                                Created:{" "}
                                {formatTimestamp(
                                  item.created_at
                                )}
                              </span>

                              <span>
                                Last used:{" "}
                                {formatTimestamp(
                                  item.last_used_at
                                )}
                              </span>

                              <span>
                                Expires:{" "}
                                {
                                  item.expires_at
                                    ? formatTimestamp(
                                        item.expires_at
                                      )
                                    : "Never"
                                }
                              </span>

                            </div>


                            <div className="api-key-scopes">

                              {
                                item.scopes.map(
                                  (scope) => (
                                    <span key={scope}>
                                      {scope}
                                    </span>
                                  )
                                )
                              }

                            </div>

                          </div>


                          {
                            item.active
                            ? (
                                <button
                                  className="api-revoke-button"
                                  type="button"
                                  disabled={
                                    revokingId
                                    ===
                                    item.id
                                  }
                                  onClick={() =>
                                    void handleRevoke(
                                      item
                                    )
                                  }
                                >
                                  <Trash2
                                    size={16}
                                    strokeWidth={1.8}
                                  />

                                  {
                                    revokingId
                                    ===
                                    item.id
                                      ? "Revoking..."
                                      : "Revoke"
                                  }
                                </button>
                              )
                            : null
                          }

                        </div>
                      )
                    )
                  )
            }

          </div>

        </section>

      </main>
    </>
  );
}

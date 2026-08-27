import {
  useEffect,
  useMemo,
  useState
} from "react";

import {
  Ban,
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Copy,
  Link2,
  MoreVertical,
  PencilLine,
  Plus,
  QrCode,
  RefreshCcw,
  Search,
  Signal,
  SortAsc,
  Trash2,
  Unlink,
  UserCheck,
  UsersRound,
  Wifi
} from "lucide-react";

import CreateUserModal
  from "../components/CreateUserModal";

import ModifyUserModal
  from "../components/ModifyUserModal";

import SubscriptionModal
  from "../components/SubscriptionModal";

import {
  getUserAccess,
  removeUser,
  resetUserUsage,
  revokeSubscription,
  toggleUser
} from "../api/userActions";


import {
  getResellerUsers,
  type ResellerUser,
  type UsersSummary
} from "../api/users";

import {
  formatBytes
} from "../utils/formatBytes";

import "../users.css";


type SortKey =
  | "username"
  | "created"
  | "edited"
  | "expiry"
  | "usage"
  | "lastOnline";


type ToastState = {
  message: string;
  userId: string;
} | null;


const sortOptions = [

  {
    key: "username" as SortKey,
    label: "Username",
    icon: UsersRound
  },

  {
    key: "created" as SortKey,
    label: "Created at",
    icon: CalendarDays
  },

  {
    key: "edited" as SortKey,
    label: "Edited at",
    icon: PencilLine
  },

  {
    key: "expiry" as SortKey,
    label: "Expire Date",
    icon: CalendarDays
  },

  {
    key: "usage" as SortKey,
    label: "Data Usage",
    icon: Signal
  },

  {
    key: "lastOnline" as SortKey,
    label: "Last Online",
    icon: Clock3
  }
];


const emptySummary:
UsersSummary = {

  total: 0,

  active: 0,

  online: 0,

  disabled: 0,

  expired: 0,

  on_hold: 0
};


function StatCard({

  type,
  label,
  value

}: {

  type:
    | "online"
    | "active"
    | "users";

  label: string;

  value: number;

}) {

  return (

    <section
      className="up-stat-card"
    >

      <div
        className="up-stat-left"
      >

        {
          type === "online"

            ? (
              <span
                className="
                  up-online-dot
                "
              />
            )

            : type === "active"

              ? (
                <UserCheck
                  size={23}
                />
              )

              : (
                <UsersRound
                  size={23}
                />
              )
        }


        <span>
          {label}
        </span>

      </div>


      <strong>
        {value}
      </strong>

    </section>
  );
}


function timestamp(
  value:
    string | null
): number {

  if (!value) {
    return 0;
  }


  const parsed =
    Date.parse(value);


  if (
    Number.isNaN(parsed)
  ) {

    return 0;
  }


  return parsed;
}


function sortValue(
  user: ResellerUser,
  key: SortKey
):

number | string {

  switch (key) {

    case "username":

      return user.username
        .toLowerCase();


    case "created":

      return timestamp(
        user.created_at
      );


    case "edited":

      return timestamp(
        user.updated_at
      );


    case "expiry":

      return (
        user.expire_at_ms > 0
          ? user.expire_at_ms
          : Number.MAX_SAFE_INTEGER
      );


    case "usage":

      return user.used_bytes;


    case "lastOnline":

      return timestamp(
        user.last_online_at
      );


    default:

      return 0;
  }
}


export default function UsersPage() {

  const [
    users,
    setUsers
  ] = useState<
    ResellerUser[]
  >([]);


  const [
    summary,
    setSummary
  ] = useState<
    UsersSummary
  >(
    emptySummary
  );


  const [
    loading,
    setLoading
  ] = useState(true);


  const [
    error,
    setError
  ] = useState("");


  const [
    createOpen,
    setCreateOpen
  ] = useState(false);


  const [
    modifyUser,
    setModifyUser
  ] = useState<
    ResellerUser | null
  >(null);


  const [
    subscriptionUser,
    setSubscriptionUser
  ] = useState<
    ResellerUser | null
  >(null);


  const [
    globalToast,
    setGlobalToast
  ] = useState("");


const [
    sortOpen,
    setSortOpen
  ] = useState(false);


  const [
    sortKey,
    setSortKey
  ] = useState<SortKey>(
    "created"
  );


  const [
    direction,
    setDirection
  ] = useState<
    "newest" | "oldest"
  >(
    "newest"
  );


  const [
    search,
    setSearch
  ] = useState("");


  const [
    copyMenuFor,
    setCopyMenuFor
  ] = useState<
    string | null
  >(null);


  const [
    moreMenuFor,
    setMoreMenuFor
  ] = useState<
    string | null
  >(null);


  const [
    toast,
    setToast
  ] = useState<
    ToastState
  >(null);


  const [
    page,
    setPage
  ] = useState(1);


  const itemsPerPage = 10;


  const loadUsers =
    async (silent = false) => {

      if (!silent) {
        setLoading(true);
      }


      try {

        const result =
          await getResellerUsers();


        setUsers(
          result.users
        );


        setSummary(
          result.summary
        );


        setError("");

      } catch (err) {

        setError(
          err instanceof Error
            ? err.message
            : "Users unavailable"
        );

      } finally {

        if (!silent) {
          setLoading(false);
        }
      }
    };


  useEffect(() => {

    void loadUsers();

    const liveTimer =
      window.setInterval(
        () => {
          void loadUsers(true);
        },
        10000
      );

    return () => {
      window.clearInterval(
        liveTimer
      );
    };

  }, []);


  const sortedUsers =
    useMemo(
      () => {

        const normalized =
          search
            .trim()
            .toLowerCase();


        const filtered =
          users.filter(
            user =>
              user.username
                .toLowerCase()
                .includes(
                  normalized
                )
              ||
              (
                user.customer_name
                || ""
              )
                .toLowerCase()
                .includes(
                  normalized
                )
          );


        return [
          ...filtered
        ].sort(
          (
            left,
            right
          ) => {

            const a =
              sortValue(
                left,
                sortKey
              );


            const b =
              sortValue(
                right,
                sortKey
              );


            if (
              typeof a
              ===
              "string"
              &&
              typeof b
              ===
              "string"
            ) {

              return a.localeCompare(
                b
              );
            }


            const numericA =
              Number(a);

            const numericB =
              Number(b);


            if (
              direction
              ===
              "newest"
            ) {

              return (
                numericB
                -
                numericA
              );
            }


            return (
              numericA
              -
              numericB
            );
          }
        );

      },
      [
        users,
        search,
        sortKey,
        direction
      ]
    );


  const totalPages =
    Math.max(
      1,

      Math.ceil(
        sortedUsers.length
        /
        itemsPerPage
      )
    );


  const currentPage =
    Math.min(
      page,
      totalPages
    );


  const visibleUsers =
    sortedUsers.slice(
      (
        currentPage - 1
      )
      *
      itemsPerPage,

      currentPage
      *
      itemsPerPage
    );


  const selectedSort =
    sortOptions.find(
      item =>
        item.key
        ===
        sortKey
    )
    ||
    sortOptions[0];


  const showToast = (

    userId: string,

    message: string

  ) => {

    setToast({
      userId,
      message
    });


    window.setTimeout(
      () => {

        setToast(
          current =>

            current
            ?.userId
            ===
            userId

            &&
            current.message
            ===
            message

              ? null
              : current
        );

      },
      1600
    );
  };


  const showGlobalToast = (
    message: string
  ) => {

    setGlobalToast(
      message
    );

    window.setTimeout(
      () => {
        setGlobalToast("");
      },
      1800
    );
  };


  const copyText = async (
    value: string
  ) => {

    if (
      navigator.clipboard
      &&
      window.isSecureContext
    ) {
      await navigator.clipboard.writeText(value);
      return;
    }

    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  };


  const actionError = (
    user: ResellerUser,
    err: unknown
  ) => {
    showToast(
      String(user.id),
      err instanceof Error
        ? err.message
        : "Action failed"
    );
  };


  const handleCopySubscription = async (user: ResellerUser) => {
    try {
      const access = await getUserAccess(user.id);
      if (!access.subscription_url) {
        throw new Error("Subscription URL was not returned by x-ui");
      }
      await copyText(access.subscription_url);
      showToast(String(user.id), "Subscription copied");
    } catch (err) {
      actionError(user, err);
    }
  };


  const handleCopyConfigs = async (user: ResellerUser) => {
    try {
      const access = await getUserAccess(user.id);
      const configs = access.links.join("\
");
      if (!configs) {
        throw new Error("No config links returned by x-ui");
      }
      await copyText(configs);
      showToast(String(user.id), "Configs copied");
    } catch (err) {
      actionError(user, err);
    }
  };


  const handleRevokeSubscription = async (user: ResellerUser) => {
    if (!window.confirm(`Revoke the current subscription URL for ${user.username}?`)) return;
    try {
      await revokeSubscription(user.id);
      showGlobalToast("Subscription revoked");
      if (subscriptionUser?.id === user.id) setSubscriptionUser(null);
      await loadUsers();
    } catch (err) {
      actionError(user, err);
    }
  };


  const handleResetUsage = async (user: ResellerUser) => {
    if (!window.confirm(`Reset current x-ui traffic for ${user.username}? Representative cumulative usage will not decrease.`)) return;
    try {
      await resetUserUsage(user.id);
      showGlobalToast("Usage reset");
      await loadUsers();
    } catch (err) {
      actionError(user, err);
    }
  };


  const handleToggleUser = async (user: ResellerUser) => {
    const nextEnabled = !user.enabled;
    try {
      await toggleUser(user.id, nextEnabled);
      showGlobalToast(nextEnabled ? "User enabled" : "User disabled");
      await loadUsers();
    } catch (err) {
      actionError(user, err);
    }
  };


  const handleRemoveUser = async (user: ResellerUser) => {
    if (!window.confirm(`Remove ${user.username} from x-ui? This cannot be undone.`)) return;
    try {
      await removeUser(user.id);
      showGlobalToast("User removed");
      await loadUsers();
    } catch (err) {
      actionError(user, err);
    }
  };

  return (

    <>

      <header
        className="
          page-header
          users-header
        "
      >

        <div>

          <div
            className="
              page-title-row
            "
          >

            <h1>
              Users
            </h1>


            <span
              className="
                help-chip
              "
            >
              ?
            </span>

          </div>


          <p>
            Control, update, and manage reseller users
          </p>

        </div>


        <button
          className="
            up-create-button
          "
          type="button"
          onClick={() =>
            setCreateOpen(true)
          }
        >

          <Plus size={20} />

          Create User

        </button>

      </header>


      <main
        className="up-page"
        onClick={() => {

          setCopyMenuFor(
            null
          );

          setMoreMenuFor(
            null
          );

          setSortOpen(
            false
          );
        }}
      >

        <section
          className="
            up-stats-grid
          "
        >

          <StatCard
            type="online"
            label="Online Users"
            value={
              summary.online
            }
          />


          <StatCard
            type="active"
            label="Active Users"
            value={
              summary.active
            }
          />


          <StatCard
            type="users"
            label="Users"
            value={
              summary.total
            }
          />

        </section>


        {
          error
            ? (
              <div
                className="
                  up-api-error
                "
              >
                {error}
              </div>
            )
            : null
        }


        <section
          className="
            up-toolbar
          "
        >

          <div
            className="
              up-search-box
            "
          >

            <Search size={18} />


            <input
              value={search}
              onChange={event => {

                setSearch(
                  event.target.value
                );

                setPage(1);
              }}
              placeholder="Search"
            />

          </div>


          <div
            className="
              up-sort-wrap
            "
          >

            <button
              className={
                `up-tool-button ${
                  sortOpen
                    ? "active"
                    : ""
                }`
              }
              type="button"
              onClick={event => {

                event.stopPropagation();

                setSortOpen(
                  !sortOpen
                );
              }}
              title="Sort"
            >

              <SortAsc
                size={19}
              />

            </button>


            {
              sortOpen
                ? (

                  <div
                    className="
                      up-sort-menu
                    "
                    onClick={event =>
                      event
                        .stopPropagation()
                    }
                  >

                    <div
                      className="
                        up-sort-title
                      "
                    >
                      Sort Options
                    </div>


                    {
                      sortOptions.map(
                        option => {

                          const Icon =
                            option.icon;


                          const active =
                            option.key
                            ===
                            sortKey;


                          return (

                            <div
                              key={
                                option.key
                              }
                              className={
                                `up-sort-option ${
                                  active
                                    ? "active"
                                    : ""
                                }`
                              }
                            >

                              <button
                                type="button"
                                className="
                                  up-sort-option-main
                                "
                                onClick={() => {

                                  setSortKey(
                                    option.key
                                  );

                                  setPage(1);
                                }}
                              >

                                <Icon
                                  size={17}
                                />


                                <span>
                                  {
                                    option.label
                                  }
                                </span>

                              </button>


                              {
                                active
                                &&
                                option.key
                                !==
                                "username"

                                  ? (

                                    <button
                                      className="
                                        up-sort-direction
                                      "
                                      type="button"
                                      onClick={() => {

                                        setDirection(
                                          direction
                                          ===
                                          "newest"

                                            ? "oldest"

                                            : "newest"
                                        );

                                        setPage(1);
                                      }}
                                    >

                                      {
                                        direction
                                        ===
                                        "newest"

                                          ? "Newest"

                                          : "Oldest"
                                      }


                                      <ChevronDown
                                        size={15}
                                      />

                                    </button>

                                  )

                                  : null
                              }

                            </div>
                          );
                        }
                      )
                    }

                  </div>
                )

                : null
            }

          </div>


          <div
            className="
              up-sort-summary
            "
          >

            <span>
              Sorted by
            </span>


            <strong>
              {
                selectedSort.label
              }
            </strong>


            {
              sortKey
              !==
              "username"

                ? (

                  <small>

                    ·
                    {" "}

                    {
                      direction
                      ===
                      "newest"

                        ? "Newest"

                        : "Oldest"
                    }

                  </small>

                )

                : null
            }

          </div>

        </section>


        <section
          className="
            up-table-card
          "
        >

          <div
            className="
              up-table-head
            "
          >

            <label
              className="
                up-check
              "
            >

              <input
                type="checkbox"
              />

              <span />

            </label>


            <div>
              Username
            </div>


            <div>
              Status / Expire
            </div>


            <div>
              Data Usage
            </div>


            <div />

          </div>


          <div
            className="
              up-table-body
            "
          >

            {
              loading
                ? (

                  <div
                    className="
                      up-empty-state
                    "
                  >
                    Loading users...
                  </div>

                )

                : visibleUsers.length
                  ===
                  0

                    ? (

                      <div
                        className="
                          up-empty-state
                        "
                      >
                        No users found
                      </div>

                    )

                    : (

                      visibleUsers.map(
                        user => {

                          const userId =
                            String(
                              user.id
                            );


                          const limitText =
                            user
                              .traffic_limit_bytes
                            > 0

                              ? formatBytes(
                                  user
                                    .traffic_limit_bytes
                                )

                              : "Unlimited";


                          const usedText =
                            formatBytes(
                              user.used_bytes
                            );


                          const totalText =
                            formatBytes(
                              user
                                .total_used_bytes
                            );


                          const usageWidth =
                            user
                              .traffic_limit_bytes
                            > 0

                              ? Math.min(
                                  100,
                                  Math.max(
                                    0,
                                    user
                                      .usage_percent
                                  )
                                )

                              : 0;


                          return (

                            <div
                              className="
                                up-user-row
                              "
                              key={
                                user.id
                              }
                            >

                              <label
                                className="
                                  up-check
                                "
                              >

                                <input
                                  type="checkbox"
                                />

                                <span />

                              </label>


                              <div
                                className="
                                  up-name-cell
                                "
                              >

                                <span
                                  className={
                                    `up-presence ${
                                      user.online
                                        ? "online"
                                        : ""
                                    }`
                                  }
                                />


                                <div
                                  className="
                                    up-username-line
                                  "
                                >

                                  <strong>
                                    {
                                      user.username
                                    }
                                  </strong>


                                  <span>

                                    #
                                    {
                                      user.id
                                    }

                                  </span>


                                  <span>
                                    {
                                      user.age
                                    }
                                  </span>

                                </div>

                              </div>


                              <div
                                className="
                                  up-status-cell
                                "
                              >

                                <span
                                  className={
                                    `up-active-pill ${
                                      user.status_code
                                    }`
                                  }
                                >

                                  <Wifi
                                    size={14}
                                  />

                                  {
                                    user.status
                                  }

                                </span>


                                <span
                                  className="
                                    up-expiry
                                  "
                                >

                                  {
                                    user
                                      .expire_at_ms
                                    > 0

                                      ? (
                                        user.status_code
                                        ===
                                        "expired"

                                          ? "Expired"

                                          : `Expires in ${user.expires_in}`
                                      )

                                      : "No expiry"
                                  }

                                </span>

                              </div>


                              <div
                                className="
                                  up-usage-cell
                                "
                              >

                                <div
                                  className="
                                    up-usage-progress
                                  "
                                >

                                  <div
                                    className="
                                      up-usage-fill
                                    "
                                    style={{
                                      width:
                                        `${usageWidth}%`
                                    }}
                                  />

                                </div>


                                <div
                                  className="
                                    up-usage-line
                                  "
                                >

                                  <span>

                                    {
                                      usedText
                                    }

                                    {" / "}

                                    {
                                      limitText
                                    }

                                  </span>


                                  <span>

                                    Total:
                                    {" "}

                                    {
                                      totalText
                                    }

                                  </span>

                                </div>

                              </div>


                              <div
                                className="
                                  up-actions
                                "
                                onClick={
                                  event =>
                                    event
                                      .stopPropagation()
                                }
                              >

                                {
                                  toast
                                  ?.userId
                                  ===
                                  userId

                                    ? (
                                      <div
                                        className="
                                          ua-action-toast
                                        "
                                      >
                                        {toast.message}
                                      </div>
                                    )
                                    : null
                                }

                                <button
                                  type="button"
                                  title="Copy Subscription Link"
                                  onClick={() =>
                                    void handleCopySubscription(user)
                                  }
                                >
                                  <Link2 size={18} />
                                </button>

                                <div className="ua-action-wrap">
                                  <button
                                    type="button"
                                    title="Copy Configs"
                                    onClick={() => {
                                      setCopyMenuFor(copyMenuFor === userId ? null : userId);
                                      setMoreMenuFor(null);
                                    }}
                                  >
                                    <Copy size={18} />
                                  </button>

                                  {
                                    copyMenuFor === userId
                                      ? (
                                        <div className="ua-copy-menu">
                                          <div className="ua-menu-label">Copy Configs</div>
                                          <button
                                            type="button"
                                            onClick={() => {
                                              void handleCopyConfigs(user);
                                              setCopyMenuFor(null);
                                            }}
                                          >
                                            <Link2 size={17} />
                                            <span>links</span>
                                          </button>
                                        </div>
                                      )
                                      : null
                                  }
                                </div>

                                <button
                                  type="button"
                                  title="QR Code"
                                  onClick={() => setSubscriptionUser(user)}
                                >
                                  <QrCode size={18} />
                                </button>

                                <div className="ua-action-wrap">
                                  <button
                                    type="button"
                                    title="More"
                                    onClick={() => {
                                      setMoreMenuFor(moreMenuFor === userId ? null : userId);
                                      setCopyMenuFor(null);
                                    }}
                                  >
                                    <MoreVertical size={18} />
                                  </button>

                                  {
                                    moreMenuFor === userId
                                      ? (
                                        <div className="ua-more-menu">
                                          <button
                                            type="button"
                                            onClick={() => {
                                              setModifyUser(user);
                                              setMoreMenuFor(null);
                                            }}
                                          >
                                            <PencilLine size={18} />
                                            <span>Modify</span>
                                          </button>

                                          <button
                                            type="button"
                                            onClick={() => {
                                              void handleRevokeSubscription(user);
                                              setMoreMenuFor(null);
                                            }}
                                          >
                                            <Unlink size={18} />
                                            <span>Revoke Subscription</span>
                                          </button>

                                          <button
                                            type="button"
                                            onClick={() => {
                                              void handleResetUsage(user);
                                              setMoreMenuFor(null);
                                            }}
                                          >
                                            <RefreshCcw size={18} />
                                            <span>Reset Usage</span>
                                          </button>

                                          <div className="ua-menu-divider" />

                                          <button
                                            type="button"
                                            className="ua-warning"
                                            onClick={() => {
                                              void handleToggleUser(user);
                                              setMoreMenuFor(null);
                                            }}
                                          >
                                            <Ban size={18} />
                                            <span>{user.enabled ? "Disable" : "Enable"}</span>
                                          </button>

                                          <button
                                            type="button"
                                            className="ua-danger"
                                            onClick={() => {
                                              void handleRemoveUser(user);
                                              setMoreMenuFor(null);
                                            }}
                                          >
                                            <Trash2 size={18} />
                                            <span>Remove</span>
                                          </button>
                                        </div>
                                      )
                                      : null
                                  }
                                </div>

                              </div>

                            </div>
                          );
                        }
                      )
                    )
            }

          </div>

        </section>


        <section
          className="
            up-pagination
          "
        >

          <div
            className="
              up-items-per-page
            "
          >

            <button
              type="button"
            >

              {itemsPerPage}

              <ChevronDown
                size={16}
              />

            </button>


            <span>
              Items per page
            </span>

          </div>


          <div
            className="
              up-pagination-right
            "
          >

            <button
              type="button"
              disabled={
                currentPage
                <=
                1
              }
              onClick={() =>
                setPage(
                  Math.max(
                    1,
                    currentPage - 1
                  )
                )
              }
            >

              <ChevronLeft
                size={18}
              />

              Previous

            </button>


            <button
              className="
                up-current-page
              "
              type="button"
            >

              {currentPage}

            </button>


            <button
              type="button"
              disabled={
                currentPage
                >=
                totalPages
              }
              onClick={() =>
                setPage(
                  Math.min(
                    totalPages,
                    currentPage + 1
                  )
                )
              }
            >

              Next

              <ChevronRight
                size={18}
              />

            </button>

          </div>

        </section>

      </main>


      <CreateUserModal
        open={
          createOpen
        }
        onClose={() =>
          setCreateOpen(false)
        }
        onCreated={async () => {
          setCreateOpen(false);
          await loadUsers();
        }}
      />

      <ModifyUserModal
        open={modifyUser !== null}
        userId={modifyUser?.id ?? null}
        onClose={() => setModifyUser(null)}
        onSaved={async () => {
          setModifyUser(null);
          await loadUsers();
        }}
      />

      <SubscriptionModal
        open={subscriptionUser !== null}
        userId={subscriptionUser?.id ?? null}
        username={subscriptionUser?.username ?? ""}
        onClose={() => setSubscriptionUser(null)}
        onCopied={showGlobalToast}
      />

      {
        globalToast
          ? (
            <div className="ua-global-toast">
              {globalToast}
            </div>
          )
          : null
      }

    </>
  );
}

import {
  FormEvent,
  useEffect,
  useMemo,
  useState
} from "react";

import {
  Check,
  ChevronDown,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Server,
  SlidersHorizontal,
  UserPlus,
  X
} from "lucide-react";

import {
  createXuiUser,
  getXuiInbounds,
  type XuiInbound
} from "../api/createUser";


type Props = {
  open: boolean;

  onClose: () => void;

  onCreated?: () =>
    void | Promise<void>;
};


function generateUsername() {

  const chars =
    "abcdefghjkmnpqrstuvwxyz23456789";

  let value = "user-";

  for (
    let index = 0;
    index < 7;
    index += 1
  ) {

    value +=
      chars[
        Math.floor(
          Math.random()
          *
          chars.length
        )
      ];
  }

  return value;
}


export default function CreateUserModal({
  open,
  onClose,
  onCreated
}: Props) {

  const [
    username,
    setUsername
  ] = useState("");


  const [
    traffic,
    setTraffic
  ] = useState("");


  const [
    expiry,
    setExpiry
  ] = useState("");



  const [
    startAfterFirstUse,
    setStartAfterFirstUse
  ] = useState(false);

  const [
    startAfterDays,
    setStartAfterDays
  ] = useState("30");

const [
    enabled,
    setEnabled
  ] = useState(true);


  const [
    comment,
    setComment
  ] = useState("");


  const [
    limitIp,
    setLimitIp
  ] = useState("0");


  const [
    telegramId,
    setTelegramId
  ] = useState("");


  const [
    advancedOpen,
    setAdvancedOpen
  ] = useState(false);


  const [
    inbounds,
    setInbounds
  ] = useState<
    XuiInbound[]
  >([]);


  const [
    selected,
    setSelected
  ] = useState<
    number[]
  >([]);


  const [
    search,
    setSearch
  ] = useState("");


  const [
    loadingInbounds,
    setLoadingInbounds
  ] = useState(false);


  const [
    saving,
    setSaving
  ] = useState(false);


  const [
    error,
    setError
  ] = useState("");


  const [
    success,
    setSuccess
  ] = useState("");


  useEffect(() => {

    if (!open) {
      return;
    }


    let alive = true;


    setError("");

    setSuccess("");

    setSearch("");

    setLoadingInbounds(true);


    getXuiInbounds()

      .then(rows => {

        if (!alive) {
          return;
        }


        setInbounds(
          rows
        );


        setSelected(
          current => {

            const valid =
              current.filter(
                id =>
                  rows.some(
                    item =>
                      item.id
                      ===
                      id
                  )
              );


            return valid;
          }
        );

      })

      .catch(err => {

        if (!alive) {
          return;
        }


        setError(
          err instanceof Error
            ? err.message
            : "Unable to load x-ui inbounds"
        );

      })

      .finally(() => {

        if (alive) {

          setLoadingInbounds(
            false
          );
        }
      });


    return () => {

      alive = false;
    };

  }, [open]);


  useEffect(() => {

    // ADMIN_STEP2_CREATE_MODAL_INBOUND_POLL
    if (!open) {
      return;
    }

    let alive = true;

    const refresh = async () => {
      try {
        const rows = await getXuiInbounds();
        if (!alive) return;
        setInbounds(rows);
        setSelected(current =>
          current.filter(id => rows.some(item => item.id === id))
        );
      } catch {
        // Preserve the last successful list on a temporary x-ui error.
      }
    };

    const timer = window.setInterval(() => void refresh(), 3000);
    const focus = () => void refresh();
    window.addEventListener("focus", focus);

    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", focus);
    };

  }, [open]);


  const visibleInbounds =
    useMemo(
      () => {

        const query =
          search
            .trim()
            .toLowerCase();


        if (!query) {
          return inbounds;
        }


        return inbounds.filter(
          item => {

            const text = [
              item.label,
              item.remark,
              item.protocol,
              item.network,
              item.security,
              item.port,
              item.id
            ]
              .join(" ")
              .toLowerCase();


            return text.includes(
              query
            );
          }
        );

      },
      [
        inbounds,
        search
      ]
    );


  if (!open) {
    return null;
  }


  const toggleInbound = (
    id: number
  ) => {

    setSelected(
      current =>

        current.includes(id)

          ? current.filter(
              item =>
                item !== id
            )

          : [
              ...current,
              id
            ]
    );
  };


  const submit =
    async (
      event: FormEvent
    ) => {

      event.preventDefault();


      if (saving) {
        return;
      }


      if (!username.trim()) {

        setError(
          "Username is required"
        );

        return;
      }


      if (
        selected.length
        ===
        0
      ) {

        setError(
          "Select at least one inbound"
        );

        return;
      }


      setSaving(true);

      setError("");

      setSuccess("");


      try {

        const result =
          await createXuiUser(
            {
              username:
                username.trim(),

              traffic_gb:
                Math.max(
                  0,
                  Number(
                    traffic
                    ||
                    0
                  )
                ),

              expiry_date:
                expiry,


              start_after_first_use:
                startAfterFirstUse,

              start_after_days:
                startAfterFirstUse
                  ? Math.max(
                      1,
                      Number(
                        startAfterDays
                        ||
                        0
                      )
                    )
                  : 0,
enabled,

              comment:
                comment.trim(),

              inbound_ids:
                selected,

              limit_ip:
                Math.max(
                  0,
                  Number(
                    limitIp
                    ||
                    0
                  )
                ),

              telegram_user_id:
                telegramId.trim()
            }
          );


        setSuccess(
          `${result.user.username} created successfully`
        );


        await new Promise(
          resolve =>
            window.setTimeout(
              resolve,
              550
            )
        );


        if (onCreated) {

          await onCreated();

        } else {

          onClose();
        }


        setUsername("");

        setTraffic("");

        setExpiry("");


        setStartAfterFirstUse(false);
        setStartAfterDays("30");

setComment("");

        setLimitIp("0");

        setTelegramId("");

        setSelected([]);

        setAdvancedOpen(false);


      } catch (err) {

        setError(
          err instanceof Error
            ? err.message
            : "Create user failed"
        );

      } finally {

        setSaving(false);
      }
    };


  return (

    <div
      className="xcu-backdrop"
      onMouseDown={event => {

        if (
          event.target
          ===
          event.currentTarget
          &&
          !saving
        ) {

          onClose();
        }
      }}
    >

      <form
        className="xcu-modal"
        onSubmit={submit}
      >

        <header
          className="xcu-header"
        >

          <div
            className="xcu-title"
          >

            <UserPlus
              size={21}
            />


            <div>

              <h2>
                Create User
              </h2>

              <p>
                Create a new x-ui client
              </p>

            </div>

          </div>


          <button
            type="button"
            className="xcu-icon-btn"
            onClick={onClose}
            disabled={saving}
          >

            <X size={20} />

          </button>

        </header>


        <div
          className="xcu-content"
        >

          <section
            className="xcu-main"
          >

            {
              error
              ? (

                <div
                  className="
                    xcu-message
                    error
                  "
                >
                  {error}
                </div>

              )
              : null
            }


            {
              success
              ? (

                <div
                  className="
                    xcu-message
                    success
                  "
                >

                  <Check size={16} />

                  {success}

                </div>

              )
              : null
            }


            <div
              className="xcu-grid"
            >

              <label
                className="xcu-field"
              >

                <span>
                  Username
                  {" "}
                  <b>*</b>
                </span>


                <div
                  className="
                    xcu-input-action
                  "
                >

                  <input
                    value={username}
                    onChange={
                      event =>
                        setUsername(
                          event
                            .target
                            .value
                        )
                    }
                    placeholder="Enter username"
                    autoFocus
                    disabled={saving}
                  />


                  <button
                    type="button"
                    title="Generate username"
                    onClick={() =>
                      setUsername(
                        generateUsername()
                      )
                    }
                  >

                    <RefreshCw
                      size={16}
                    />

                  </button>

                </div>

              </label>


              <label
                className="xcu-field"
              >

                <span>
                  Traffic Limit (GB)
                </span>

                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={traffic}
                  onChange={
                    event =>
                      setTraffic(
                        event
                          .target
                          .value
                      )
                  }
                  placeholder="0 = unlimited"
                  disabled={saving}
                />

              </label>


              <label
                className="xcu-field"
              >

                <span>
                  Expiry
                </span>

                <input
                  type="date"
                  value={expiry}
                  onChange={
                    event =>
                      setExpiry(
                        event
                          .target
                          .value
                      )
                  }
                  disabled={saving || startAfterFirstUse}
                />

              </label>


              <label
                className="xcu-field"
              >

                <span>
                  Status
                </span>

                <select
                  value={
                    enabled
                      ? "enabled"
                      : "disabled"
                  }
                  onChange={
                    event =>
                      setEnabled(
                        event
                          .target
                          .value
                        ===
                        "enabled"
                      )
                  }
                  disabled={saving}
                >

                  <option
                    value="enabled"
                  >
                    Enabled
                  </option>

                  <option
                    value="disabled"
                  >
                    Disabled
                  </option>

                </select>

              </label>


              <label
                className="
                  xcu-field
                  xcu-full
                "
              >

                <span>
                  Comment
                </span>

                <textarea
                  value={comment}
                  onChange={
                    event =>
                      setComment(
                        event
                          .target
                          .value
                      )
                  }
                  placeholder="Optional note for this user ..."
                  disabled={saving}
                />

              </label>

            </div>


            <section
              className="
                xcu-advanced
              "
            >

              <button
                type="button"
                className="
                  xcu-advanced-head
                "
                onClick={() =>
                  setAdvancedOpen(
                    current =>
                      !current
                  )
                }
              >

                <span>

                  <SlidersHorizontal
                    size={17}
                  />

                  Advanced Options

                </span>


                <ChevronDown
                  size={17}
                  className={
                    advancedOpen
                      ? "open"
                      : ""
                  }
                />

              </button>


              {
                advancedOpen
                ? (

                  <div
                    className="
                      xcu-advanced-body
                    "
                  >

                    <label
                      className="xcu-field"
                    >

                      <span>
                        IP Limit
                      </span>

                      <input
                        type="number"
                        min="0"
                        step="1"
                        value={limitIp}
                        onChange={
                          event =>
                            setLimitIp(
                              event
                                .target
                                .value
                            )
                        }
                        disabled={saving}
                      />

                      <small>
                        0 = unlimited
                      </small>

                    </label>


                    <label
                      className="xcu-field"
                    >

                      <span>
                        Telegram User ID
                      </span>

                      <input
                        value={telegramId}
                        onChange={
                          event =>
                            setTelegramId(
                              event
                                .target
                                .value
                            )
                        }
                        placeholder="Optional"
                        disabled={saving}
                      />

                    </label>


                    <label className="xcu-field">
                      <span>Start After First Use</span>
                      <select
                        value={startAfterFirstUse ? "on" : "off"}
                        onChange={event => {
                          const on = event.target.value === "on";
                          setStartAfterFirstUse(on);
                          if (on) setExpiry("");
                        }}
                        disabled={saving}
                      >
                        <option value="off">Off</option>
                        <option value="on">On</option>
                      </select>
                      <small>Expiry timer starts after first traffic.</small>
                    </label>

                    {startAfterFirstUse ? (
                      <label className="xcu-field">
                        <span>Duration (days)</span>
                        <input
                          type="number"
                          min="1"
                          max="3650"
                          step="1"
                          value={startAfterDays}
                          onChange={event => setStartAfterDays(event.target.value)}
                          disabled={saving}
                        />
                      </label>
                    ) : null}


                    <div
                      className="
                        xcu-option-row
                      "
                    >

                      <span>
                        Auto Renew
                      </span>

                      <strong>
                        Off
                      </strong>

                    </div>

                  </div>

                )
                : null
              }

            </section>


            <div
              className="
                xcu-info
              "
            >

              <Plus size={15} />

              UUID, password and
              subscription ID will be
              generated automatically.

            </div>

          </section>


          <aside
            className="
              xcu-inbounds
            "
          >

            <div
              className="
                xcu-inbound-title
              "
            >

              <div>

                <Server
                  size={18}
                />

                <strong>
                  Attached Inbounds
                </strong>

              </div>


              <span>
                {selected.length} selected
              </span>

            </div>


            <div
              className="
                xcu-search
              "
            >

              <Search
                size={16}
              />

              <input
                value={search}
                onChange={
                  event =>
                    setSearch(
                      event
                        .target
                        .value
                    )
                }
                placeholder="Search inbounds"
              />

            </div>


            <button
              type="button"
              className="
                xcu-select-all
              "
              onClick={() => {

                if (
                  selected.length
                  ===
                  inbounds.length
                ) {

                  setSelected([]);

                } else {

                  setSelected(
                    inbounds.map(
                      item =>
                        item.id
                    )
                  );
                }
              }}
              disabled={
                loadingInbounds
              }
            >

              <span
                className={
                  `xcu-checkbox ${
                    selected.length
                    > 0
                    &&
                    selected.length
                    ===
                    inbounds.length
                      ? "checked"
                      : ""
                  }`
                }
              >

                {
                  selected.length
                  > 0
                  &&
                  selected.length
                  ===
                  inbounds.length

                    ? <Check size={13} />

                    : null
                }

              </span>


              Select all

            </button>


            <div
              className="
                xcu-inbound-list
              "
            >

              {
                loadingInbounds
                ? (

                  <div
                    className="
                      xcu-loading
                    "
                  >

                    <LoaderCircle
                      size={19}
                      className="
                        xcu-spinner
                      "
                    />

                    Loading x-ui inbounds...

                  </div>

                )
                : null
              }


              {
                !loadingInbounds
                &&
                visibleInbounds
                  .map(
                    inbound => {

                      const checked =
                        selected.includes(
                          inbound.id
                        );


                      const details = [

                        inbound
                          .protocol
                          ?.toUpperCase(),

                        inbound
                          .network
                          ?.toUpperCase(),

                        inbound
                          .security
                          ?.toUpperCase()

                      ]
                        .filter(Boolean)
                        .join(" · ");


                      return (

                        <button
                          type="button"
                          key={inbound.id}
                          className={
                            `xcu-inbound-item ${
                              checked
                                ? "selected"
                                : ""
                            }`
                          }
                          onClick={() =>
                            toggleInbound(
                              inbound.id
                            )
                          }
                        >

                          <span
                            className={
                              `xcu-checkbox ${
                                checked
                                  ? "checked"
                                  : ""
                              }`
                            }
                          >

                            {
                              checked
                                ? (
                                  <Check
                                    size={13}
                                  />
                                )
                                : null
                            }

                          </span>


                          <div>

                            <strong>
                              {
                                inbound.label
                              }
                            </strong>

                            <small>
                              {details}
                            </small>

                          </div>


                          <span
                            className="
                              xcu-inbound-id
                            "
                          >

                            #
                            {
                              inbound.id
                            }

                          </span>

                        </button>
                      );
                    }
                  )
              }


              {
                !loadingInbounds
                &&
                visibleInbounds
                  .length
                ===
                0

                  ? (

                    <div
                      className="
                        xcu-empty
                      "
                    >
                      No inbounds found
                    </div>

                  )
                  : null
              }

            </div>

          </aside>

        </div>


        <footer
          className="
            xcu-footer
          "
        >

          <div />


          <div
            className="
              xcu-footer-actions
            "
          >

            <button
              type="button"
              className="
                xcu-cancel
              "
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </button>


            <button
              type="submit"
              className="
                xcu-submit
              "
              disabled={
                saving
                ||
                loadingInbounds
              }
            >

              {
                saving
                  ? (
                    <LoaderCircle
                      size={17}
                      className="
                        xcu-spinner
                      "
                    />
                  )
                  : (
                    <UserPlus
                      size={17}
                    />
                  )
              }


              {
                saving
                  ? "Creating..."
                  : "Create User"
              }

            </button>

          </div>

        </footer>

      </form>

    </div>
  );
}

import {
  Cpu,
  Database,
  HardDrive,
  MemoryStick,
  Radio,
  UsersRound
} from "lucide-react";

import {
  useEffect,
  useState
} from "react";

import MetricCard
  from "../components/MetricCard";

import StatusRows
  from "../components/StatusRows";

import UsageChart
  from "../components/UsageChart";

import {
  getResellerDashboard,
  type ResellerDashboard
} from "../api/dashboard";

import {
  formatBytes
} from "../utils/formatBytes";


function formatDuration(
  seconds: number
): string {

  if (
    !Number.isFinite(seconds)
    ||
    seconds <= 0
  ) {

    return "0 mins";
  }


  const days =
    Math.floor(
      seconds / 86400
    );


  const hours =
    Math.floor(
      (
        seconds % 86400
      )
      /
      3600
    );


  const minutes =
    Math.floor(
      (
        seconds % 3600
      )
      /
      60
    );


  if (days > 0) {

    return (
      `${days}d ${hours}h`
    );
  }


  if (hours > 0) {

    return (
      `${hours}h ${minutes}m`
    );
  }


  return `${minutes} mins`;
}


const emptyDashboard:
ResellerDashboard = {

  reseller: {
    id: 0,
    username: "",
    status: "",
    quota_bytes: 0,
    used_bytes: 0,
    remaining_bytes: 0,
    quota_percent: 0
  },

  system: {
    cpu_percent: 0,
    cpu_cores: 0,

    ram_used_bytes: 0,
    ram_total_bytes: 0,
    ram_percent: 0,

    disk_used_bytes: 0,
    disk_total_bytes: 0,
    disk_percent: 0,

    network_upload_bytes: 0,
    network_download_bytes: 0,
    network_total_bytes: 0,

    uptime_seconds: 0
  },

  users: {
    total: 0,
    active: 0,
    online: 0,
    expired: 0,
    limited: 0,
    on_hold: 0,
    disabled: 0
  },

  usage: []
};


export default function DashboardPage() {

  const [
    dashboard,
    setDashboard
  ] = useState<
    ResellerDashboard
  >(
    emptyDashboard
  );


  const [
    loading,
    setLoading
  ] = useState(true);


  const [
    error,
    setError
  ] = useState("");


  useEffect(() => {

    let active = true;


    const load = async () => {

      try {

        const result =
          await getResellerDashboard();


        if (!active) {
          return;
        }


        setDashboard(
          result
        );

        setError("");

      } catch (err) {

        if (!active) {
          return;
        }


        setError(
          err instanceof Error
            ? err.message
            : "Dashboard unavailable"
        );

      } finally {

        if (active) {
          setLoading(false);
        }
      }
    };


    void load();


    const timer =
      window.setInterval(
        () => {
          void load();
        },
        30000
      );


    return () => {

      active = false;

      window.clearInterval(
        timer
      );
    };

  }, []);


  const {
    system,
    users,
    usage
  } = dashboard;


  const activePercent =
    users.total > 0

      ? Math.round(
          (
            users.active
            /
            users.total
          )
          *
          100
        )

      : 0;


  return (

    <>

      <header
        className="page-header"
      >

        <div>

          <div
            className="
              page-title-row
            "
          >

            <h1>
              Dashboard
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
            Reseller Management Dashboard
          </p>

        </div>

      </header>


      <main
        className="
          dashboard-content
        "
      >

        {
          error
            ? (
              <div
                style={{
                  marginBottom: "16px",
                  color: "#ef7676",
                  fontSize: "12px"
                }}
              >
                {error}
              </div>
            )
            : null
        }


        <section
          className="
            dashboard-metric-grid
          "
        >

          <MetricCard
            icon={Cpu}
            title="CPU Usage"
            value={
              loading
                ? "..."
                : `${system.cpu_percent}%`
            }
            ring={
              system.cpu_percent
            }
            tag={
              `${system.cpu_cores} cores`
            }
          />


          <MetricCard
            icon={MemoryStick}
            title="RAM Usage"
            value={
              loading
                ? "..."
                : `${
                    formatBytes(
                      system.ram_used_bytes
                    )
                  }/${
                    formatBytes(
                      system.ram_total_bytes
                    )
                  }`
            }
            ring={
              system.ram_percent
            }
            tag={
              `${system.ram_percent}%`
            }
          />


          <MetricCard
            icon={HardDrive}
            title="Disk Usage"
            value={
              loading
                ? "..."
                : `${
                    formatBytes(
                      system.disk_used_bytes
                    )
                  }/${
                    formatBytes(
                      system.disk_total_bytes
                    )
                  }`
            }
            ring={
              system.disk_percent
            }
            tag={
              `${system.disk_percent}%`
            }
          />


          <MetricCard
            icon={Database}
            title="Total Traffic"
            value={
              loading
                ? "..."
                : formatBytes(
                    dashboard.reseller.used_bytes
                  )
            }
            footerRight={

              <div
                className="
                  dashboard-traffic-tags
                "
              >

                <span
                  className="
                    dashboard-traffic-down
                  "
                >

                  ↓
                  {" "}
                  {
                    formatBytes(
                      system.network_download_bytes
                    )
                  }

                </span>


                <span
                  className="
                    dashboard-traffic-up
                  "
                >

                  ↑
                  {" "}
                  {
                    formatBytes(
                      system.network_upload_bytes
                    )
                  }

                </span>

              </div>
            }
          />


          <MetricCard
            icon={Radio}
            title="Uptime"
            value={
              loading
                ? "..."
                : formatDuration(
                    system.uptime_seconds
                  )
            }
            wide
          />

        </section>


        <section
          className="
            dashboard-panel
            dashboard-users-summary
          "
        >

          <div
            className="
              dashboard-users-summary-title
            "
          >

            <div
              className="
                metric-icon
              "
            >

              <UsersRound
                size={21}
                strokeWidth={1.8}
              />

            </div>

            <span>
              Users
            </span>

          </div>


          <div
            className="
              dashboard-users-summary-grid
            "
          >

            <div
              className="
                dashboard-summary-box
              "
            >

              <span>
                Users
              </span>

              <strong>
                {users.total}
              </strong>

            </div>


            <div
              className="
                dashboard-summary-box
              "
            >

              <span>
                Active Users
              </span>


              <div
                className="
                  dashboard-summary-value-row
                "
              >

                <span
                  className="
                    status-badge
                  "
                >

                  {activePercent}%

                </span>


                <strong>
                  {users.active}
                </strong>

              </div>

            </div>


            <div
              className="
                dashboard-summary-box
              "
            >

              <span>
                Online Users
              </span>


              <div
                className="
                  dashboard-summary-value-row
                "
              >

                <span
                  className="
                    dashboard-dot
                    dashboard-green-dot
                  "
                />


                <strong>
                  {users.online}
                </strong>

              </div>

            </div>

          </div>

        </section>


        <div
          className="
            dashboard-lower-grid
          "
        >

          <StatusRows
            users={users}
          />


          <UsageChart
            usage={usage}
          />

        </div>


        <footer
          className="
            dashboard-footer
          "
        >

          x-ui reseller interface

        </footer>

      </main>

    </>
  );
}

import type {
  DashboardUsagePoint
} from "../api/dashboard";

import {
  formatBytes
} from "../utils/formatBytes";


type Props = {
  usage: DashboardUsagePoint[];
};


export default function UsageChart({
  usage
}: Props) {

  const maxBytes = Math.max(
    ...usage.map(
      item => item.bytes
    ),
    1
  );


  const periodUsage =
    usage.reduce(
      (
        total,
        item
      ) =>
        total + item.bytes,
      0
    );


  const yLabels = [
    maxBytes,
    maxBytes * 0.75,
    maxBytes * 0.50,
    maxBytes * 0.25,
    0
  ];


  return (

    <section
      className="
        dashboard-panel
        dashboard-usage-panel
      "
    >

      <div
        className="
          dashboard-usage-header
        "
      >

        <div
          className="
            dashboard-panel-heading
          "
        >

          <h3>
            Usage
          </h3>

          <p>
            Monitor reseller traffic usage over time
          </p>

        </div>


        <div
          className="
            dashboard-usage-filters
          "
        >

          <button
            type="button"
            className="
              dashboard-select-like
            "
          >

            7 days
            {" "}
            <span>⌄</span>

          </button>


          <button
            type="button"
            className="
              dashboard-select-like
            "
          >

            Auto
            {" "}
            <span>⌄</span>

          </button>

        </div>

      </div>


      <div
        className="
          dashboard-chart
        "
      >

        <div
          className="
            dashboard-chart-ylabels
          "
        >

          {
            yLabels.map(
              (
                value,
                index
              ) => (

                <span key={index}>

                  {
                    value <= 0
                      ? "0 B"
                      : formatBytes(
                          value
                        )
                  }

                </span>
              )
            )
          }

        </div>


        <div
          className="
            dashboard-chart-grid
          "
        >

          {
            [
              0,
              1,
              2,
              3,
              4
            ].map(
              number => (

                <div
                  className="
                    dashboard-grid-line
                  "
                  key={number}
                />

              )
            )
          }


          <div
            className="
              dashboard-bars
            "
          >

            {
              usage.map(
                (
                  item,
                  index
                ) => {

                  const percent =
                    item.bytes > 0

                      ? Math.max(
                          (
                            item.bytes
                            /
                            maxBytes
                          )
                          *
                          100,

                          3
                        )

                      : 0;


                  return (

                    <div
                      className="
                        dashboard-bar-wrap
                      "
                      key={item.date}
                    >

                      <div
                        className={
                          `dashboard-bar ${
                            index
                            ===
                            usage.length - 1
                              ? "active"
                              : ""
                          }`
                        }
                        style={{
                          height:
                            `${percent}%`
                        }}
                        title={
                          `${item.label}: ${formatBytes(item.bytes)}`
                        }
                      />


                      <div
                        className="
                          dashboard-bar-label
                        "
                      >

                        {item.label}

                      </div>

                    </div>
                  );
                }
              )
            }

          </div>

        </div>

      </div>


      <div
        className="
          dashboard-usage-footer
        "
      >

        <div>

          Usage During Period:
          {" "}

          <strong>
            {formatBytes(periodUsage)}
          </strong>

        </div>


        <div>
          Total traffic usage across all servers
        </div>

      </div>

    </section>
  );
}

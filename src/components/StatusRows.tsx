import {
  CircleCheckBig,
  CircleDot,
  CircleOff,
  Hourglass,
  PauseCircle,
  UsersRound
} from "lucide-react";

import type {
  DashboardUsers
} from "../api/dashboard";


type Props = {
  users: DashboardUsers;
};


export default function StatusRows({
  users
}: Props) {

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


  const rows = [

    {
      label: "Users",
      value: users.total,
      icon: UsersRound,
      color: "neutral"
    },

    {
      label: "Active Users",
      value: users.active,
      icon: CircleCheckBig,
      color: "accent",
      badge:
        `${activePercent}%`
    },

    {
      label: "Online Users",
      value: users.online,
      icon: CircleDot,
      color: "green"
    },

    {
      label: "Expired Users",
      value: users.expired,
      icon: Hourglass,
      color: "orange"
    },

    {
      label: "Limited Users",
      value: users.limited,
      icon: CircleOff,
      color: "red"
    },

    {
      label: "On Hold Users",
      value: users.on_hold,
      icon: PauseCircle,
      color: "purple"
    },

    {
      label: "Disabled Users",
      value: users.disabled,
      icon: CircleOff,
      color: "slate"
    }

  ];


  return (

    <section
      className="
        dashboard-panel
        dashboard-status-panel
      "
    >

      <div
        className="
          dashboard-panel-heading
        "
      >

        <h3>
          Users
        </h3>

        <p>
          Monitor Users
        </p>

      </div>


      <div
        className="
          dashboard-status-list
        "
      >

        {
          rows.map(
            ({
              label,
              value,
              icon: Icon,
              color,
              badge
            }) => (

              <div
                className="
                  dashboard-status-row
                "
                key={label}
              >

                <div
                  className={
                    `dashboard-status-icon ${color}`
                  }
                >

                  <Icon
                    size={24}
                    strokeWidth={1.7}
                  />

                </div>


                <div
                  className="
                    dashboard-status-label
                  "
                >
                  {label}
                </div>


                <div
                  className="
                    dashboard-status-spacer
                  "
                />


                {
                  badge
                    ? (
                      <div
                        className="
                          status-badge
                        "
                      >
                        {badge}
                      </div>
                    )
                    : null
                }


                <div
                  className="
                    dashboard-status-value
                  "
                >
                  {value}
                </div>

              </div>
            )
          )
        }

      </div>

    </section>
  );
}

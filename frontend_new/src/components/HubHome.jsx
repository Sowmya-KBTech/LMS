// ============================================================
// HubHome — the dashboard frame shared by every role (Option C)
// ============================================================
// Sidebar + main panel · greeting with one main action · a row of stat
// cards · then the role's own panels (children), laid out on a 3-column
// grid. Each role page supplies only numbers it already loads:
//
//   <HubHome
//     title="Good afternoon, Veni.M"
//     sub="Your subjects, students and activity at a glance."
//     action={{ label: "Take attendance", to: "/teacher/attendance", icon: "userCheck" }}
//     stats={[{ label: "My subjects", value: 13, hint: "Teaching this term", icon: "book", tone: "dep" }]}
//   >
//     <HomePanel title="Quick actions" span={2}>…</HomePanel>
//   </HubHome>
//
// Module on/off: the main action, stat cards and quick actions hide
// themselves when they point at a module this college has switched off
// (by their `to` path via PAGE_MODULES, or an explicit `module: "learning"`).
//
// (Kept the old name so existing imports work.)
// ============================================================

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import Icon from "./Icon";
import Navbar from "./Navbar";
import Sidebar from "./Sidebar";
import useModules, { hasModule } from "./useModules";
import { moduleForPath } from "./hubs";

// true when the item's module is on (or it belongs to core)
function useModuleFilter() {
  const modules = useModules();
  return (item) =>
    !item || hasModule(modules, item.module || (item.to ? moduleForPath(item.to) : null));
}

export default function HubHome({ title, sub, action: rawAction, stats: rawStats = [], children }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const isOn = useModuleFilter();
  const action = rawAction && isOn(rawAction) ? rawAction : null;
  const stats = rawStats.filter(isOn);

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="kb-page-head">
              <div>
                <h1>{title}</h1>
                {sub && <p>{sub}</p>}
              </div>
              {action && (
                <button type="button" className="kb-btn kb-btn--dark" onClick={() => navigate(action.to)}>
                  {action.icon && <Icon name={action.icon} />}
                  {action.label}
                </button>
              )}
            </div>

            {stats.length > 0 && (
              <div className="kb-stats">
                {stats.map((s) => (
                  <div
                    key={s.label}
                    className={`kb-stat tone-${s.tone || "brand"}${s.to ? " is-link" : ""}`}
                    role={s.to ? "link" : undefined}
                    tabIndex={s.to ? 0 : undefined}
                    onClick={s.to ? () => navigate(s.to) : undefined}
                    onKeyDown={s.to ? (e) => e.key === "Enter" && navigate(s.to) : undefined}
                  >
                    <div className="kb-stat-top">
                      <span className="kb-stat-ico"><Icon name={s.icon || "chart"} /></span>
                      <span>{s.label}</span>
                    </div>
                    <div className={`kb-stat-val ${s.valueTone || ""}`}>{s.value}</div>
                    {s.hint && <div className="kb-stat-hint">{s.hint}</div>}
                  </div>
                ))}
              </div>
            )}

            <div className="kb-dash">{children}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------- building blocks for the panels ----------------

export function HomePanel({ title, sub, action, onAction, span = 1, children }) {
  return (
    <section className={`kb-card kb-panel span-${span}`}>
      <div className="kb-panel-head">
        <div>
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {action && (
          <button type="button" className="kb-panel-link" onClick={onAction}>
            {action} <Icon name="arrowRight" />
          </button>
        )}
      </div>
      {children}
    </section>
  );
}

export function HomeRow({ pill, pillTone, title, sub, children, dim }) {
  return (
    <div className={`kb-row ${dim ? "is-dim" : ""}`}>
      {pill && <span className={`kb-pill ${pillTone || ""}`}>{pill}</span>}
      <div className="kb-grow">
        <div className="kb-row-t">{title}</div>
        {sub && <div className="kb-row-s">{sub}</div>}
      </div>
      {children}
    </div>
  );
}

// a tile in a "Quick actions" panel
export function QuickActions({ items: rawItems }) {
  const navigate = useNavigate();
  const isOn = useModuleFilter();
  const items = rawItems.filter(isOn);
  return (
    <div className="kb-quick">
      {items.map((a) => (
        <a
          key={a.title}
          href={a.to}
          className={`kb-quick-item tone-${a.tone || "brand"}`}
          onClick={(e) => {
            e.preventDefault();
            navigate(a.to);
          }}
        >
          <span className="kb-quick-ico"><Icon name={a.icon || "arrowRight"} /></span>
          <span className="kb-grow">
            <b>{a.title}</b>
            <small>{a.sub}</small>
          </span>
          <Icon name="chevronRight" className="kb-quick-go" />
        </a>
      ))}
    </div>
  );
}

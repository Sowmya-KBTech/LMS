// WAVE 3 PART 1A - page frame for the CBCS pages (Regulations, Credits and categories).
import { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import "../../App.css";
import "../../styles/Regulations.css";

export default function Shell({ title, subtitle, actions, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content rg-page">
            <div className="header-box rg-header">
              <div>
                <h1>{title}</h1>
                {subtitle && <p>{subtitle}</p>}
              </div>
              {actions && <div className="rg-actions">{actions}</div>}
            </div>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

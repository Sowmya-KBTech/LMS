// ============================================================
// ModuleGate — friendly page for modules this college doesn't have
// ============================================================
// ProtectedRoute wraps every page in this. If the page belongs to a
// module that is switched off (see PAGE_MODULES in hubs.js and
// ENABLED_MODULES in backend/.env), show a short message inside the
// normal app frame instead of a page full of failed requests.
// Core pages and unknown states (still loading, request failed) pass
// straight through.
// ============================================================

import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import Navbar from "./Navbar";
import Sidebar from "./Sidebar";
import useModules, { hasModule } from "./useModules";
import { homePath, moduleForPath, readUser } from "./hubs";

export default function ModuleGate({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const modules = useModules();
  const [open, setOpen] = useState(false);

  const mod = moduleForPath(location.pathname, location.search);
  if (hasModule(modules, mod)) return children;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="kb-page-head">
              <div>
                <h1>This feature isn't enabled</h1>
                <p>
                  Your college hasn't switched on this part of KB Tech Campus.
                  Contact your administrator if you need it.
                </p>
              </div>
              <button
                type="button"
                className="kb-btn kb-btn--dark"
                onClick={() => navigate(homePath(readUser()))}
              >
                Go to home
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

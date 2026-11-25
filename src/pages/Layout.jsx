
import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { createPageUrl } from "@/utils";
import { auth } from "@/api/entities";
import {
  LayoutGrid,
  FileText,
  Users,
  Building2,
  Menu,
  UserCircle,
  Shield,
  FileStack,
  TrendingUp,
  Package,
  ShieldAlert,
  FileSpreadsheet,
  MapPin,
  Store,
  LogOut
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { ProjectProvider } from "@/components/context/ProjectContext";
import ProjectSelector from "@/components/layout/ProjectSelector";
import NotificationsPanel from "@/components/layout/NotificationsPanel";

function LayoutContent({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Department State: 'inspection' vs 'expediting'
  const [activeDepartment, setActiveDepartment] = useState(() => {
    if (typeof window !== "undefined") {
      const path = window.location.pathname.toLowerCase();
      if (path.startsWith("/expediting")) return "expediting";
      if (path.startsWith("/inspection")) return "inspection";
      const saved = localStorage.getItem("inspectflow_active_dept");
      if (saved === "expediting" || saved === "inspection") return saved;
    }
    return "inspection";
  });

  const isExpeditingRoute = location.pathname.toLowerCase().startsWith("/expediting");
  const effectiveDepartment = isExpeditingRoute ? "expediting" : activeDepartment;

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const currentUser = await auth.me();
        if (!currentUser) {
          navigate("/login", { replace: true });
          return;
        }
        setUser(currentUser);
        // If no explicit saved department and user has expediting role, switch to expediting
        const role = currentUser?.inspection_role || currentUser?.role;
        const isExpRole = ["expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "vendor"].includes(role);
        const saved = localStorage.getItem("inspectflow_active_dept");
        if (!saved && isExpRole) {
          setActiveDepartment("expediting");
          localStorage.setItem("inspectflow_active_dept", "expediting");
        }
      } catch (error) {
        console.error("Error fetching user:", error);
      } finally {
        setLoading(false);
      }
    };
    fetchUser();
  }, []);

  // Synchronize department state with URL path & Enforce Strict Department Lockout
  useEffect(() => {
    const path = location.pathname.toLowerCase();
    const role = user?.inspection_role || user?.role;
    const isAdminUser = user?.role === "admin" || user?.inspection_role === "admin";
    const isExpRole = ["expediting_manager", "expeditor", "field_expeditor", "doc_expeditor", "vendor"].includes(role);
    const isInspRole = ["inspection_engineer", "qc_manager", "inspector", "inspection_agency"].includes(role);

    if (user && !isAdminUser) {
      if (role === "vendor") {
        setActiveDepartment("expediting");
        localStorage.setItem("inspectflow_active_dept", "expediting");
        const qSec = new URLSearchParams(location.search).get("sec");
        if (path.startsWith("/expediting") && qSec !== "portal") {
          navigate("/Expediting?sec=portal", { replace: true });
        } else if (
          !path.startsWith("/expediting") &&
          !path.startsWith("/vendorportal") &&
          !path.startsWith("/vendor-portal") &&
          !path.startsWith("/profile")
        ) {
          navigate("/Expediting?sec=portal", { replace: true });
        }
        return;
      }
      if (isExpRole) {
        setActiveDepartment("expediting");
        localStorage.setItem("inspectflow_active_dept", "expediting");
        const canVendorView = ["expediting_manager", "expeditor"].includes(role);
        const onVendorPortal = path.startsWith("/vendorportal") || path.startsWith("/vendor-portal");
        if (!path.startsWith("/expediting") && !path.startsWith("/profile") && !(canVendorView && onVendorPortal)) {
          const defaultSec = role === "field_expeditor" ? "field" : "dash";
          navigate(`/Expediting?sec=${defaultSec}`, { replace: true });
        }
        return;
      }
      if (isInspRole) {
        setActiveDepartment("inspection");
        localStorage.setItem("inspectflow_active_dept", "inspection");
        if (path.startsWith("/expediting") || path.startsWith("/vendorportal") || path.startsWith("/vendor-portal")) {
          navigate("/Inspection", { replace: true });
          return;
        }
        if (path.startsWith("/usermanagement")) {
          navigate("/Inspection", { replace: true });
          return;
        }
        if ((path.startsWith("/tpiagencies") || path.startsWith("/tpiperformance")) && role !== "qc_manager") {
          navigate("/Inspection", { replace: true });
          return;
        }
        if (path.startsWith("/inspectors") && !["inspection_engineer", "qc_manager", "inspection_agency"].includes(role)) {
          navigate("/Inspection", { replace: true });
          return;
        }
        if (path.startsWith("/upload") && !["inspection_engineer", "qc_manager"].includes(role)) {
          navigate("/Inspection", { replace: true });
          return;
        }
        return;
      }
    }

    if (path.startsWith("/expediting")) {
      setActiveDepartment("expediting");
      localStorage.setItem("inspectflow_active_dept", "expediting");
    } else if (path.startsWith("/inspection")) {
      setActiveDepartment("inspection");
      localStorage.setItem("inspectflow_active_dept", "inspection");
    }
  }, [location.pathname, location.search, user, navigate]);

  // Listen for custom department-change events
  useEffect(() => {
    const handleDeptChange = (ev) => {
      if (ev.detail?.department) {
        setActiveDepartment(ev.detail.department);
      }
    };
    window.addEventListener("department-change", handleDeptChange);
    return () => window.removeEventListener("department-change", handleDeptChange);
  }, []);

  const handleDepartmentSwitch = (dept) => {
    setActiveDepartment(dept);
    localStorage.setItem("inspectflow_active_dept", dept);
    if (dept === "expediting") {
      navigate("/Expediting?sec=dash");
    } else {
      navigate("/Inspection");
    }
  };

  const isAdmin = user?.role === "admin" || user?.inspection_role === "admin";
  const isInspectionEngineer = user?.inspection_role === "inspection_engineer";
  const isQCManager = user?.inspection_role === "qc_manager";
  const isInspector = user?.inspection_role === "inspector";
  const isInspectionAgency = user?.inspection_role === "inspection_agency";
  const isExpeditingManager = user?.role === "expediting_manager" || user?.inspection_role === "expediting_manager";
  const isExpeditor = user?.role === "expeditor" || user?.inspection_role === "expeditor";
  const isFieldExpeditor = user?.role === "field_expeditor" || user?.inspection_role === "field_expeditor";
  const isDocExpeditor = user?.role === "doc_expeditor" || user?.inspection_role === "doc_expeditor";
  const isVendor = user?.role === "vendor" || user?.inspection_role === "vendor";

  const canAccessDashboard = isAdmin || isInspectionEngineer || isQCManager || isInspector || isExpeditingManager || isExpeditor;
  const canAccessReports = isAdmin || isInspectionEngineer || isQCManager || isInspector || isExpeditingManager || isExpeditor || isDocExpeditor;
  const canAccessInspectors = isAdmin || isInspectionEngineer || isQCManager || isInspectionAgency || isExpeditingManager;
  const canAccessAgencies = isAdmin || isQCManager;
  const canAccessUserManagement = isAdmin;

  // 1. Inspection Department Navigation
  const inspectionNavItems = [
    {
      title: isInspector ? "My Inspections" : "Dashboard",
      url: "/Inspection",
      icon: LayoutGrid,
      show: canAccessDashboard,
    },
    {
      title: "IR & IRC",
      url: "/Reports",
      icon: FileStack,
      show: canAccessReports,
    },
    {
      title: "Inspectors",
      url: "/Inspectors",
      icon: Users,
      show: canAccessInspectors,
    },
    {
      title: "Agencies",
      url: "/TPIAgencies",
      icon: Building2,
      show: canAccessAgencies,
    },
    {
      title: "Performance",
      url: "/TPIPerformance",
      icon: TrendingUp,
      show: isAdmin || isQCManager,
    },
    {
      title: "Admin",
      url: "/UserManagement",
      icon: Shield,
      show: canAccessUserManagement,
    },
    {
      title: "My Profile",
      url: "/Profile",
      icon: UserCircle,
      show: isInspector,
    },
  ];

  // 2. Expediting Department Navigation
  const expeditingNavItems = isVendor
    ? [
      {
        title: "Vendor Expediting Portal",
        url: "/Expediting?sec=portal",
        icon: Store,
        show: true,
      },
      {
        title: "NOI, VDMS & Dispatch",
        url: "/VendorPortal",
        icon: Package,
        show: true,
      },
    ]
    : (() => {
      const activePo = new URLSearchParams(location.search).get("po");
      const poSuffix = activePo ? `&po=${encodeURIComponent(activePo)}` : "";
      return [
        {
          title: "Executive Dashboard",
          url: "/Expediting?sec=dash",
          icon: LayoutGrid,
          show: true,
        },
        {
          title: "PO Master Register",
          url: "/Expediting?sec=queue",
          icon: FileSpreadsheet,
          show: true,
        },
        {
          title: "Expeditor Workbench",
          url: `/Expediting?sec=core&tab=sched${poSuffix}`,
          icon: Package,
          show: true,
        },
        {
          title: "RAIL Action Tracker",
          url: "/Expediting?sec=rail",
          icon: ShieldAlert,
          show: true,
        },
        {
          title: "Field Expediting",
          url: "/Expediting?sec=field",
          icon: MapPin,
          show: true,
        },
        {
          title: "Vendor Portal",
          url: "/VendorPortal",
          icon: Store,
          show: isAdmin || isExpeditingManager || isExpeditor,
        },
      ];
    })();

  const currentNavItems = (effectiveDepartment === "expediting" ? expeditingNavItems : inspectionNavItems).filter((item) => item.show);

  const getRoleBadge = () => {
    const roleColors = {
      admin: "bg-red-100 text-red-800",
      inspection_engineer: "bg-blue-100 text-blue-800",
      qc_manager: "bg-green-100 text-green-800",
      inspector: "bg-purple-100 text-purple-800",
      inspection_agency: "bg-amber-100 text-amber-800",
      expediting_manager: "bg-indigo-100 text-indigo-800",
      expeditor: "bg-teal-100 text-teal-800",
      field_expeditor: "bg-orange-100 text-orange-800",
      doc_expeditor: "bg-cyan-100 text-cyan-800",
      vendor: "bg-emerald-100 text-emerald-800",
    };

    const roleLabels = {
      admin: "Admin",
      inspection_engineer: "Inspection Engineer",
      qc_manager: "QC Manager",
      inspector: "Inspector",
      inspection_agency: "Inspection Agency",
      expediting_manager: "Expediting Manager",
      expeditor: "Expeditor",
      field_expeditor: "Field Expeditor",
      doc_expeditor: "Doc Expeditor",
      vendor: "Vendor Portal",
    };

    const role = user?.inspection_role || user?.role;
    return (
      <Badge className={`${roleColors[role]} border font-medium`}>
        {roleLabels[role] || "User"}
      </Badge>
    );
  };

  function NavLinks({ pathname, mobile = false }) {
    return (
      <>
        {currentNavItems.map((item) => {
          let isActive = false;
          if (effectiveDepartment === "expediting") {
            if (pathname.toLowerCase().startsWith("/expediting")) {
              const currentSec = new URLSearchParams(location.search).get("sec") || "dash";
              const itemSec = new URLSearchParams(item.url.split("?")[1] || "").get("sec") || "dash";
              isActive = currentSec === itemSec;
            }
          } else {
            isActive = pathname === item.url || (item.url === "/Inspection" && pathname === "/");
          }

          return (
            <Link
              key={item.title}
              to={item.url}
              className={`flex items-center gap-2.5 px-3.5 py-2 rounded-lg transition-all duration-200 text-sm ${isActive
                ? "bg-indigo-600 text-white font-semibold shadow-md shadow-indigo-600/30"
                : "text-gray-700 hover:bg-gray-100 font-medium"
                } ${mobile ? "text-base py-3" : ""}`}
            >
              <item.icon className="w-4 h-4 shrink-0" />
              <span>{item.title}</span>
            </Link>
          );
        })}
      </>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-600">Loading application...</p>
        </div>
      </div>
    );
  }

  // If no user is authenticated, show a message
  if (!user) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center max-w-md px-6">
          <div className="w-16 h-16 bg-gradient-to-br from-indigo-600 to-indigo-700 rounded-lg flex items-center justify-center shadow-lg mx-auto mb-6">
            <FileText className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-3">InspectFlow</h1>
          <p className="text-gray-600 mb-6">
            Sign in to access your inspection management system
          </p>
          <div className="bg-white rounded-lg p-6 shadow-md text-left">
            <h2 className="font-semibold text-gray-900 mb-3">Quick Start:</h2>
            <ol className="space-y-2 text-sm text-gray-600">
              <li className="flex items-start gap-2">
                <span className="font-bold text-indigo-600">1.</span>
                <span>Click "Sign In" below to access your account</span>
              </li>
            </ol>
            <a href="/login" className="block mt-6">
              <button className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-4 rounded-lg transition-colors shadow-lg">
                Sign In
              </button>
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top App Bar - Material Design */}
      <header className="bg-white shadow-md sticky top-0 z-50">
        <div className="w-full px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                {effectiveDepartment === "expediting" ? (
                  <>
                    <div className="w-10 h-10 bg-gradient-to-br from-indigo-600 via-indigo-700 to-indigo-900 rounded-lg flex items-center justify-center shadow-lg text-white font-bold font-mono text-sm tracking-tight shadow-indigo-600/30">
                      SE
                    </div>
                    <div>
                      <h1 className="text-xl font-bold text-gray-900 leading-tight">SmartExpedit</h1>
                      <span className="text-[10px] font-semibold text-indigo-600 uppercase tracking-wider block">
                        Procurement Expediting &amp; Tracking
                      </span>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="w-10 h-10 bg-gradient-to-br from-indigo-600 to-indigo-700 rounded-lg flex items-center justify-center shadow-lg text-white shadow-indigo-600/20">
                      <FileText className="w-6 h-6" />
                    </div>
                    <div>
                      <h1 className="text-xl font-bold text-gray-900 leading-tight">InspectFlow</h1>
                      <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider block">
                        Inspection Management System
                      </span>
                    </div>
                  </>
                )}
              </div>

              {/* Department Switcher Pill in Top Bar (Strictly Admin Only) */}
              {isAdmin && (
                <div className="hidden sm:flex items-center bg-gray-100 p-1 rounded-xl border border-gray-200 shadow-inner">
                  <button
                    type="button"
                    onClick={() => handleDepartmentSwitch("inspection")}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${effectiveDepartment === "inspection"
                      ? "bg-white text-indigo-700 shadow-sm border border-gray-200/80 font-bold"
                      : "text-gray-600 hover:text-gray-900 hover:bg-gray-200/60"
                      }`}
                  >
                    <span>🔍</span>
                    <span>Inspection</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDepartmentSwitch("expediting")}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${effectiveDepartment === "expediting"
                      ? "bg-white text-indigo-700 shadow-sm border border-gray-200/80 font-bold"
                      : "text-gray-600 hover:text-gray-900 hover:bg-gray-200/60"
                      }`}
                  >
                    <span>📦</span>
                    <span>Expediting</span>
                  </button>
                </div>
              )}
            </div>

            {/* User Info & Desktop Navigation */}
            <div className="hidden md:flex items-center gap-4">
              <ProjectSelector />
              <div className="h-8 w-px bg-gray-200 mx-2" />
              <div className="flex items-center gap-3 px-3 py-1.5 bg-gray-50 rounded-lg">
                <div className="text-right">
                  <p className="text-sm font-medium text-gray-900">{user?.full_name}</p>
                  <p className="text-xs text-gray-500">{user?.email}</p>
                </div>
                {getRoleBadge()}
              </div>
              <nav className="flex items-center gap-1.5">
                <NavLinks pathname={location.pathname} />
              </nav>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => auth.signOut()}
                title="Sign Out"
                className="text-gray-600 hover:text-red-600 hover:bg-red-50"
              >
                <LogOut className="w-4 h-4 mr-1.5" />
                <span className="hidden lg:inline">Sign Out</span>
              </Button>
            </div>

            {/* Mobile Menu */}
            <Sheet>
              <SheetTrigger asChild className="md:hidden">
                <Button variant="ghost" size="icon">
                  <Menu className="w-6 h-6" />
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-72">
                <div className="flex flex-col gap-5 mt-6">
                  <div className="px-4 py-3 bg-gray-50 rounded-lg">
                    <p className="text-sm font-medium text-gray-900 mb-1">{user?.full_name}</p>
                    <p className="text-xs text-gray-500 mb-2">{user?.email}</p>
                    {getRoleBadge()}
                  </div>

                  {/* Mobile Department Switcher (Strictly Admin Only) */}
                  {isAdmin && (
                    <div className="flex items-center bg-gray-100 p-1 rounded-xl border border-gray-200">
                      <button
                        type="button"
                        onClick={() => handleDepartmentSwitch("inspection")}
                        className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-all ${effectiveDepartment === "inspection"
                          ? "bg-white text-indigo-700 shadow-sm font-bold"
                          : "text-gray-600"
                          }`}
                      >
                        <span>🔍 Inspection</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDepartmentSwitch("expediting")}
                        className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-all ${effectiveDepartment === "expediting"
                          ? "bg-white text-indigo-700 shadow-sm font-bold"
                          : "text-gray-600"
                          }`}
                      >
                        <span>📦 Expediting</span>
                      </button>
                    </div>
                  )}

                  <div className="px-1">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-3">Project</p>
                    <ProjectSelector mobile />
                  </div>
                  <div className="flex flex-col gap-2">
                    <NavLinks pathname={location.pathname} mobile />
                  </div>
                  <div className="pt-3 border-t">
                    <Button
                      variant="outline"
                      onClick={() => auth.signOut()}
                      className="w-full text-red-600 border-red-200 hover:bg-red-50"
                    >
                      <LogOut className="w-4 h-4 mr-2" />
                      Sign Out
                    </Button>
                  </div>
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      {/* Main Content Area with Collapsible Left Sidebar */}
      <div className="flex w-full min-h-[calc(100vh-4rem-4rem)]">
        {/* Left Notifications Panel */}
        <NotificationsPanel />

        {/* Content Panel */}
        <main className="flex-1 px-4 sm:px-6 lg:px-8 py-8 overflow-x-hidden">
          <div className="max-w-[1600px] mx-auto">
            {children}
          </div>
        </main>
      </div>

      {/* Footer */}
      <footer className="bg-white border-t mt-16">
        <div className="w-full px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-center text-sm text-gray-500">
            © 2025 InspectFlow. Streamline your inspection notifications &amp; procurement expediting.
          </p>
        </div>
      </footer>

      {/* Material Design CSS Variables */}
      <style>{`
        :root {
          --md-elevation-1: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
          --md-elevation-2: 0 3px 6px rgba(0,0,0,0.15), 0 2px 4px rgba(0,0,0,0.12);
          --md-elevation-3: 0 10px 20px rgba(0,0,0,0.15), 0 3px 6px rgba(0,0,0,0.10);
          --md-elevation-4: 0 15px 25px rgba(0,0,0,0.15), 0 5px 10px rgba(0,0,0,0.05);
        }
        
        .elevation-1 { box-shadow: var(--md-elevation-1); }
        .elevation-2 { box-shadow: var(--md-elevation-2); }
        .elevation-3 { box-shadow: var(--md-elevation-3); }
        .elevation-4 { box-shadow: var(--md-elevation-4); }
        
        .ripple {
          position: relative;
          overflow: hidden;
        }
        
        .ripple::after {
          content: '';
          position: absolute;
          top: 50%;
          left: 50%;
          width: 0;
          height: 0;
          border-radius: 50%;
          background: rgba(255,255,255,0.3);
          transform: translate(-50%, -50%);
          transition: width 0.6s, height 0.6s;
        }
        
        .ripple:active::after {
          width: 300px;
          height: 300px;
        }
      `}</style>
    </div>
  );
}

export default function Layout({ children }) {
  return (
    <ProjectProvider>
      <LayoutContent>{children}</LayoutContent>
    </ProjectProvider>
  );
}

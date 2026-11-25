import React, { useState, useEffect, useRef, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  RefreshCw,
  LayoutDashboard,
  FileSpreadsheet,
  Package,
  ShieldAlert,
  MapPin,
  Store,
  Scissors,
  Truck,
  ShieldCheck,
  Sparkles,
  Calendar,
} from "lucide-react";
import { toast } from "sonner";
import ExecutiveRiskRibbon from "@/components/expediting/ExecutiveRiskRibbon";
import SplitItemDialog from "@/components/expediting/SplitItemDialog";
import LogisticsStageDialog from "@/components/expediting/LogisticsStageDialog";
import TwoStageRailDialog from "@/components/expediting/TwoStageRailDialog";
import IrcBlockerDrawer from "@/components/expediting/IrcBlockerDrawer";
import ProjectPoAllocationDialog from "@/components/expediting/ProjectPoAllocationDialog";
import ExpeditingErpHubModal from "@/components/expediting/ExpeditingErpHubModal";
import { useProject } from "@/components/context/ProjectContext";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Users, FolderGit2 } from "lucide-react";

export default function Expediting() {
  const location = useLocation();
  const navigate = useNavigate();
  const { selectedProjectId, currentProject } = useProject();
  const iframeRef = useRef(null);
  const [iframeKey, setIframeKey] = useState(0);

  // Workflow Dialog States
  const [splitDialogOpen, setSplitDialogOpen] = useState(false);
  const [logisticsDialogOpen, setLogisticsDialogOpen] = useState(false);
  const [railDialogOpen, setRailDialogOpen] = useState(false);
  const [blockerDrawerOpen, setBlockerDrawerOpen] = useState(false);
  const [allocationDialogOpen, setAllocationDialogOpen] = useState(false);
  const [erpHubOpen, setErpHubOpen] = useState(false);
  const [erpHubTab, setErpHubTab] = useState("schedule9");
  const [projectPos, setProjectPos] = useState([]);

  const readStoredUser = () => {
    try {
      const raw =
        localStorage.getItem("inspectflow_mock_session") ||
        localStorage.getItem("csharp_auth_user") ||
        localStorage.getItem("inspectflow_user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  };

  const [authUser, setAuthUser] = useState(readStoredUser);
  const authRole = (authUser?.inspection_role || authUser?.role || "").toLowerCase();
  const isVendorUser = authRole === "vendor";
  const isPrivilegedManager = ["admin", "expediting_manager"].includes(authRole);

  // Parse current query parameters
  const searchParams = new URLSearchParams(location.search);
  const rawSec = searchParams.get("sec") || "dash";
  const sec = isVendorUser ? "portal" : rawSec;
  const tab = searchParams.get("tab") || "";
  const po = searchParams.get("po") || "";
  const [posLoadedFor, setPosLoadedFor] = useState(null);
  const lastNavFromIframeRef = useRef("");

  useEffect(() => {
    let active = true;
    const pidKey = selectedProjectId || "all";
    if (posLoadedFor && posLoadedFor !== pidKey) {
      setProjectPos([]);
    }
    const loadPos = async () => {
      try {
        const res = await fetch(
          `/api/v1/governance/overview?project_id=${encodeURIComponent(pidKey)}`
        );
        const json = await res.json();
        if (active && json.ok) {
          setProjectPos(json.pos || []);
          setPosLoadedFor(pidKey);
        }
      } catch (e) {
        console.error("Failed to fetch project POs:", e);
      }
    };
    loadPos();
    window.addEventListener("governance-updated", loadPos);
    return () => {
      active = false;
      window.removeEventListener("governance-updated", loadPos);
    };
  }, [selectedProjectId, iframeKey]);

  const activePoObj =
    projectPos.find((p) => p.po === po) || projectPos[0] || null;
  const activePo = activePoObj?.po || (posLoadedFor !== (selectedProjectId || "all") ? po : "");

  // Always mark active department as expediting when visiting this page
  useEffect(() => {
    localStorage.setItem("inspectflow_active_dept", "expediting");
    window.dispatchEvent(new CustomEvent("department-change", { detail: { department: "expediting" } }));
  }, []);

  // PostMessage bridge: when location.search or selectedProjectId changes or iframe loads, sync project + route + user
  const syncIframeState = (forceNav = false) => {
    const parsed = authUser || readStoredUser();
    const uRole = (parsed?.inspection_role || parsed?.role || "").toLowerCase();
    const isAdmin = uRole === "admin";
    const isVendor = uRole === "vendor";
    if (iframeRef.current && iframeRef.current.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        {
          type: "SX_SET_PROJECT",
          projectId: selectedProjectId || "all",
        },
        "*"
      );
      const navSig = `${isVendor ? "portal" : sec}|${tab}|${activePo}`;
      if (forceNav || lastNavFromIframeRef.current !== navSig) {
        iframeRef.current.contentWindow.postMessage(
          {
            type: "SX_NAVIGATE",
            sec: isVendor ? "portal" : sec,
            tab: tab || undefined,
            po: activePo || undefined,
          },
          "*"
        );
      }
      lastNavFromIframeRef.current = "";
      if (parsed) {
        const roleMap = {
          expediting_manager: "PEXM",
          expeditor: "EXP",
          field_expeditor: "FIELD",
          doc_expeditor: "DOC",
          vendor: `VEN:${activePo || "__NONE__"}`,
        };
        iframeRef.current.contentWindow.postMessage(
          {
            type: "SX_BIND_USER",
            sxRole: roleMap[uRole] || (isAdmin ? "PEXM" : "DOC"),
            isAdmin,
            isVendor,
            vendorPos: projectPos.map((p) => p.po),
            userEmail: parsed?.email,
            userName: parsed?.full_name,
          },
          window.location.origin
        );
      }
    }
  };

  useEffect(() => {
    setAuthUser(readStoredUser());
  }, []);

  useEffect(() => {
    syncIframeState(false);
  }, [sec, tab, po, activePo, selectedProjectId, authUser, projectPos]);

  // Listen for inner navigation events from SmartExpedit to synchronize URL without reloading iframe
  useEffect(() => {
    const handleMessage = (ev) => {
      if (ev.origin !== window.location.origin) return;
      if (ev.data && ev.data.type === "SX_NAV_SYNC") {
        const newSec = isVendorUser ? "portal" : (ev.data.sec || "dash");
        const newTab = ev.data.tab || "";
        const newPo = ev.data.po || "";

        const currentParams = new URLSearchParams(location.search);
        const currSec = currentParams.get("sec") || "dash";
        const currTab = currentParams.get("tab") || "";
        const currPo = currentParams.get("po") || "";

        if (newSec !== currSec || newTab !== currTab || (newPo && newPo !== currPo)) {
          lastNavFromIframeRef.current = `${newSec}|${newTab}|${newPo}`;
          const params = new URLSearchParams();
          params.set("sec", newSec);
          if (newTab) params.set("tab", newTab);
          if (newPo) params.set("po", newPo);
          navigate(`/Expediting?${params.toString()}`, { replace: true });
        }
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [location.search, navigate, isVendorUser]);

  const handleSyncInspectFlow = async () => {
    try {
      const res = await fetch("/api/v1/sync-inspectflow", { method: "POST" });
      const json = await res.json();
      toast.success(
        json.synced > 0
          ? `Synced ${json.synced} Inspection Notification(s) into SmartExpedit!`
          : "All InspectFlow notifications are up to date in SmartExpedit."
      );
      setIframeKey((k) => k + 1);
    } catch (e) {
      toast.error("Failed to sync notifications");
    }
  };

  const sectionMeta = {
    dash: {
      title: "Expediting Executive Dashboard",
      sub: "Portfolio health, critical sub-order floats, 14-day SLA document reviews, and schedule slip S-curves",
      icon: LayoutDashboard,
    },
    queue: {
      title: "PO Master Register & Expeditor Allocation",
      sub: "Purchase Order intake queue, unassigned order dispatching, and workload balance across expediting engineers",
      icon: FileSpreadsheet,
    },
    core: {
      title: "Package Expeditor Workbench",
      sub: "Live order tracking across Level-3 manufacturing schedules, VDRL SDRL review cycles, and stores delivery",
      icon: Package,
    },
    exec: {
      title: "Manufacturing Schedule & Progress Review",
      sub: "Review vendor schedule submissions, compare baseline vs forecast dates, and approve or return revisions",
      icon: Package,
    },
    rail: {
      title: "Rolling Action Item List (RAIL)",
      sub: "3-Tier escalation tracking (Tier 1: 1-7d, Tier 2: 8-14d PExM, Tier 3: >14d Critical) with two-stage verification",
      icon: ShieldAlert,
    },
    field: {
      title: "Field Expediting & Shop Visit Log",
      sub: "Shop surveillance findings, witness milestone audits, and vendor fabrication physical progress verification",
      icon: MapPin,
    },
    portal: {
      title: "Vendor Expediting Portal",
      sub: "Direct supplier portal for manufacturing schedule submission, procurement plan declaration, and NOI issuance",
      icon: Store,
    },
  };

  const currentMeta = sectionMeta[sec] || sectionMeta.dash;
  const SectionIcon = currentMeta.icon;

  // Stabilize iframeSrc so in-app tab/PO navigation uses postMessage without reloading the iframe document
  const iframeSrc = useMemo(() => {
    const p = new URLSearchParams();
    p.set("sec", isVendorUser ? "portal" : (sec || "dash"));
    if (tab) p.set("tab", tab);
    if (po) p.set("po", po);
    p.set("project_id", selectedProjectId || "all");
    return `/smartexpedit-app?${p.toString()}`;
  }, [selectedProjectId, iframeKey, isVendorUser]);

  return (
    <div className="space-y-4 pb-6">
      {/* Executive Risk Ribbon (Internal Staff Only — hidden from Vendors) */}
      {!isVendorUser && (
        <ExecutiveRiskRibbon
          onSelectPo={(selectedPo) => {
            navigate(`/Expediting?sec=core&tab=sched&po=${encodeURIComponent(selectedPo)}`);
          }}
        />
      )}

      {/* Active Project & Paired PO Team Governance Strip */}
      <div className="bg-indigo-950 text-white px-4 py-2.5 rounded-xl border border-indigo-800/80 shadow-xs flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <FolderGit2 className="w-4 h-4 text-indigo-300" />
            <span className="font-bold text-indigo-200">
              {currentProject
                ? `[${currentProject.code}] ${currentProject.name} (${projectPos.length} POs)`
                : `All Assigned Projects (${projectPos.length} Linked POs)`}
            </span>
          </div>
          {activePoObj ? (
            <>
              <span className="text-indigo-700">|</span>
              <span>
                <b className="text-indigo-300">Exp Mgr:</b>{" "}
                {(activePoObj.expediting_manager_name || currentProject?.expediting_manager_name || "Unassigned").split("(")[0].trim()}
              </span>
              <span>
                <b className="text-sky-300">Expeditor:</b>{" "}
                {(activePoObj.assigned_expeditor_name || "Unassigned").split("(")[0].trim()}
              </span>
              <span>
                <b className="text-emerald-300">QC Mgr:</b>{" "}
                {(activePoObj.inspection_manager_name || currentProject?.inspection_manager_name || "Unassigned").split("(")[0].trim()}
              </span>
              <span>
                <b className="text-teal-300">Paired IE:</b>{" "}
                {(activePoObj.assigned_inspection_engineer_name || "Unassigned").split("(")[0].trim()}
              </span>
            </>
          ) : (
            currentProject && (
              <>
                <span className="text-indigo-700">|</span>
                <span className="text-amber-300 font-medium">
                  No POs created in this project yet — use &ldquo;Project &amp; PO Team Allocation&rdquo; to add a project PO
                </span>
              </>
            )
          )}
        </div>

        <div className="flex items-center gap-2">
          <Select
            value={activePo}
            disabled={projectPos.length === 0}
            onValueChange={(newPo) => {
              const targetSec = ["core", "exec", "sub", "insp", "deliv", "portal"].includes(sec) ? sec : "core";
              navigate(`/Expediting?sec=${targetSec}&tab=${tab || "sched"}&po=${encodeURIComponent(newPo)}`);
            }}
          >
            <SelectTrigger className="w-60 h-7 text-xs bg-white text-gray-900 border-0 font-bold">
              <SelectValue placeholder={projectPos.length === 0 ? "No POs in project" : "Select Project PO"} />
            </SelectTrigger>
            <SelectContent>
              {projectPos.length === 0 ? (
                <SelectItem value="__none" disabled className="text-xs text-gray-400">
                  No POs linked to this project
                </SelectItem>
              ) : (
                projectPos.map((pItem) => (
                  <SelectItem key={pItem.po} value={pItem.po} className="text-xs">
                    PO #{pItem.po} — {pItem.supplier} ({pItem.bom_count} BOM)
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>

          {isPrivilegedManager && (
            <Button
              size="xs"
              onClick={() => setAllocationDialogOpen(true)}
              className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs h-7 px-2.5 font-semibold"
            >
              <Users className="w-3.5 h-3.5 mr-1" />
              Project &amp; PO Team Allocation
            </Button>
          )}
        </div>
      </div>

      {/* Sleek Expediting Action Bar with Workflow Triggers */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 bg-white p-3 rounded-xl border border-gray-200/80 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shadow-xs shrink-0">
            <SectionIcon className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-gray-900 leading-snug">
              {currentMeta.title}
            </h2>
            <p className="text-gray-500 text-[11px] line-clamp-1">
              {currentMeta.sub}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 shrink-0">
          {!isVendorUser ? (
            <>
              <Button
                variant="outline"
                size="xs"
                disabled={!activePo}
                onClick={() => setSplitDialogOpen(true)}
                className="text-indigo-700 border-indigo-200 hover:bg-indigo-50 font-semibold text-xs h-7 px-2.5 shadow-xs"
                title="Split package line items into multi-location sub-assemblies"
              >
                <Scissors className="w-3.5 h-3.5 mr-1 text-indigo-600" />
                Split Package Item
              </Button>

              <Button
                variant="outline"
                size="xs"
                disabled={!activePo}
                onClick={() => setLogisticsDialogOpen(true)}
                className="text-emerald-700 border-emerald-200 hover:bg-emerald-50 font-semibold text-xs h-7 px-2.5 shadow-xs"
                title="Update 4-Stage Logistics & Site Delivery MRV"
              >
                <Truck className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                Update Logistics Stage
              </Button>

              <Button
                variant="outline"
                size="xs"
                disabled={!activePo}
                onClick={() => setRailDialogOpen(true)}
                className="text-purple-700 border-purple-200 hover:bg-purple-50 font-semibold text-xs h-7 px-2.5 shadow-xs"
                title="Two-stage verification for RAIL quality closeouts"
              >
                <ShieldCheck className="w-3.5 h-3.5 mr-1 text-purple-600" />
                Two-Stage RAIL Closeout
              </Button>

              <Button
                variant="outline"
                size="xs"
                onClick={() => setBlockerDrawerOpen(true)}
                className="text-rose-700 border-rose-200 hover:bg-rose-50 font-semibold text-xs h-7 px-2.5 shadow-xs"
                title="View Real-Time Diagnostic Reasons Why IRC Is Blocked"
              >
                <ShieldAlert className="w-3.5 h-3.5 mr-1 text-rose-600" />
                IRC Blocker Diagnostics
              </Button>

              <Button
                variant="outline"
                size="xs"
                onClick={() => {
                  setErpHubTab("schedule9");
                  setErpHubOpen(true);
                }}
                className="text-sky-700 border-sky-200 hover:bg-sky-50 font-semibold text-xs h-7 px-2.5 shadow-xs"
                title="Open 9-Column Minimum Schedule, Progress Reports & Consolidated Weekly MSSR"
              >
                <Calendar className="w-3.5 h-3.5 mr-1 text-sky-600" />
                9-Col Schedule &amp; MSSR
              </Button>

              <Button
                variant="outline"
                size="xs"
                disabled={!activePo}
                onClick={() => {
                  setErpHubTab("ai_agents");
                  setErpHubOpen(true);
                }}
                className="text-violet-700 border-violet-200 hover:bg-violet-50 font-semibold text-xs h-7 px-2.5 shadow-xs"
                title="AI Agents: PO/MR Review (Action #2) & First Expediting Contact (Action #3)"
              >
                <Sparkles className="w-3.5 h-3.5 mr-1 text-violet-600" />
                AI Agents
              </Button>

              <Button
                variant="outline"
                size="xs"
                onClick={() => {
                  setErpHubTab("phase4_ops");
                  setErpHubOpen(true);
                }}
                className="text-teal-700 border-teal-200 hover:bg-teal-50 font-semibold text-xs h-7 px-2.5 shadow-xs"
                title="Client IAP Gate, MOM/PIM, Inspection Look-Ahead, Stores MNCR, LD Closeout & Governance Registers"
              >
                <ShieldCheck className="w-3.5 h-3.5 mr-1 text-teal-600" />
                IAP, Look-Ahead &amp; Closeout
              </Button>

              <Button
                variant="outline"
                size="xs"
                onClick={() => navigate("/VendorPortal")}
                className="text-amber-800 border-amber-200 hover:bg-amber-50 font-semibold text-xs h-7 px-2.5 shadow-xs"
                title="Access the Dedicated Vendor Portal"
              >
                <Store className="w-3.5 h-3.5 mr-1 text-amber-600" />
                Vendor Portal
              </Button>

              <div className="h-4 w-px bg-gray-200 mx-1 hidden sm:block" />

              <Button
                variant="ghost"
                size="xs"
                onClick={handleSyncInspectFlow}
                className="text-gray-700 hover:bg-gray-100 text-xs h-7 px-2"
              >
                <RefreshCw className="w-3 h-3 mr-1 text-indigo-600" />
                Sync IMS
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              size="xs"
              onClick={() => navigate("/VendorPortal")}
              className="text-indigo-700 border-indigo-200 hover:bg-indigo-50 font-semibold text-xs h-7 px-2.5 shadow-xs"
            >
              <Store className="w-3.5 h-3.5 mr-1 text-indigo-600" />
              Open NOI, VDMS &amp; NCR Dispatch View
            </Button>
          )}
          <Button
            variant="ghost"
            size="xs"
            onClick={() => setIframeKey((k) => k + 1)}
            className="text-gray-600 text-xs h-7 px-2"
          >
            <RefreshCw className="w-3 h-3 mr-1" />
            Reload
          </Button>
        </div>
      </div>

      {/* Embedded SmartExpedit Application Suite */}
      <div className="bg-white rounded-2xl elevation-2 overflow-hidden border border-gray-200">
        <iframe
          ref={iframeRef}
          key={iframeKey}
          src={iframeSrc}
          onLoad={() => syncIframeState(true)}
          title="SmartExpedit — Procurement Expediting & Material Tracking"
          className="w-full border-0"
          style={{ height: "calc(100vh - 12rem)", minHeight: "850px" }}
        />
      </div>

      {/* Workflow Modals */}
      <SplitItemDialog
        open={splitDialogOpen}
        onOpenChange={setSplitDialogOpen}
        currentPo={activePo}
        onSplitsSaved={() => setIframeKey((k) => k + 1)}
      />

      <LogisticsStageDialog
        open={logisticsDialogOpen}
        onOpenChange={setLogisticsDialogOpen}
        currentPo={activePo}
        onSuccess={() => setIframeKey((k) => k + 1)}
      />

      <TwoStageRailDialog
        open={railDialogOpen}
        onOpenChange={setRailDialogOpen}
        po={activePo}
        userRole="expeditor"
        onSuccess={() => setIframeKey((k) => k + 1)}
      />

      <IrcBlockerDrawer
        open={blockerDrawerOpen}
        onOpenChange={setBlockerDrawerOpen}
        onSelectPo={(selectedPo) => {
          navigate(`/Expediting?sec=core&tab=sched&po=${encodeURIComponent(selectedPo)}`);
        }}
      />

      <ProjectPoAllocationDialog
        open={allocationDialogOpen}
        onOpenChange={setAllocationDialogOpen}
        defaultTab="paired-po"
        initialProjectId={selectedProjectId}
        onSuccess={(createdPo) => {
          setIframeKey((k) => k + 1);
          if (createdPo) {
            navigate(`/Expediting?sec=core&tab=sched&po=${encodeURIComponent(createdPo)}`);
          }
        }}
      />

      <ExpeditingErpHubModal
        open={erpHubOpen}
        onOpenChange={setErpHubOpen}
        defaultTab={erpHubTab}
        activePo={activePo}
        projectId={selectedProjectId}
        onUpdated={() => setIframeKey((k) => k + 1)}
      />
    </div>
  );
}

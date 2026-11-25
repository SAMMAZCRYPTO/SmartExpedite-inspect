import React, { useState, useEffect, useMemo } from "react";
import { base44 } from "@/api/base44Client";
import { useQuery } from "@tanstack/react-query";
import { useProject } from "@/components/context/ProjectContext";
import { useNavigate } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  ChevronLeft,
  ChevronRight,
  Search,
  Bell,
  FileText,
  Info,
  CheckCircle2,
  AlertCircle
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";

export default function NotificationsPanel() {
  const navigate = useNavigate();
  const { selectedProjectId } = useProject();
  const [isExpanded, setIsExpanded] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentUser, setCurrentUser] = useState(null);

  // Fetch current user
  useEffect(() => {
    const fetchUser = async () => {
      try {
        const u = await base44.auth.getUser();
        setCurrentUser(u);
      } catch (e) {
        console.error("Failed to fetch user in NotificationsPanel:", e);
      }
    };
    fetchUser();
  }, []);

  // Fetch notifications (inspections)
  const { data: inspections = [] } = useQuery({
    queryKey: ["inspections"],
    queryFn: () => base44.entities.Inspection.list("-created_at"),
    refetchInterval: 12000, // Keep fresh
  });

  // Filter by project
  const projectFiltered = useMemo(() => {
    if (!selectedProjectId || selectedProjectId === "all") return inspections;
    return inspections.filter(
      (i) => String(i.project_id || "").toLowerCase() === String(selectedProjectId).toLowerCase()
    );
  }, [inspections, selectedProjectId]);

  // Filter by user role permissions
  const roleFiltered = useMemo(() => {
    if (!currentUser) return [];

    const effRole = (currentUser.inspection_role || currentUser.role || "").toLowerCase();
    const userEmail = (currentUser.email || "").toLowerCase();
    const userProjIds = (currentUser.project_ids || []).map((p) => String(p).toLowerCase());
    const isAdmin = effRole === "admin" || currentUser.role === "admin";

    if (isAdmin || effRole === "qc_manager") {
      return projectFiltered;
    } else if (effRole === "inspection_engineer") {
      return projectFiltered.filter(
        (i) =>
          (i.created_by || "").toLowerCase() === userEmail ||
          (i.assigned_inspection_engineer_email || "").toLowerCase() === userEmail ||
          (i.project_id && userProjIds.includes(String(i.project_id).toLowerCase()))
      );
    } else if (["expediting_manager", "expeditor", "field_expeditor", "doc_expeditor"].includes(effRole)) {
      return projectFiltered.filter(
        (i) =>
          !i.project_id ||
          userProjIds.includes(String(i.project_id).toLowerCase()) ||
          (i.assigned_expeditor_email || "").toLowerCase() === userEmail
      );
    } else if (effRole === "inspection_agency") {
      const agencyName = currentUser.company || currentUser.company_affiliation;
      if (!agencyName) return [];
      return projectFiltered.filter((i) => i.tpi_agency === agencyName);
    } else if (effRole === "inspector") {
      return projectFiltered.filter((i) => (i.assigned_inspector_email || "").toLowerCase() === userEmail);
    } else if (effRole === "vendor") {
      const co = (currentUser.company || currentUser.company_affiliation || "").toLowerCase();
      return projectFiltered.filter(
        (i) => (i.supplier_name || "").toLowerCase().includes(co) && co
      );
    }
    return [];
  }, [projectFiltered, currentUser]);

  // Filter by search query
  const searchedNotifications = useMemo(() => {
    if (!searchQuery.trim()) return roleFiltered;
    const query = searchQuery.toLowerCase();
    return roleFiltered.filter(i =>
      (i.po_number && i.po_number.toLowerCase().includes(query)) ||
      (i.notification_number && i.notification_number.toLowerCase().includes(query)) ||
      (i.supplier_name && i.supplier_name.toLowerCase().includes(query))
    );
  }, [roleFiltered, searchQuery]);

  // Count active notifications (status is not finalized)
  const activeCount = useMemo(() => {
    return roleFiltered.filter(i => i.status !== "finalized").length;
  }, [roleFiltered]);

  const handleItemClick = (inspection) => {
    // Check if this notification is expediting related (e.g. schedule update or document review)
    const isSchedule =
      inspection.type === 'schedule_update' ||
      inspection.inspection_type === 'schedule' ||
      inspection.target_tab === 'sched' ||
      (inspection.scope_of_inspection && inspection.scope_of_inspection.toLowerCase().includes('schedule'));

    if (isSchedule && inspection.po_number) {
      navigate(`/Expediting?sec=core&tab=sched&po=${encodeURIComponent(inspection.po_number)}`);
      return;
    }

    // Save to sessionStorage so the dashboard can open it on mount if we redirect
    sessionStorage.setItem('activeInspectionId', inspection.id);

    // Dispatch event immediately in case we are already on the dashboard
    window.dispatchEvent(new CustomEvent('select-inspection', { detail: { id: inspection.id } }));

    // Navigate to inspection dashboard
    navigate("/Inspection");
  };

  const getStatusBadge = (status) => {
    const styles = {
      received: "bg-blue-50 text-blue-700 border-blue-200",
      scheduled: "bg-yellow-50 text-yellow-700 border-yellow-200",
      inprogress: "bg-indigo-50 text-indigo-700 border-indigo-200",
      completed: "bg-green-50 text-green-700 border-green-200",
      finalized: "bg-purple-50 text-purple-700 border-purple-200",
    };

    const label = {
      received: "Received",
      scheduled: "Scheduled",
      inprogress: "In Progress",
      completed: "Completed",
      finalized: "Finalized",
    };

    const s = String(status).toLowerCase();
    return (
      <Badge variant="outline" className={`${styles[s] || "bg-gray-50 text-gray-700 border-gray-200"} text-[10px] font-medium px-1.5 py-0`}>
        {label[s] || status}
      </Badge>
    );
  };

  // Render Collapsed State Ribbon
  if (!isExpanded) {
    return (
      <div
        onClick={() => setIsExpanded(true)}
        className="hidden md:flex flex-col items-center py-6 w-14 bg-white border-r border-gray-200 hover:bg-gray-50/80 cursor-pointer transition-all duration-300 shadow-sm relative shrink-0"
        title="Expand Notifications Panel"
      >
        <div className="relative p-2 bg-indigo-50 rounded-full text-indigo-600 mb-6 hover:scale-105 transition-transform">
          <Bell className="w-5 h-5" />
          {activeCount > 0 && (
            <span className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full text-[9px] w-5 h-5 flex items-center justify-center font-bold border-2 border-white animate-bounce">
              {activeCount}
            </span>
          )}
        </div>

        <div className="flex flex-col items-center gap-1.5 [writing-mode:vertical-lr] text-gray-500 hover:text-indigo-600 select-none">
          <span className="font-semibold tracking-wider text-xs uppercase">Notifications</span>
          <ChevronRight className="w-4 h-4 mt-1" />
        </div>
      </div>
    );
  }

  // Render Expanded Panel
  return (
    <div className="hidden md:flex flex-col w-80 bg-white border-r border-gray-200 shrink-0 h-[calc(100vh-4rem)] transition-all duration-300 shadow-lg z-20 flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 flex items-center justify-between bg-gray-50/50">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-indigo-600" />
          <h3 className="font-semibold text-gray-900 text-sm">Notifications</h3>
          {activeCount > 0 && (
            <Badge className="bg-red-500 text-white border-0 text-[10px] px-1.5 h-4 flex items-center justify-center font-bold">
              {activeCount}
            </Badge>
          )}
        </div>
        <button
          onClick={() => setIsExpanded(false)}
          className="p-1 rounded hover:bg-gray-200 text-gray-500 hover:text-gray-700 transition-colors"
          title="Collapse Panel"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      {/* Search Filter */}
      <div className="p-3 border-b border-gray-100 relative">
        <Search className="w-4 h-4 text-gray-400 absolute left-6 top-[18px]" />
        <Input
          placeholder="Search by PO, supplier..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-8 h-8 text-xs bg-gray-50 border-gray-200 focus:bg-white"
        />
      </div>

      {/* Scrollable Notifications List */}
      <ScrollArea className="flex-1 bg-gray-50/20">
        <div className="p-3 space-y-2">
          {searchedNotifications.length === 0 ? (
            <div className="text-center py-8 px-4 text-gray-400">
              <Info className="w-6 h-6 mx-auto mb-2 text-gray-300" />
              <p className="text-xs">No notifications found.</p>
            </div>
          ) : (
            searchedNotifications.map((noti) => (
              <Card
                key={noti.id}
                onClick={() => handleItemClick(noti)}
                className="p-3 cursor-pointer hover:shadow-md hover:border-indigo-300 transition-all border border-gray-150 duration-200 bg-white relative overflow-hidden group"
              >
                {/* Visual hover border bar */}
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity" />

                <div className="flex justify-between items-start gap-2 mb-1.5">
                  <span className="font-semibold text-xs text-gray-800 break-all">
                    PO: {noti.po_number || "No PO"}
                  </span>
                  {getStatusBadge(noti.status)}
                </div>

                <div className="flex items-center gap-1.5 text-[10px] text-gray-500 mb-2 font-medium">
                  <FileText className="w-3 h-3 text-indigo-400" />
                  <span className="truncate">{noti.notification_number || "No Reference"}</span>
                </div>

                <div className="text-[10px] text-gray-600 truncate border-t border-gray-100 pt-1.5 flex justify-between items-center">
                  <span className="font-medium truncate max-w-[70%]">{noti.supplier_name || "Unknown Supplier"}</span>
                  <span className="text-[9px] text-gray-400 shrink-0">
                    {noti.start_date ? noti.start_date.split('T')[0] : "No date"}
                  </span>
                </div>
              </Card>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

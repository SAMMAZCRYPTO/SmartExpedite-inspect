import React, { useState } from "react";
import { base44 } from "@/api/base44Client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Users,
  Search,
  Shield,
  Edit,
  Mail,
  UserX,
  FolderGit2,
  Plus,
  Trash2,
  UserCog,
  Building2,
  Package,
  ShieldCheck,
  CheckCircle2,
} from "lucide-react";
import { motion } from "framer-motion";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import ProjectPoAllocationDialog from "@/components/expediting/ProjectPoAllocationDialog";

const roleColors = {
  admin: "bg-red-100 text-red-800 border-red-200",
  expediting_manager: "bg-indigo-100 text-indigo-800 border-indigo-200",
  qc_manager: "bg-green-100 text-green-800 border-green-200",
  expeditor: "bg-sky-100 text-sky-800 border-sky-200",
  field_expeditor: "bg-teal-100 text-teal-800 border-teal-200",
  doc_expeditor: "bg-cyan-100 text-cyan-800 border-cyan-200",
  inspection_engineer: "bg-blue-100 text-blue-800 border-blue-200",
  inspector: "bg-purple-100 text-purple-800 border-purple-200",
  inspection_agency: "bg-amber-100 text-amber-800 border-amber-200",
  vendor: "bg-orange-100 text-orange-800 border-orange-200",
};

const roleLabels = {
  admin: "Global Admin",
  expediting_manager: "Expediting Manager",
  qc_manager: "QC / Inspection Manager",
  expeditor: "Package Expeditor",
  field_expeditor: "Field Expeditor",
  doc_expeditor: "Document Controller (VDRL)",
  inspection_engineer: "Inspection Engineer",
  inspector: "Field / TPI Inspector",
  inspection_agency: "TPI Agency Coordinator",
  vendor: "Vendor Portal User",
};

export default function UserManagement() {
  const [activeTab, setActiveTab] = useState("projects");
  const [searchQuery, setSearchQuery] = useState("");
  const [editingUser, setEditingUser] = useState(null);
  const [deactivatingUser, setDeactivatingUser] = useState(null);
  const [editingProject, setEditingProject] = useState(null);
  const [deletingProject, setDeletingProject] = useState(null);
  const [isAddingProject, setIsAddingProject] = useState(false);

  // Governance & Paired PO Allocation Modal
  const [allocationModalOpen, setAllocationModalOpen] = useState(false);
  const [allocationDefaultTab, setAllocationDefaultTab] = useState("paired-po");
  const [allocationProjId, setAllocationProjId] = useState(null);

  // Add New Vendor Modal
  const [addVendorOpen, setAddVendorOpen] = useState(false);
  const [savingVendor, setSavingVendor] = useState(false);
  const [vendorForm, setVendorForm] = useState({
    company_affiliation: "",
    full_name: "",
    email: "",
    phone: "",
    password: "",
    project_ids: [],
  });

  const [editFormData, setEditFormData] = useState({
    inspection_role: "",
    company_affiliation: "",
    phone: "",
    department: "",
    project_ids: [],
  });

  const [projectFormData, setProjectFormData] = useState({
    name: "",
    code: "",
    client_name: "",
    description: "",
    status: "active",
    expediting_manager_id: "",
    inspection_manager_id: "",
  });

  const queryClient = useQueryClient();

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => base44.entities.User.list("-created_at"),
    initialData: [],
  });

  const { data: agencies = [] } = useQuery({
    queryKey: ["tpiagencies"],
    queryFn: () => base44.entities.TPIAgency.list(),
    initialData: [],
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => base44.entities.Project.list(),
    initialData: [],
  });

  const { data: inspectors = [] } = useQuery({
    queryKey: ["inspectors"],
    queryFn: () => base44.entities.Inspector.list(),
    initialData: [],
  });

  const { data: govOverview, refetch: refetchGovernance } = useQuery({
    queryKey: ["governance-overview"],
    queryFn: async () => {
      const res = await fetch("/api/v1/governance/overview");
      return res.json();
    },
  });

  const updateUserMutation = useMutation({
    mutationFn: ({ id, data }) => base44.entities.User.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["governance-overview"] });
      window.dispatchEvent(new CustomEvent("governance-updated"));
      setEditingUser(null);
      toast.success("User role & project assignments updated");
    },
  });

  const deactivateUserMutation = useMutation({
    mutationFn: ({ id }) =>
      base44.entities.User.update(id, {
        role: "guest",
        inspection_role: null,
        user_status: "deactivated",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setDeactivatingUser(null);
      toast.success("User deactivated successfully");
    },
  });

  const handleEdit = (user) => {
    setEditingUser(user);
    setEditFormData({
      inspection_role: user.inspection_role || user.role || "",
      company_affiliation: user.company_affiliation || "",
      phone: user.phone || "",
      department: user.department || "",
      project_ids: user.project_ids || [],
    });
  };

  const handleSave = () => {
    updateUserMutation.mutate({
      id: editingUser.id,
      data: editFormData,
    });
  };

  const filteredUsers = users.filter((user) => {
    const query = searchQuery.toLowerCase();
    return (
      user.full_name?.toLowerCase().includes(query) ||
      user.email?.toLowerCase().includes(query) ||
      user.inspection_role?.toLowerCase().includes(query) ||
      user.company_affiliation?.toLowerCase().includes(query)
    );
  });

  const roleStats = {
    total: users.length,
    admin: users.filter((u) => u.inspection_role === "admin" || u.role === "admin").length,
    managers: users.filter((u) =>
      ["expediting_manager", "qc_manager"].includes(u.inspection_role || u.role)
    ).length,
    expeditors: users.filter((u) =>
      ["expeditor", "field_expeditor", "doc_expeditor"].includes(u.inspection_role || u.role)
    ).length,
    inspection_engineer: users.filter((u) => u.inspection_role === "inspection_engineer").length,
    inspector: users.filter((u) => u.inspection_role === "inspector").length,
    vendor: users.filter((u) => (u.inspection_role || u.role) === "vendor").length,
    unassigned: users.filter((u) => !u.inspection_role && u.role !== "admin").length,
  };

  const saveProjectGovernance = async (payload) => {
    const res = await fetch("/api/v1/governance/project-assign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const json = await res.json();
    if (!json.ok) throw new Error(json.detail || "Failed to save project");
    queryClient.invalidateQueries({ queryKey: ["projects"] });
    queryClient.invalidateQueries({ queryKey: ["users"] });
    queryClient.invalidateQueries({ queryKey: ["governance-overview"] });
    window.dispatchEvent(new CustomEvent("governance-updated"));
    return json;
  };

  const deleteProjectMutation = useMutation({
    mutationFn: (id) => base44.entities.Project.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["governance-overview"] });
      window.dispatchEvent(new CustomEvent("governance-updated"));
      setDeletingProject(null);
      toast.success("Project deleted successfully");
    },
    onError: () => {
      toast.error("Failed to delete project");
    },
  });

  const expManagers = users.filter((u) =>
    ["expediting_manager", "admin"].includes(u.inspection_role || u.role)
  );
  const inspManagers = users.filter((u) =>
    ["qc_manager", "admin"].includes(u.inspection_role || u.role)
  );
  const enrichedProjects = govOverview?.projects || projects;

  return (
    <div className="space-y-6 pb-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 mb-1">
            Global Admin — Project &amp; Departmental Governance
          </h1>
          <p className="text-sm text-gray-600">
            Assign Projects to Expediting Managers &amp; Inspection/QC Managers, pair Expeditors &amp; Inspection Engineers per PO, and manage user access.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            onClick={() => {
              setAllocationDefaultTab("paired-po");
              setAllocationProjId(null);
              setAllocationModalOpen(true);
            }}
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs h-9 font-semibold"
          >
            <ShieldCheck className="w-4 h-4 mr-1.5" />
            Project &amp; PO Team Allocation Hub
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setAllocationDefaultTab("new-po-bom");
              setAllocationProjId(null);
              setAllocationModalOpen(true);
            }}
            className="border-emerald-300 text-emerald-700 hover:bg-emerald-50 text-xs h-9 font-semibold"
          >
            <Package className="w-4 h-4 mr-1.5" />
            + Onboard New PO &amp; BOM
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card className="p-3.5 elevation-1">
          <p className="text-xs text-gray-500 mb-1">Active Projects</p>
          <p className="text-2xl font-bold text-indigo-700">{enrichedProjects.length}</p>
        </Card>
        <Card className="p-3.5 elevation-1">
          <p className="text-xs text-gray-500 mb-1">Dept Managers (Exp/QC)</p>
          <p className="text-2xl font-bold text-emerald-600">{roleStats.managers}</p>
        </Card>
        <Card className="p-3.5 elevation-1">
          <p className="text-xs text-gray-500 mb-1">Expeditors (Pkg/Field)</p>
          <p className="text-2xl font-bold text-sky-600">{roleStats.expeditors}</p>
        </Card>
        <Card className="p-3.5 elevation-1">
          <p className="text-xs text-gray-500 mb-1">Inspection Engineers</p>
          <p className="text-2xl font-bold text-blue-600">{roleStats.inspection_engineer}</p>
        </Card>
        <Card className="p-3.5 elevation-1">
          <p className="text-xs text-gray-500 mb-1">TPI Inspectors</p>
          <p className="text-2xl font-bold text-purple-600">{roleStats.inspector}</p>
        </Card>
        <Card className="p-3.5 elevation-1">
          <p className="text-xs text-gray-500 mb-1">Total Users</p>
          <p className="text-2xl font-bold text-gray-900">{roleStats.total}</p>
        </Card>
      </div>

      {/* Tabs for Projects, Users, and Inspectors */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full max-w-2xl grid-cols-3">
          <TabsTrigger value="projects">
            <FolderGit2 className="w-4 h-4 mr-2" />
            Projects &amp; PO Assignments ({enrichedProjects.length})
          </TabsTrigger>
          <TabsTrigger value="users">
            <Users className="w-4 h-4 mr-2" />
            Users &amp; Roles ({users.length})
          </TabsTrigger>
          <TabsTrigger value="inspectors">
            <UserCog className="w-4 h-4 mr-2" />
            Inspectors ({inspectors.length})
          </TabsTrigger>
        </TabsList>

        {/* ── TAB 1: PROJECTS & INTERLINKED MANAGERS / POs ── */}
        <TabsContent value="projects" className="mt-6 space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 bg-indigo-50/70 border border-indigo-200 rounded-xl p-4">
            <div className="text-xs text-indigo-950 space-y-0.5">
              <p className="font-bold text-sm">
                2-Tier Cascading Governance: Global Admin &rarr; Expediting Manager &amp; QC Manager &rarr; Paired PO Teams
              </p>
              <p className="text-indigo-700">
                Every Project has an assigned Expediting Manager and Inspection/QC Manager. All Purchase Orders and BOMs under the project are interlinked across both modules.
              </p>
            </div>
            <Button
              onClick={() => {
                setProjectFormData({
                  name: "",
                  code: `PRJ-${Math.floor(1000 + Math.random() * 9000)}`,
                  client_name: "ADNOC / QatarEnergy",
                  description: "",
                  status: "active",
                  expediting_manager_id: expManagers[0]?.id || "",
                  inspection_manager_id: inspManagers[0]?.id || "",
                });
                setIsAddingProject(true);
              }}
              className="bg-indigo-600 hover:bg-indigo-700 text-xs h-9"
            >
              <Plus className="w-4 h-4 mr-1.5" />
              Create &amp; Assign New Project
            </Button>
          </div>

          <div className="space-y-4">
            {enrichedProjects.map((project, idx) => {
              const linkedPos = project.linked_pos || [];
              return (
                <motion.div
                  key={project.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.04 }}
                >
                  <Card className="p-5 elevation-2 border-gray-200 space-y-4">
                    <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4 pb-3 border-b border-gray-100">
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-2.5 flex-wrap">
                          <span className="font-mono font-bold text-xs bg-indigo-100 text-indigo-800 px-2.5 py-1 rounded-md border border-indigo-200">
                            {project.code}
                          </span>
                          <h3 className="text-lg font-bold text-gray-900">
                            {project.name}
                          </h3>
                          <Badge
                            className={`border font-medium ${
                              project.status === "active"
                                ? "bg-green-100 text-green-800 border-green-200"
                                : "bg-gray-100 text-gray-600 border-gray-300"
                            }`}
                          >
                            {project.status === "active" ? "Active" : project.status}
                          </Badge>
                          {project.client_name && (
                            <span className="text-xs text-gray-500">
                              • Client: <b>{project.client_name}</b>
                            </span>
                          )}
                        </div>
                        {project.description && (
                          <p className="text-xs text-gray-600">
                            {project.description}
                          </p>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2 shrink-0">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setAllocationDefaultTab("paired-po");
                            setAllocationProjId(project.id);
                            setAllocationModalOpen(true);
                          }}
                          className="text-xs h-8 border-indigo-200 text-indigo-700 hover:bg-indigo-50"
                        >
                          <Users className="w-3.5 h-3.5 mr-1.5" />
                          Allocate PO Teams ({linkedPos.length})
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setEditingProject({
                              ...project,
                              expediting_manager_id: project.expediting_manager_id || expManagers[0]?.id || "",
                              inspection_manager_id: project.inspection_manager_id || inspManagers[0]?.id || "",
                            });
                          }}
                          className="text-xs h-8"
                        >
                          <Edit className="w-3.5 h-3.5 mr-1.5" />
                          Edit Project &amp; Managers
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDeletingProject(project)}
                          className="text-xs h-8 text-red-600 hover:text-red-700 border-red-200 hover:bg-red-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </div>

                    {/* Tier 1 Assigned Managers Banner */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div className="p-3 rounded-xl bg-indigo-50/60 border border-indigo-200/80 flex items-center justify-between">
                        <div>
                          <span className="text-[10px] uppercase tracking-wider font-bold text-indigo-600 block">
                            Tier-1 Assigned Expediting Manager
                          </span>
                          <span className="text-xs font-bold text-gray-900">
                            {project.expediting_manager_name || "Tariq Al-Mansoor (Expediting Manager)"}
                          </span>
                          <span className="text-[11px] text-gray-500 block">
                            {project.expediting_manager_email || "pexm@inspectflow.com"}
                          </span>
                        </div>
                        <Badge className="bg-indigo-100 text-indigo-800 border-indigo-200 text-[10px]">
                          Full Project PO Access
                        </Badge>
                      </div>

                      <div className="p-3 rounded-xl bg-emerald-50/60 border border-emerald-200/80 flex items-center justify-between">
                        <div>
                          <span className="text-[10px] uppercase tracking-wider font-bold text-emerald-700 block">
                            Tier-1 Assigned Inspection / QC Manager
                          </span>
                          <span className="text-xs font-bold text-gray-900">
                            {project.inspection_manager_name || "Dr. Henrik Lindqvist (QC / Inspection Manager)"}
                          </span>
                          <span className="text-[11px] text-gray-500 block">
                            {project.inspection_manager_email || "qc@inspectflow.com"}
                          </span>
                        </div>
                        <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200 text-[10px]">
                          Full Quality &amp; IRC Oversight
                        </Badge>
                      </div>
                    </div>

                    {/* Tier 2 Interlinked POs & Paired Expeditor <-> Inspection Engineer Table */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-gray-800">
                          Interlinked Purchase Orders &amp; Hand-in-Hand Team Assignments ({linkedPos.length} POs)
                        </span>
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() => {
                            setAllocationDefaultTab("new-po-bom");
                            setAllocationProjId(project.id);
                            setAllocationModalOpen(true);
                          }}
                          className="text-xs text-emerald-700 hover:bg-emerald-50 h-6 px-2 font-semibold"
                        >
                          <Plus className="w-3 h-3 mr-1" /> Add PO &amp; BOM to {project.code}
                        </Button>
                      </div>

                      {linkedPos.length === 0 ? (
                        <div className="p-3 rounded-lg bg-gray-50 border border-gray-200 text-xs text-gray-500">
                          No Purchase Orders linked to this project yet. Click "+ Add PO &amp; BOM" above.
                        </div>
                      ) : (
                        <div className="overflow-x-auto rounded-lg border border-gray-200">
                          <table className="w-full text-xs text-left">
                            <thead className="bg-gray-50 text-gray-600 font-semibold border-b border-gray-200">
                              <tr>
                                <th className="py-2 px-3">PO Number</th>
                                <th className="py-2 px-3">Supplier / Vendor</th>
                                <th className="py-2 px-3">Package Description</th>
                                <th className="py-2 px-3">BOM Lines</th>
                                <th className="py-2 px-3">Assigned Package Expeditor</th>
                                <th className="py-2 px-3">Paired Inspection Engineer</th>
                                <th className="py-2 px-3">Linked NOIs</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {linkedPos.map((po) => (
                                <tr key={po.po} className="hover:bg-gray-50/70">
                                  <td className="py-2 px-3 font-mono font-bold text-indigo-700">
                                    {po.po}
                                  </td>
                                  <td className="py-2 px-3 font-medium text-gray-900">
                                    {po.supplier}
                                  </td>
                                  <td className="py-2 px-3 text-gray-600 max-w-xs truncate">
                                    {po.head}
                                  </td>
                                  <td className="py-2 px-3">
                                    <Badge variant="outline" className="text-[10px]">
                                      {po.bom_count} items ({po.total_ordered_qty} qty)
                                    </Badge>
                                  </td>
                                  <td className="py-2 px-3 font-semibold text-indigo-800">
                                    {po.assigned_expeditor_name || "Ali Al-Rashid"}
                                  </td>
                                  <td className="py-2 px-3 font-semibold text-emerald-800">
                                    {po.assigned_inspection_engineer_name || "Omar Farooq"}
                                  </td>
                                  <td className="py-2 px-3">
                                    <Badge className="bg-blue-50 text-blue-700 border-blue-200 text-[10px]">
                                      {po.inspection_count} NOI(s)
                                    </Badge>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </TabsContent>

        {/* ── TAB 2: USERS & ROLES ── */}
        <TabsContent value="users" className="mt-6 space-y-6">
          <div className="bg-white rounded-2xl p-5 elevation-2">
            <div className="relative">
              <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <Input
                placeholder="Search by name, email, role, or company..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-12 h-11 text-sm border-2 focus:border-indigo-600 rounded-xl"
              />
            </div>
          </div>

          <Card className="elevation-2">
            <div className="p-5 border-b flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-indigo-100 rounded-xl flex items-center justify-center">
                  <Users className="w-5 h-5 text-indigo-600" />
                </div>
                <h2 className="text-xl font-bold text-gray-900">All Enterprise Users</h2>
              </div>
              <Button
                size="sm"
                onClick={() => {
                  setVendorForm({
                    company_affiliation: "",
                    full_name: "",
                    email: "",
                    phone: "",
                    password: "",
                    project_ids: [],
                  });
                  setAddVendorOpen(true);
                }}
                className="bg-amber-600 hover:bg-amber-700 text-white text-xs h-8"
              >
                <Plus className="w-3.5 h-3.5 mr-1.5" />
                Add Vendor Portal Account
              </Button>
            </div>

            {isLoading ? (
              <div className="text-center py-12">Loading users...</div>
            ) : (
              <div className="divide-y max-h-[650px] overflow-y-auto">
                {filteredUsers.map((user) => {
                  const rKey = user.inspection_role || user.role;
                  const userProjs = projects.filter((p) =>
                    (user.project_ids || []).map((x) => String(x).toLowerCase()).includes(String(p.id).toLowerCase())
                  );
                  return (
                    <div key={user.id} className="p-5 hover:bg-gray-50 transition-colors">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0 space-y-1.5">
                          <div className="flex items-center gap-2.5 flex-wrap">
                            <h3 className="text-base font-bold text-gray-900">
                              {user.full_name}
                            </h3>
                            <Badge className={`${roleColors[rKey] || "bg-gray-100 text-gray-700"} border font-medium`}>
                              {roleLabels[rKey] || rKey || "Unassigned"}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-gray-600">
                            <span className="flex items-center gap-1">
                              <Mail className="w-3.5 h-3.5" />
                              {user.email}
                            </span>
                            {user.department && <span>• Dept: <b>{user.department}</b></span>}
                            {user.company_affiliation && <span>• Co: <b>{user.company_affiliation}</b></span>}
                          </div>
                          <div className="flex items-center gap-1.5 flex-wrap pt-1">
                            <span className="text-[11px] text-gray-500 font-semibold">Assigned Projects:</span>
                            {rKey === "admin" ? (
                              <Badge variant="outline" className="text-[10px] bg-red-50 text-red-700 border-red-200">
                                Global Enterprise Access (All Projects)
                              </Badge>
                            ) : userProjs.length > 0 ? (
                              userProjs.map((up) => (
                                <Badge key={up.id} variant="outline" className="text-[10px] bg-indigo-50 text-indigo-700 border-indigo-200">
                                  [{up.code}] {up.name}
                                </Badge>
                              ))
                            ) : (
                              <span className="text-[11px] text-amber-600 italic">No projects assigned</span>
                            )}
                          </div>
                        </div>

                        <div className="flex gap-2 shrink-0">
                          <Button onClick={() => handleEdit(user)} variant="outline" size="sm" className="text-xs h-8">
                            <Edit className="w-3.5 h-3.5 mr-1.5" />
                            Edit Role &amp; Projects
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </TabsContent>

        {/* ── TAB 3: INSPECTORS ── */}
        <TabsContent value="inspectors" className="mt-6 space-y-6">
          <Card className="elevation-2">
            <div className="p-5 border-b flex items-center gap-3">
              <div className="w-9 h-9 bg-purple-100 rounded-xl flex items-center justify-center">
                <UserCog className="w-5 h-5 text-purple-600" />
              </div>
              <h2 className="text-xl font-bold text-gray-900">Inspector &amp; TPI Agency Linkage</h2>
            </div>

            {inspectors.length === 0 ? (
              <div className="text-center py-12 text-gray-500">No inspectors found</div>
            ) : (
              <div className="divide-y">
                {inspectors.map((inspector) => (
                  <div key={inspector.id} className="p-5 hover:bg-gray-50 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-base font-bold text-gray-900">{inspector.full_name}</h3>
                        <Badge className="bg-purple-100 text-purple-800 border-purple-200 text-xs">Inspector</Badge>
                      </div>
                      <p className="text-xs text-gray-600">{inspector.email}</p>
                    </div>
                    <div className="min-w-[240px]">
                      <Label className="text-xs font-medium mb-1 block">Linked TPI Agency</Label>
                      <Select
                        value={inspector.tpi_agency_id || "none"}
                        onValueChange={async (value) => {
                          try {
                            await base44.entities.Inspector.update(inspector.id, {
                              tpi_agency_id: value === "none" ? null : value,
                            });
                            queryClient.invalidateQueries({ queryKey: ["inspectors"] });
                            toast.success("Inspector linked to TPI agency");
                          } catch (error) {
                            toast.error("Failed to update inspector");
                          }
                        }}
                      >
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue placeholder="Select TPI Agency" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">None</SelectItem>
                          {agencies.map((agency) => (
                            <SelectItem key={agency.id} value={agency.id}>
                              {agency.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </TabsContent>
      </Tabs>

      {/* Edit User Dialog */}
      <Dialog open={!!editingUser} onOpenChange={() => setEditingUser(null)}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit User Role &amp; Assigned Projects</DialogTitle>
          </DialogHeader>

          {editingUser && (
            <div className="space-y-4 py-3 text-xs">
              <div className="bg-gray-50 rounded-lg p-3">
                <h4 className="font-bold text-sm text-gray-900">{editingUser.full_name}</h4>
                <p className="text-xs text-gray-600">{editingUser.email}</p>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-semibold">System &amp; Departmental Role *</Label>
                <Select
                  value={editFormData.inspection_role}
                  onValueChange={(value) =>
                    setEditFormData({ ...editFormData, inspection_role: value })
                  }
                >
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue placeholder="Select Role" />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(roleLabels).map(([val, label]) => (
                      <SelectItem key={val} value={val} className="text-xs">
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs font-semibold">Department</Label>
                  <Input
                    value={editFormData.department}
                    onChange={(e) =>
                      setEditFormData({ ...editFormData, department: e.target.value })
                    }
                    className="h-8 text-xs mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs font-semibold">Company Affiliation</Label>
                  <Input
                    value={editFormData.company_affiliation}
                    onChange={(e) =>
                      setEditFormData({ ...editFormData, company_affiliation: e.target.value })
                    }
                    className="h-8 text-xs mt-1"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-semibold">Assigned Projects</Label>
                <div className="border rounded-lg p-3 max-h-44 overflow-y-auto space-y-2 bg-gray-50">
                  {projects.map((project) => {
                    const isChecked = (editFormData.project_ids || [])
                      .map((x) => String(x).toLowerCase())
                      .includes(String(project.id).toLowerCase());
                    return (
                      <label key={project.id} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          className="rounded border-gray-300 text-indigo-600"
                          checked={isChecked}
                          onChange={(e) => {
                            const currentIds = editFormData.project_ids || [];
                            const newIds = e.target.checked
                              ? [...currentIds, project.id]
                              : currentIds.filter(
                                  (id) => String(id).toLowerCase() !== String(project.id).toLowerCase()
                                );
                            setEditFormData({ ...editFormData, project_ids: newIds });
                          }}
                        />
                        <span className="text-xs font-medium text-gray-800">
                          [{project.code}] {project.name}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t">
                <Button variant="outline" size="sm" onClick={() => setEditingUser(null)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={updateUserMutation.isPending}
                  className="bg-indigo-600 hover:bg-indigo-700"
                >
                  Save Changes
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Add/Edit Project Dialog with Expediting Manager & QC Manager Assignment */}
      <Dialog
        open={isAddingProject || !!editingProject}
        onOpenChange={() => {
          setIsAddingProject(false);
          setEditingProject(null);
        }}
      >
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>
              {editingProject ? "Edit Project & Department Managers" : "Create New Project & Assign Managers"}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-semibold">Project Code *</Label>
                <Input
                  value={editingProject ? editingProject.code : projectFormData.code}
                  onChange={(e) =>
                    editingProject
                      ? setEditingProject({ ...editingProject, code: e.target.value })
                      : setProjectFormData({ ...projectFormData, code: e.target.value })
                  }
                  className="h-8 text-xs font-mono mt-1"
                  placeholder="PRJ-2026-01"
                />
              </div>
              <div>
                <Label className="text-xs font-semibold">Client / Operator</Label>
                <Input
                  value={editingProject ? editingProject.client_name || "" : projectFormData.client_name}
                  onChange={(e) =>
                    editingProject
                      ? setEditingProject({ ...editingProject, client_name: e.target.value })
                      : setProjectFormData({ ...projectFormData, client_name: e.target.value })
                  }
                  className="h-8 text-xs mt-1"
                  placeholder="ADNOC / QatarEnergy"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs font-semibold">Project Name *</Label>
              <Input
                value={editingProject ? editingProject.name : projectFormData.name}
                onChange={(e) =>
                  editingProject
                    ? setEditingProject({ ...editingProject, name: e.target.value })
                    : setProjectFormData({ ...projectFormData, name: e.target.value })
                }
                className="h-8 text-xs mt-1"
                placeholder="Offshore Gas Expansion Project"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
              <div className="p-2.5 rounded-lg bg-indigo-50/70 border border-indigo-200">
                <Label className="text-xs font-bold text-indigo-900 block mb-1">
                  Assign Expediting Manager *
                </Label>
                <Select
                  value={
                    editingProject
                      ? editingProject.expediting_manager_id || ""
                      : projectFormData.expediting_manager_id
                  }
                  onValueChange={(v) =>
                    editingProject
                      ? setEditingProject({ ...editingProject, expediting_manager_id: v })
                      : setProjectFormData({ ...projectFormData, expediting_manager_id: v })
                  }
                >
                  <SelectTrigger className="h-8 text-xs bg-white">
                    <SelectValue placeholder="Select Expediting Manager" />
                  </SelectTrigger>
                  <SelectContent>
                    {expManagers.map((u) => (
                      <SelectItem key={u.id} value={u.id} className="text-xs">
                        {u.full_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="p-2.5 rounded-lg bg-emerald-50/70 border border-emerald-200">
                <Label className="text-xs font-bold text-emerald-900 block mb-1">
                  Assign Inspection / QC Manager *
                </Label>
                <Select
                  value={
                    editingProject
                      ? editingProject.inspection_manager_id || ""
                      : projectFormData.inspection_manager_id
                  }
                  onValueChange={(v) =>
                    editingProject
                      ? setEditingProject({ ...editingProject, inspection_manager_id: v })
                      : setProjectFormData({ ...projectFormData, inspection_manager_id: v })
                  }
                >
                  <SelectTrigger className="h-8 text-xs bg-white">
                    <SelectValue placeholder="Select Inspection / QC Manager" />
                  </SelectTrigger>
                  <SelectContent>
                    {inspManagers.map((u) => (
                      <SelectItem key={u.id} value={u.id} className="text-xs">
                        {u.full_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label className="text-xs font-semibold">Project Description</Label>
              <Textarea
                value={editingProject ? editingProject.description || "" : projectFormData.description}
                onChange={(e) =>
                  editingProject
                    ? setEditingProject({ ...editingProject, description: e.target.value })
                    : setProjectFormData({ ...projectFormData, description: e.target.value })
                }
                rows={2}
                className="text-xs mt-1"
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setIsAddingProject(false);
                  setEditingProject(null);
                }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={async () => {
                  try {
                    const target = editingProject || projectFormData;
                    const res = await saveProjectGovernance({
                      project_id: editingProject ? editingProject.id : null,
                      ...target,
                    });
                    toast.success(res.message);
                    setIsAddingProject(false);
                    setEditingProject(null);
                  } catch (err) {
                    toast.error(err.message || "Failed to save project");
                  }
                }}
                className="bg-indigo-600 hover:bg-indigo-700"
              >
                Save Project &amp; Assign Managers
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Project Dialog */}
      <AlertDialog open={!!deletingProject} onOpenChange={() => setDeletingProject(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Project</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <strong>{deletingProject?.name}</strong>?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteProjectMutation.mutate(deletingProject.id)}
              className="bg-red-600 hover:bg-red-700"
            >
              Delete Project
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 2-Tier Project & PO Allocation Hub Modal */}
      <ProjectPoAllocationDialog
        open={allocationModalOpen}
        onOpenChange={setAllocationModalOpen}
        defaultTab={allocationDefaultTab}
        initialProjectId={allocationProjId}
        onSuccess={() => {
          refetchGovernance();
          queryClient.invalidateQueries({ queryKey: ["projects"] });
          queryClient.invalidateQueries({ queryKey: ["users"] });
        }}
      />

      {/* Register New Vendor Portal User Dialog */}
      <Dialog open={addVendorOpen} onOpenChange={setAddVendorOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Building2 className="w-4 h-4 text-amber-600" />
              Register Vendor / Supplier Portal Account
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2 text-xs">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-semibold">Supplier / Company Name *</Label>
                <Input
                  value={vendorForm.company_affiliation}
                  onChange={(e) => setVendorForm({ ...vendorForm, company_affiliation: e.target.value })}
                  placeholder="e.g., SNY Valves Ltd."
                  className="h-8 text-xs mt-1"
                />
              </div>
              <div>
                <Label className="text-xs font-semibold">Contact Full Name</Label>
                <Input
                  value={vendorForm.full_name}
                  onChange={(e) => setVendorForm({ ...vendorForm, full_name: e.target.value })}
                  placeholder="e.g., Ahmed Al-Kuwari"
                  className="h-8 text-xs mt-1"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-semibold">Login Email</Label>
                <Input
                  value={vendorForm.email}
                  onChange={(e) => setVendorForm({ ...vendorForm, email: e.target.value })}
                  placeholder="vendor@sny.com (auto if blank)"
                  className="h-8 text-xs font-mono mt-1"
                />
              </div>
              <div>
                <Label className="text-xs font-semibold">Phone</Label>
                <Input
                  value={vendorForm.phone}
                  onChange={(e) => setVendorForm({ ...vendorForm, phone: e.target.value })}
                  placeholder="+971-50-000-0000"
                  className="h-8 text-xs mt-1"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs font-semibold">Assigned Projects (Optional)</Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-32 overflow-y-auto border rounded-lg p-2 mt-1 bg-gray-50">
                {projects.map((p) => {
                  const checked = vendorForm.project_ids.includes(p.id);
                  return (
                    <label key={p.id} className="flex items-center gap-2 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...vendorForm.project_ids, p.id]
                            : vendorForm.project_ids.filter((x) => x !== p.id);
                          setVendorForm({ ...vendorForm, project_ids: next });
                        }}
                      />
                      <span className="truncate">[{p.code}] {p.name}</span>
                    </label>
                  );
                })}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-3 border-t">
              <Button variant="outline" size="sm" onClick={() => setAddVendorOpen(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={savingVendor}
                onClick={async () => {
                  if (!vendorForm.company_affiliation.trim()) {
                    toast.error("Supplier / Company Name is required");
                    return;
                  }
                  setSavingVendor(true);
                  try {
                    const res = await fetch("/api/v1/governance/vendors", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify(vendorForm),
                    });
                    const json = await res.json();
                    if (!res.ok || !json.ok) {
                      toast.error(json.detail || "Failed to register vendor");
                    } else {
                      toast.success(json.message);
                      queryClient.invalidateQueries({ queryKey: ["users"] });
                      queryClient.invalidateQueries({ queryKey: ["governance-overview"] });
                      window.dispatchEvent(new CustomEvent("governance-updated"));
                      setAddVendorOpen(false);
                    }
                  } catch (err) {
                    toast.error("Error saving vendor");
                  } finally {
                    setSavingVendor(false);
                  }
                }}
                className="bg-amber-600 hover:bg-amber-700 text-white"
              >
                Save Vendor Account
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

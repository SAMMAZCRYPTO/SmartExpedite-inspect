import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  FolderGit2,
  Users,
  Package,
  Plus,
  Trash2,
  CheckCircle2,
  RefreshCw,
  ShieldCheck,
  Building2,
} from "lucide-react";
import { toast } from "sonner";

export default function ProjectPoAllocationDialog({
  open,
  onOpenChange,
  defaultTab = "paired-po",
  initialProjectId = null,
  onSuccess,
}) {
  const [activeTab, setActiveTab] = useState(defaultTab);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [govData, setGovData] = useState({
    projects: [],
    pos: [],
    users: [],
    users_by_role: {},
  });

  // Tab 1: Tier 1 Project Form
  const [selectedProjId, setSelectedProjId] = useState("new");
  const [projForm, setProjForm] = useState({
    name: "",
    code: "",
    client_name: "",
    description: "",
    status: "active",
    expediting_manager_id: "",
    inspection_manager_id: "",
    requires_client_iap: false,
  });

  // Tab 2: Tier 2 Paired PO Allocation State
  const [filterProjId, setFilterProjId] = useState(initialProjectId || "all");
  const [poEdits, setPoEdits] = useState({});

  // Tab 3: Onboard New PO & BOM State
  const [newPoForm, setNewPoForm] = useState({
    po_number: `PO-${Math.floor(90000 + Math.random() * 9000)}`,
    project_id: initialProjectId && initialProjectId !== "all" ? initialProjectId : "",
    procurement_class: "tagged",
    contract_no: "",
    budget_no: "",
    mr_ref: "",
    incoterm: "DDP Site",
    cdd_date: "",
    ros_date: "",
    platform: "",
    delivery_point: "Site Warehouse / DDP",
    supplier: "",
    description: "",
    assigned_expeditor_id: "",
    assigned_field_expeditor_id: "",
    assigned_inspection_engineer_id: "",
    assigned_vendor_id: "__auto__",
    vendor_contact_name: "",
    vendor_email: "",
    vendor_phone: "",
    items: [
      {
        item: "10",
        desc: "Skid Structural Frame & Piping Manifold",
        qty: 10,
        unit: "EA",
        tag: "SK-101",
        location: "Vendor Works",
        ros_date: "",
        platform: "",
        despatch_location: "",
      },
      {
        item: "20",
        desc: "6-Inch Cryogenic Ball Valves ANSI 900#",
        qty: 50,
        unit: "EA",
        tag: "XV-201",
        location: "Vendor Works",
        ros_date: "",
        platform: "",
        despatch_location: "",
      },
    ],
  });

  const deriveVendorEmail = (sup) => {
    const slug = String(sup || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "");
    return slug ? `vendor@${slug}.com` : "vendor@supplier.com";
  };

  const fetchGovernance = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/governance/overview");
      const json = await res.json();
      if (json.ok) {
        setGovData(json);
        const projs = json.projects || [];
        const roles = json.users_by_role || {};

        if (projs.length > 0) {
          const targetP =
            (initialProjectId &&
              initialProjectId !== "all" &&
              projs.find((p) => p.id === initialProjectId)) ||
            projs[0];
          setSelectedProjId(targetP.id);
          setProjForm({
            name: targetP.name || "",
            code: targetP.code || "",
            client_name: targetP.client_name || "",
            description: targetP.description || "",
            status: targetP.status || "active",
            expediting_manager_id: targetP.expediting_manager_id || "",
            inspection_manager_id: targetP.inspection_manager_id || "",
            requires_client_iap: Boolean(targetP.requires_client_iap),
          });

          setNewPoForm((prev) => ({
            ...prev,
            project_id:
              initialProjectId && initialProjectId !== "all"
                ? initialProjectId
                : prev.project_id || targetP.id,
            assigned_expeditor_id:
              prev.assigned_expeditor_id ||
              roles.package_expeditors?.[0]?.id ||
              "",
            assigned_field_expeditor_id:
              prev.assigned_field_expeditor_id ||
              roles.field_expeditors?.[0]?.id ||
              "",
            assigned_inspection_engineer_id:
              prev.assigned_inspection_engineer_id ||
              roles.inspection_engineers?.[0]?.id ||
              "",
            assigned_vendor_id: prev.assigned_vendor_id || "__auto__",
          }));
        }

        // Initialize PO edits map
        const edits = {};
        (json.pos || []).forEach((p) => {
          edits[p.po] = {
            project_id: p.project_id || projs[0]?.id || "",
            assigned_expeditor_id: p.assigned_expeditor_id || "",
            assigned_field_expeditor_id: p.assigned_field_expeditor_id || "",
            assigned_inspection_engineer_id:
              p.assigned_inspection_engineer_id || "",
            assigned_vendor_id: p.assigned_vendor_id || "",
          };
        });
        setPoEdits(edits);
      }
    } catch (e) {
      console.error("Failed to load governance overview:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      setActiveTab(defaultTab);
      if (initialProjectId) setFilterProjId(initialProjectId);
      fetchGovernance();
    }
  }, [open, defaultTab, initialProjectId]);

  const handleSelectProjectForEdit = (pid) => {
    setSelectedProjId(pid);
    if (pid === "new") {
      const roles = govData.users_by_role || {};
      setProjForm({
        name: "",
        code: `PRJ-${Math.floor(1000 + Math.random() * 9000)}`,
        client_name: "ADNOC / QatarEnergy",
        description: "",
        status: "active",
        expediting_manager_id: roles.expediting_managers?.[0]?.id || "",
        inspection_manager_id: roles.inspection_managers?.[0]?.id || "",
        requires_client_iap: false,
      });
    } else {
      const found = (govData.projects || []).find((p) => p.id === pid);
      if (found) {
        setProjForm({
          name: found.name || "",
          code: found.code || "",
          client_name: found.client_name || "",
          description: found.description || "",
          status: found.status || "active",
          expediting_manager_id: found.expediting_manager_id || "",
          inspection_manager_id: found.inspection_manager_id || "",
          requires_client_iap: Boolean(found.requires_client_iap),
        });
      }
    }
  };

  const handleSaveTier1Project = async () => {
    if (!projForm.name || !projForm.code) {
      toast.error("Project Name and Code are required");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/v1/governance/project-assign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: selectedProjId === "new" ? null : selectedProjId,
          ...projForm,
        }),
      });
      const json = await res.json();
      if (json.ok) {
        toast.success(json.message);
        window.dispatchEvent(new CustomEvent("governance-updated"));
        await fetchGovernance();
        if (onSuccess) onSuccess();
      } else {
        toast.error(json.detail || "Failed to save project");
      }
    } catch (e) {
      toast.error("Error saving project governance");
    } finally {
      setSaving(false);
    }
  };

  const handleSavePoRoster = async (poNum) => {
    const edit = poEdits[poNum];
    if (!edit) return;
    setSaving(true);
    try {
      const res = await fetch("/api/v1/governance/po-assign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          po_number: poNum,
          ...edit,
        }),
      });
      const json = await res.json();
      if (json.ok) {
        toast.success(json.message);
        window.dispatchEvent(new CustomEvent("governance-updated"));
        await fetchGovernance();
        if (onSuccess) onSuccess();
      } else {
        toast.error(json.detail || "Failed to update PO roster");
      }
    } catch (e) {
      toast.error("Error updating PO roster");
    } finally {
      setSaving(false);
    }
  };

  const handleCreatePoWithBom = async () => {
    if (!newPoForm.po_number || !newPoForm.project_id || !newPoForm.supplier?.trim()) {
      toast.error("PO Number, Project, and Vendor / Supplier Name are required");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...newPoForm,
        vendor_mode:
          newPoForm.assigned_vendor_id === "__new__"
            ? "new"
            : newPoForm.assigned_vendor_id === "__auto__"
              ? "auto"
              : "existing",
      };
      const res = await fetch("/api/v1/governance/create-po-with-bom", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (json.ok) {
        toast.success(json.message);
        window.dispatchEvent(new CustomEvent("governance-updated"));
        await fetchGovernance();
        setNewPoForm((prev) => ({
          ...prev,
          po_number: `PO-${Math.floor(90000 + Math.random() * 9000)}`,
          supplier: "",
          description: "",
          assigned_vendor_id: "__auto__",
          vendor_contact_name: "",
          vendor_email: "",
          vendor_phone: "",
        }));
        setActiveTab("paired-po");
        if (onSuccess) onSuccess(json.po);
      } else {
        toast.error(json.detail || "Failed to create PO");
      }
    } catch (e) {
      toast.error("Error creating PO & BOM");
    } finally {
      setSaving(false);
    }
  };

  const roles = govData.users_by_role || {};
  const expManagers = roles.expediting_managers || [];
  const inspManagers = roles.inspection_managers || [];
  const pkgExpeditors = [
    ...(roles.package_expeditors || []),
    ...(roles.field_expeditors || []),
  ];
  const fieldExpeditors = roles.field_expeditors || [];
  const inspEngineers = [
    ...(roles.inspection_engineers || []),
    ...(roles.inspection_managers || []),
  ];
  const vendors = roles.vendors || [];

  const filteredPos = (govData.pos || []).filter(
    (p) => !filterProjId || filterProjId === "all" || p.project_id === filterProjId
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[90vh] flex flex-col p-6 overflow-hidden">
        <DialogHeader className="pb-3 border-b border-gray-200 shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600">
                <FolderGit2 className="w-5 h-5" />
              </div>
              <div>
                <DialogTitle className="text-base font-bold text-gray-900">
                  2-Tier Project &amp; PO Governance Hub (Expediting &harr; Inspection Interlink)
                </DialogTitle>
                <DialogDescription className="text-xs text-gray-500">
                  Tier 1: Global Admin assigns Project Expediting Manager &amp; QC Manager. Tier 2: Managers pair Expeditors &amp; Inspection Engineers on every PO.
                </DialogDescription>
              </div>
            </div>
            <Button
              variant="outline"
              size="xs"
              onClick={fetchGovernance}
              disabled={loading}
              className="text-xs h-7"
            >
              <RefreshCw className={`w-3 h-3 mr-1 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </DialogHeader>

        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex-1 flex flex-col overflow-hidden mt-2"
        >
          <TabsList className="grid grid-cols-3 bg-gray-100 p-1 rounded-xl shrink-0">
            <TabsTrigger value="tier1-project" className="text-xs font-semibold">
              <FolderGit2 className="w-3.5 h-3.5 mr-1.5" />
              1. Tier-1: Project &amp; Managers (Admin)
            </TabsTrigger>
            <TabsTrigger value="paired-po" className="text-xs font-semibold">
              <Users className="w-3.5 h-3.5 mr-1.5" />
              2. Tier-2: Paired PO Team Roster ({govData.pos?.length || 0})
            </TabsTrigger>
            <TabsTrigger value="new-po-bom" className="text-xs font-semibold">
              <Package className="w-3.5 h-3.5 mr-1.5" />
              3. Onboard New PO &amp; Dummy BOM
            </TabsTrigger>
          </TabsList>

          {/* ── TAB 1: TIER 1 PROJECT & DEPARTMENT MANAGERS ── */}
          <TabsContent
            value="tier1-project"
            className="flex-1 overflow-y-auto py-3 space-y-4"
          >
            <div className="p-4 rounded-xl bg-indigo-50/50 border border-indigo-100 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h4 className="text-xs font-bold text-indigo-950">
                    Select Project to Configure or Create New Project
                  </h4>
                  <p className="text-[11px] text-indigo-700">
                    Assigning an Expediting Manager and Inspection/QC Manager cascades across all POs and NOIs under that project.
                  </p>
                </div>
                <Select
                  value={selectedProjId}
                  onValueChange={handleSelectProjectForEdit}
                >
                  <SelectTrigger className="w-72 h-8 text-xs bg-white font-bold">
                    <SelectValue placeholder="Choose Project" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="new" className="text-xs font-bold text-indigo-600">
                      + Create New Capital Project
                    </SelectItem>
                    {(govData.projects || []).map((p) => (
                      <SelectItem key={p.id} value={p.id} className="text-xs">
                        [{p.code}] {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
                <div>
                  <Label className="text-xs font-semibold">Project Code *</Label>
                  <Input
                    value={projForm.code}
                    onChange={(e) =>
                      setProjForm({ ...projForm, code: e.target.value })
                    }
                    className="h-8 text-xs font-mono mt-1 bg-white"
                    placeholder="e.g., PRJ-TRAIN3"
                  />
                </div>
                <div>
                  <Label className="text-xs font-semibold">Project Name *</Label>
                  <Input
                    value={projForm.name}
                    onChange={(e) =>
                      setProjForm({ ...projForm, name: e.target.value })
                    }
                    className="h-8 text-xs mt-1 bg-white"
                    placeholder="e.g., Offshore Gas Expansion"
                  />
                </div>
                <div>
                  <Label className="text-xs font-semibold">Client / Operator</Label>
                  <Input
                    value={projForm.client_name}
                    onChange={(e) =>
                      setProjForm({ ...projForm, client_name: e.target.value })
                    }
                    className="h-8 text-xs mt-1 bg-white"
                    placeholder="e.g., ADNOC / QatarEnergy"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                <div className="p-3 rounded-lg bg-white border border-indigo-200">
                  <Label className="text-xs font-bold text-indigo-800 block mb-1">
                    Project Expediting Manager (Department Head) *
                  </Label>
                  <Select
                    value={projForm.expediting_manager_id}
                    onValueChange={(v) =>
                      setProjForm({ ...projForm, expediting_manager_id: v })
                    }
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder="Assign Expediting Manager" />
                    </SelectTrigger>
                    <SelectContent>
                      {expManagers.map((u) => (
                        <SelectItem key={u.id} value={u.id} className="text-xs">
                          {u.full_name} ({u.email})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-gray-500 mt-1">
                    Has full Project PO read/write &amp; allocates Package Expeditors.
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-white border border-emerald-200">
                  <Label className="text-xs font-bold text-emerald-800 block mb-1">
                    Project Inspection / QC Manager (Department Head) *
                  </Label>
                  <Select
                    value={projForm.inspection_manager_id}
                    onValueChange={(v) =>
                      setProjForm({ ...projForm, inspection_manager_id: v })
                    }
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder="Assign Inspection / QC Manager" />
                    </SelectTrigger>
                    <SelectContent>
                      {inspManagers.map((u) => (
                        <SelectItem key={u.id} value={u.id} className="text-xs">
                          {u.full_name} ({u.email})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-gray-500 mt-1">
                    Has full Project Quality oversight, concessions &amp; allocates Inspection Engineers.
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
                <label className="flex items-center gap-2 text-xs text-gray-700 bg-white px-3 py-1.5 rounded-lg border border-gray-200 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={Boolean(projForm.requires_client_iap)}
                    onChange={(e) =>
                      setProjForm({ ...projForm, requires_client_iap: e.target.checked })
                    }
                  />
                  <span className="font-semibold">Requires Client IAP Gate</span>
                  <span className="text-[10px] text-gray-500">(Aramco / ADNOC IAP workflow before PIM/FAT)</span>
                </label>
                <Button
                  size="sm"
                  onClick={handleSaveTier1Project}
                  disabled={saving}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs h-8 font-semibold"
                >
                  <ShieldCheck className="w-3.5 h-3.5 mr-1.5" />
                  {selectedProjId === "new"
                    ? "Create Project & Assign Managers"
                    : "Save Project & Cascade Manager Assignments"}
                </Button>
              </div>
            </div>
          </TabsContent>

          {/* ── TAB 2: TIER 2 PAIRED PO OWNERSHIP MATRIX ── */}
          <TabsContent
            value="paired-po"
            className="flex-1 overflow-y-auto py-3 space-y-3"
          >
            <div className="flex items-center justify-between bg-gray-50 p-2.5 rounded-xl border border-gray-200">
              <div className="text-xs text-gray-700">
                <b>Hand-in-Hand Paired PO Ownership:</b> Assign the Package Expeditor and Inspection Engineer working together on each Purchase Order.
              </div>
              <div className="flex items-center gap-2">
                <Label className="text-xs font-semibold">Filter Project:</Label>
                <Select value={filterProjId} onValueChange={setFilterProjId}>
                  <SelectTrigger className="w-56 h-7 text-xs bg-white">
                    <SelectValue placeholder="All Projects" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all" className="text-xs font-bold">
                      All Projects ({govData.pos?.length || 0} POs)
                    </SelectItem>
                    {(govData.projects || []).map((p) => (
                      <SelectItem key={p.id} value={p.id} className="text-xs">
                        [{p.code}] {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2.5">
              {filteredPos.map((po) => {
                const edit = poEdits[po.po] || {};
                return (
                  <div
                    key={po.po}
                    className="p-3.5 rounded-xl border border-gray-200 bg-white shadow-xs space-y-2.5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-gray-100">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-xs text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                          PO #{po.po}
                        </span>
                        <span className="text-xs font-bold text-gray-900">
                          {po.supplier}
                        </span>
                        <span className="text-xs text-gray-500">
                          — {po.head}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Badge variant="outline" className="text-[10px] bg-gray-50">
                          {po.bom_count} BOM Items ({po.total_ordered_qty} Qty)
                        </Badge>
                        <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-700 border-blue-200">
                          {po.inspection_count} Linked NOI(s)
                        </Badge>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5 text-xs">
                      <div>
                        <Label className="text-[10px] text-gray-500 font-semibold block mb-1">
                          1. Assigned Project
                        </Label>
                        <Select
                          value={edit.project_id || ""}
                          onValueChange={(v) =>
                            setPoEdits({
                              ...poEdits,
                              [po.po]: { ...edit, project_id: v },
                            })
                          }
                        >
                          <SelectTrigger className="h-7 text-[11px]">
                            <SelectValue placeholder="Project" />
                          </SelectTrigger>
                          <SelectContent>
                            {(govData.projects || []).map((p) => (
                              <SelectItem key={p.id} value={p.id} className="text-xs">
                                [{p.code}] {p.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label className="text-[10px] text-indigo-700 font-bold block mb-1">
                          2. Package Expeditor (Expediting)
                        </Label>
                        <Select
                          value={edit.assigned_expeditor_id || ""}
                          onValueChange={(v) =>
                            setPoEdits({
                              ...poEdits,
                              [po.po]: { ...edit, assigned_expeditor_id: v },
                            })
                          }
                        >
                          <SelectTrigger className="h-7 text-[11px] border-indigo-200 bg-indigo-50/30">
                            <SelectValue placeholder="Package Expeditor" />
                          </SelectTrigger>
                          <SelectContent>
                            {pkgExpeditors.map((u) => (
                              <SelectItem key={u.id} value={u.id} className="text-xs">
                                {u.full_name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label className="text-[10px] text-emerald-700 font-bold block mb-1">
                          3. Inspection Engineer (Quality)
                        </Label>
                        <Select
                          value={edit.assigned_inspection_engineer_id || ""}
                          onValueChange={(v) =>
                            setPoEdits({
                              ...poEdits,
                              [po.po]: {
                                ...edit,
                                assigned_inspection_engineer_id: v,
                              },
                            })
                          }
                        >
                          <SelectTrigger className="h-7 text-[11px] border-emerald-200 bg-emerald-50/30">
                            <SelectValue placeholder="Inspection Engineer" />
                          </SelectTrigger>
                          <SelectContent>
                            {inspEngineers.map((u) => (
                              <SelectItem key={u.id} value={u.id} className="text-xs">
                                {u.full_name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label className="text-[10px] text-amber-700 font-bold block mb-1">
                          4. Vendor Portal Account
                        </Label>
                        <Select
                          value={edit.assigned_vendor_id || ""}
                          onValueChange={(v) =>
                            setPoEdits({
                              ...poEdits,
                              [po.po]: { ...edit, assigned_vendor_id: v },
                            })
                          }
                        >
                          <SelectTrigger className="h-7 text-[11px]">
                            <SelectValue placeholder="Vendor User" />
                          </SelectTrigger>
                          <SelectContent>
                            {vendors.map((u) => (
                              <SelectItem key={u.id} value={u.id} className="text-xs">
                                {u.full_name} ({u.company_affiliation || u.email})
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="flex items-end">
                        <Button
                          size="xs"
                          onClick={() => handleSavePoRoster(po.po)}
                          disabled={saving}
                          className="w-full h-7 bg-indigo-600 hover:bg-indigo-700 text-white text-[11px] font-semibold"
                        >
                          <CheckCircle2 className="w-3 h-3 mr-1" />
                          Save Paired Roster
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </TabsContent>

          {/* ── TAB 3: ONBOARD NEW PO & BILL OF MATERIALS ── */}
          <TabsContent
            value="new-po-bom"
            className="flex-1 overflow-y-auto py-3 space-y-4"
          >
            <div className="p-4 rounded-xl border border-gray-200 bg-white space-y-3">
              <h4 className="text-xs font-bold text-gray-900">
                Create New Purchase Order &amp; Bill of Materials (Shared Project PO Registry)
              </h4>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                <div>
                  <Label className="text-xs font-semibold">PO Number *</Label>
                  <Input
                    value={newPoForm.po_number}
                    onChange={(e) =>
                      setNewPoForm({ ...newPoForm, po_number: e.target.value })
                    }
                    className="h-8 text-xs font-mono mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs font-semibold">Project *</Label>
                  <Select
                    value={newPoForm.project_id}
                    onValueChange={(v) =>
                      setNewPoForm({ ...newPoForm, project_id: v })
                    }
                  >
                    <SelectTrigger className="h-8 text-xs mt-1">
                      <SelectValue placeholder="Select Project" />
                    </SelectTrigger>
                    <SelectContent>
                      {(govData.projects || []).map((p) => (
                        <SelectItem key={p.id} value={p.id} className="text-xs">
                          [{p.code}] {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs font-semibold">Vendor / Supplier Name *</Label>
                  <Input
                    value={newPoForm.supplier}
                    onChange={(e) =>
                      setNewPoForm({ ...newPoForm, supplier: e.target.value })
                    }
                    placeholder="e.g., SNY Valves & Controls"
                    className="h-8 text-xs mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs font-semibold">Package Title &amp; Schedule Type</Label>
                  <div className="flex gap-1.5 mt-1">
                    <Input
                      value={newPoForm.description}
                      onChange={(e) =>
                        setNewPoForm({ ...newPoForm, description: e.target.value })
                      }
                      placeholder="e.g., High-Pressure Control Valves"
                      className="h-8 text-xs flex-1"
                    />
                    <Select
                      value={newPoForm.procurement_class || "tagged"}
                      onValueChange={(v) =>
                        setNewPoForm({ ...newPoForm, procurement_class: v })
                      }
                    >
                      <SelectTrigger className="h-8 text-[11px] w-28">
                        <SelectValue placeholder="Type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="tagged" className="text-xs">Tagged</SelectItem>
                        <SelectItem value="bulk" className="text-xs">Bulk</SelectItem>
                        <SelectItem value="package" className="text-xs">Package</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>

              {/* NEAS Order Fields Strip */}
              <div className="grid grid-cols-2 md:grid-cols-6 gap-2.5 text-xs bg-slate-50 p-3 rounded-lg border border-slate-200">
                <div>
                  <Label className="text-[11px] font-semibold">Contract No.</Label>
                  <Input
                    value={newPoForm.contract_no}
                    onChange={(e) => setNewPoForm({ ...newPoForm, contract_no: e.target.value })}
                    placeholder="4700026176"
                    className="h-7 text-xs bg-white mt-1 font-mono"
                  />
                </div>
                <div>
                  <Label className="text-[11px] font-semibold">MR No.</Label>
                  <Input
                    value={newPoForm.mr_ref}
                    onChange={(e) => setNewPoForm({ ...newPoForm, mr_ref: e.target.value })}
                    placeholder="MR-2820-001"
                    className="h-7 text-xs bg-white mt-1 font-mono"
                  />
                </div>
                <div>
                  <Label className="text-[11px] font-semibold">CDD Date</Label>
                  <Input
                    type="date"
                    value={newPoForm.cdd_date}
                    onChange={(e) => setNewPoForm({ ...newPoForm, cdd_date: e.target.value })}
                    className="h-7 text-xs bg-white mt-1"
                  />
                </div>
                <div>
                  <Label className="text-[11px] font-semibold">ROS Date</Label>
                  <Input
                    type="date"
                    value={newPoForm.ros_date}
                    onChange={(e) => setNewPoForm({ ...newPoForm, ros_date: e.target.value })}
                    className="h-7 text-xs bg-white mt-1"
                  />
                </div>
                <div>
                  <Label className="text-[11px] font-semibold">Platform / Facility</Label>
                  <Input
                    value={newPoForm.platform}
                    onChange={(e) => setNewPoForm({ ...newPoForm, platform: e.target.value })}
                    placeholder="e.g. LZ Platform-4"
                    className="h-7 text-xs bg-white mt-1"
                  />
                </div>
                <div>
                  <Label className="text-[11px] font-semibold">Despatch Location</Label>
                  <Input
                    value={newPoForm.delivery_point}
                    onChange={(e) => setNewPoForm({ ...newPoForm, delivery_point: e.target.value })}
                    placeholder="Mussafah / Offshore"
                    className="h-7 text-xs bg-white mt-1"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs pt-1">
                <div>
                  <Label className="text-xs font-semibold text-indigo-700">
                    Assigned Package Expeditor
                  </Label>
                  <Select
                    value={newPoForm.assigned_expeditor_id}
                    onValueChange={(v) =>
                      setNewPoForm({ ...newPoForm, assigned_expeditor_id: v })
                    }
                  >
                    <SelectTrigger className="h-8 text-xs mt-1">
                      <SelectValue placeholder="Select Expeditor" />
                    </SelectTrigger>
                    <SelectContent>
                      {pkgExpeditors.map((u) => (
                        <SelectItem key={u.id} value={u.id} className="text-xs">
                          {u.full_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs font-semibold text-emerald-700">
                    Paired Inspection Engineer
                  </Label>
                  <Select
                    value={newPoForm.assigned_inspection_engineer_id}
                    onValueChange={(v) =>
                      setNewPoForm({
                        ...newPoForm,
                        assigned_inspection_engineer_id: v,
                      })
                    }
                  >
                    <SelectTrigger className="h-8 text-xs mt-1">
                      <SelectValue placeholder="Select Inspection Engineer" />
                    </SelectTrigger>
                    <SelectContent>
                      {inspEngineers.map((u) => (
                        <SelectItem key={u.id} value={u.id} className="text-xs">
                          {u.full_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs font-semibold text-amber-700">
                    Vendor Portal User
                  </Label>
                  <Select
                    value={newPoForm.assigned_vendor_id || "__auto__"}
                    onValueChange={(v) =>
                      setNewPoForm({ ...newPoForm, assigned_vendor_id: v })
                    }
                  >
                    <SelectTrigger className="h-8 text-xs mt-1">
                      <SelectValue placeholder="Select or Auto-Create Vendor" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__auto__" className="text-xs font-semibold text-amber-800">
                        + Auto-Create / Match Vendor for Supplier Above
                      </SelectItem>
                      <SelectItem value="__new__" className="text-xs font-semibold text-indigo-700">
                        + Register Custom Vendor Contact &amp; Login
                      </SelectItem>
                      {vendors.map((u) => (
                        <SelectItem key={u.id} value={u.id} className="text-xs">
                          {u.full_name} ({u.company_affiliation || u.email})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {["__auto__", "__new__"].includes(newPoForm.assigned_vendor_id || "__auto__") && (
                <div className="p-3 rounded-lg bg-amber-50/70 border border-amber-200 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[11px] font-bold text-amber-900">
                      Vendor Details &amp; Auto-Provisioned Portal Access
                    </span>
                    <span className="text-[10px] text-amber-700">
                      Automatically added to Vendor Master with a cryptographically random temporary credential when PO is created
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-xs">
                    <div>
                      <Label className="text-[11px] font-semibold text-gray-700">Vendor Contact Name</Label>
                      <Input
                        value={newPoForm.vendor_contact_name}
                        onChange={(e) =>
                          setNewPoForm({ ...newPoForm, vendor_contact_name: e.target.value })
                        }
                        placeholder={
                          newPoForm.supplier
                            ? `${newPoForm.supplier} (Vendor Lead)`
                            : "Supplier Lead / Coordinator"
                        }
                        className="h-7 text-xs bg-white mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-[11px] font-semibold text-gray-700">Vendor Login Email</Label>
                      <Input
                        value={newPoForm.vendor_email}
                        onChange={(e) =>
                          setNewPoForm({ ...newPoForm, vendor_email: e.target.value })
                        }
                        placeholder={deriveVendorEmail(newPoForm.supplier)}
                        className="h-7 text-xs font-mono bg-white mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-[11px] font-semibold text-gray-700">Vendor Phone (Optional)</Label>
                      <Input
                        value={newPoForm.vendor_phone}
                        onChange={(e) =>
                          setNewPoForm({ ...newPoForm, vendor_phone: e.target.value })
                        }
                        placeholder="+971-50-000-0000"
                        className="h-7 text-xs bg-white mt-1"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* BOM Line Items Builder */}
              <div className="pt-2 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Label className="text-xs font-bold text-gray-800">
                    Bill of Materials (BOM) Line Items ({newPoForm.items.length})
                  </Label>
                  <div className="flex items-center gap-1.5">
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      onClick={() => {
                        const raw = window.prompt(
                          "Paste multiple BOM items (one per line: Item# | Description | Qty | Unit | Tag | Location):",
                          "30 | Carbon Steel Flange Kit | 20 | EA | FL-301 | Milan Shop\n40 | Pressure Relief Valve | 4 | EA | PSV-401 | Dubai Works"
                        );
                        if (!raw) return;
                        const parsed = raw
                          .split(/\r?\n/)
                          .map((ln) => ln.trim())
                          .filter(Boolean)
                          .map((ln, i) => {
                            const parts = ln.split(/\s*[|,;\t]\s*/);
                            return {
                              item: parts[0] || String((newPoForm.items.length + i + 1) * 10),
                              desc: parts[1] || `BOM Item ${i + 1}`,
                              qty: Number(parts[2]) || 1,
                              unit: (parts[3] || "EA").toUpperCase(),
                              tag: parts[4] || `TAG-${(newPoForm.items.length + i + 1) * 10}`,
                              location: parts[5] || "Vendor Works",
                              ros_date: newPoForm.ros_date || "",
                              platform: newPoForm.platform || "",
                              despatch_location: newPoForm.delivery_point || "",
                            };
                          });
                        if (parsed.length) {
                          setNewPoForm({ ...newPoForm, items: [...newPoForm.items, ...parsed] });
                          toast.success(`Added ${parsed.length} BOM line items.`);
                        }
                      }}
                      className="h-7 text-xs border-indigo-200 text-indigo-700 hover:bg-indigo-50"
                    >
                      + Bulk Paste Items
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      onClick={() =>
                        setNewPoForm({
                          ...newPoForm,
                          items: [
                            ...newPoForm.items,
                            {
                              item: String((newPoForm.items.length + 1) * 10),
                              desc: "New Engineered Sub-Assembly",
                              qty: 10,
                              unit: "EA",
                              tag: `TAG-${(newPoForm.items.length + 1) * 10}`,
                              location: "Vendor Works",
                              ros_date: newPoForm.ros_date || "",
                              platform: newPoForm.platform || "",
                              despatch_location: newPoForm.delivery_point || "",
                            },
                          ],
                        })
                      }
                      className="h-7 text-xs"
                    >
                      <Plus className="w-3 h-3 mr-1" /> Add BOM Line
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  {newPoForm.items.map((itm, idx) => (
                    <div
                      key={idx}
                      className="grid grid-cols-12 gap-2 items-center bg-gray-50 p-2 rounded-lg border border-gray-200 text-xs"
                    >
                      <div className="col-span-1">
                        <Input
                          value={itm.item}
                          onChange={(e) => {
                            const next = [...newPoForm.items];
                            next[idx].item = e.target.value;
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          className="h-7 text-xs font-mono"
                          placeholder="Item#"
                        />
                      </div>
                      <div className="col-span-4">
                        <Input
                          value={itm.desc}
                          onChange={(e) => {
                            const next = [...newPoForm.items];
                            next[idx].desc = e.target.value;
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          className="h-7 text-xs"
                          placeholder="Material Description"
                        />
                      </div>
                      <div className="col-span-2">
                        <Input
                          value={itm.tag}
                          onChange={(e) => {
                            const next = [...newPoForm.items];
                            next[idx].tag = e.target.value;
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          className="h-7 text-xs font-mono"
                          placeholder="Tag #"
                        />
                      </div>
                      <div className="col-span-1">
                        <Input
                          type="number"
                          value={itm.qty}
                          onChange={(e) => {
                            const next = [...newPoForm.items];
                            next[idx].qty = Number(e.target.value);
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          className="h-7 text-xs font-bold"
                        />
                      </div>
                      <div className="col-span-1">
                        <Input
                          value={itm.unit}
                          onChange={(e) => {
                            const next = [...newPoForm.items];
                            next[idx].unit = e.target.value;
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          className="h-7 text-xs font-mono"
                        />
                      </div>
                      <div className="col-span-2">
                        <Input
                          value={itm.location}
                          onChange={(e) => {
                            const next = [...newPoForm.items];
                            next[idx].location = e.target.value;
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          className="h-7 text-xs"
                          placeholder="Location"
                        />
                      </div>
                      <div className="col-span-1 text-right">
                        <Button
                          type="button"
                          variant="ghost"
                          size="xs"
                          onClick={() => {
                            const next = newPoForm.items.filter((_, i) => i !== idx);
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          className="h-7 w-7 p-0 text-rose-600"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                      <div className="col-span-12 grid grid-cols-3 gap-2 pt-1 border-t border-gray-200/70">
                        <Input
                          type="date"
                          value={itm.ros_date || ""}
                          onChange={(e) => {
                            const next = [...newPoForm.items];
                            next[idx].ros_date = e.target.value;
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          title="Item ROS Date"
                          className="h-6 text-[11px] bg-white"
                        />
                        <Input
                          value={itm.platform || ""}
                          onChange={(e) => {
                            const next = [...newPoForm.items];
                            next[idx].platform = e.target.value;
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          placeholder="Item Platform (NEAS)"
                          className="h-6 text-[11px] bg-white"
                        />
                        <Input
                          value={itm.despatch_location || ""}
                          onChange={(e) => {
                            const next = [...newPoForm.items];
                            next[idx].despatch_location = e.target.value;
                            setNewPoForm({ ...newPoForm, items: next });
                          }}
                          placeholder="Item Despatch Location"
                          className="h-6 text-[11px] bg-white"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  size="sm"
                  onClick={handleCreatePoWithBom}
                  disabled={saving}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs h-8 font-semibold"
                >
                  <Plus className="w-3.5 h-3.5 mr-1.5" />
                  Create PO &amp; Interlink BOM Across Expediting &amp; Inspection
                </Button>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}


import React, { useState } from "react";
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogFooter 
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Scissors, Plus, Trash2, MapPin, Tag, Package } from "lucide-react";
import { toast } from "sonner";

export default function SplitItemDialog({ open, onOpenChange, currentPo, onSplitsSaved }) {
  const [parentItem, setParentItem] = useState("10");
  const [parentDesc, setParentDesc] = useState("Complete Skid Package (Valves, Vessel & Instrumentation)");
  const [splits, setSplits] = useState([
    {
      item: "10.1",
      desc: "Skid Structural Steel Base & Piping",
      qty: 1,
      unit: "SET",
      location: "Dubai Fabrication Yard (Shop A)",
      tag: "SKD-01-A",
    },
    {
      item: "10.2",
      desc: "Pressure Vessel 24\" (ASME Sec VIII)",
      qty: 1,
      unit: "EA",
      location: "Mussafah Heavy Fab Shop (Shop B)",
      tag: "V-101",
    },
    {
      item: "10.3",
      desc: "Control & Instrumentation Junction Box",
      qty: 1,
      unit: "EA",
      location: "Dammam Electrical Yard",
      tag: "CP-101",
    },
  ]);
  const [submitting, setSubmitting] = useState(false);

  const handleAddSplit = () => {
    const nextIdx = splits.length + 1;
    setSplits([
      ...splits,
      {
        item: `${parentItem}.${nextIdx}`,
        desc: "",
        qty: 1,
        unit: "EA",
        location: "Shop Floor",
        tag: "",
      },
    ]);
  };

  const handleRemoveSplit = (idx) => {
    if (splits.length <= 1) {
      toast.error("At least one split sub-assembly is required.");
      return;
    }
    setSplits(splits.filter((_, i) => i !== idx));
  };

  const handleSplitChange = (idx, field, val) => {
    const updated = [...splits];
    updated[idx][field] = val;
    setSplits(updated);
  };

  const handleSaveSplits = async () => {
    if (!currentPo) {
      toast.error("Please enter or select a valid PO Number.");
      return;
    }
    if (!parentItem.trim()) {
      toast.error("Parent Item Number is required.");
      return;
    }
    for (const s of splits) {
      if (!s.item.trim() || !s.desc.trim()) {
        toast.error("Each split item must have a valid Item Number and Material Description.");
        return;
      }
    }

    setSubmitting(true);
    try {
      const res = await fetch("/api/v1/po/split-item", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          po: currentPo,
          parent_item: parentItem,
          splits: splits,
          by: "Package Expeditor",
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to save split items");
      }

      toast.success(data.message || `Successfully split Item ${parentItem} into ${splits.length} sub-assemblies!`);
      if (onSplitsSaved) onSplitsSaved(data);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.message || "Error submitting item splits.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-indigo-950 text-base md:text-lg">
            <div className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center">
              <Scissors className="w-4 h-4" />
            </div>
            <span>Split Package PO Line Item — Multi-Location Sub-Assemblies</span>
          </DialogTitle>
        </DialogHeader>

        <p className="text-xs text-gray-600 bg-indigo-50/70 p-3 rounded-lg border border-indigo-100">
          💡 <strong>Package Expeditor Rule:</strong> When a single package PO line item consists of multiple components manufactured or inspected at different vendor shops or geographical locations, split the item here. Each sub-assembly will immediately populate <strong>SmartExpedit</strong> and <strong>InspectFlow</strong> as independent selectable target items for inspection notifications (NOIs) and Inspection Release Certificates (IRCs).
        </p>

        {/* Parent Item Definition */}
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-3.5 space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700 flex items-center gap-1.5">
            <Package className="w-4 h-4 text-indigo-600" />
            Parent Package Line Item
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <Label className="text-xs text-gray-600">PO Number</Label>
              <Input
                value={currentPo || ""}
                disabled
                className="h-8 text-xs font-mono font-bold bg-white"
              />
            </div>
            <div>
              <Label className="text-xs text-gray-600">Parent Item #</Label>
              <Input
                value={parentItem}
                onChange={(e) => setParentItem(e.target.value)}
                placeholder="e.g. 10"
                className="h-8 text-xs font-mono font-bold bg-white"
              />
            </div>
            <div>
              <Label className="text-xs text-gray-600">Parent Description</Label>
              <Input
                value={parentDesc}
                onChange={(e) => setParentDesc(e.target.value)}
                placeholder="Overall Package Description"
                className="h-8 text-xs bg-white"
              />
            </div>
          </div>
        </div>

        {/* Sub-Assemblies Table */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700">
              Configured Sub-Assemblies ({splits.length})
            </h4>
            <Button
              size="xs"
              variant="outline"
              onClick={handleAddSplit}
              className="text-indigo-600 border-indigo-200 hover:bg-indigo-50 text-xs h-7"
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              Add Sub-Assembly
            </Button>
          </div>

          <div className="border border-gray-200 rounded-xl overflow-hidden shadow-xs">
            <Table>
              <TableHeader>
                <TableRow className="bg-gray-100 text-xs">
                  <TableHead className="w-24">Sub-Item #</TableHead>
                  <TableHead>Sub-Assembly Description (As Per Drawings)</TableHead>
                  <TableHead className="w-20">Qty</TableHead>
                  <TableHead className="w-20">Unit</TableHead>
                  <TableHead className="w-48">Inspection / Shop Location</TableHead>
                  <TableHead className="w-28">Tag #</TableHead>
                  <TableHead className="w-12 text-center"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {splits.map((s, idx) => (
                  <TableRow key={idx} className="hover:bg-gray-50/70 text-xs">
                    <TableCell>
                      <Input
                        value={s.item}
                        onChange={(e) => handleSplitChange(idx, "item", e.target.value)}
                        className="h-7 text-xs font-mono font-bold"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={s.desc}
                        onChange={(e) => handleSplitChange(idx, "desc", e.target.value)}
                        placeholder="Material / Component Description"
                        className="h-7 text-xs"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min="1"
                        value={s.qty}
                        onChange={(e) => handleSplitChange(idx, "qty", parseFloat(e.target.value) || 1)}
                        className="h-7 text-xs font-mono text-center"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={s.unit}
                        onChange={(e) => handleSplitChange(idx, "unit", e.target.value)}
                        className="h-7 text-xs uppercase"
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <MapPin className="w-3 h-3 text-gray-400 shrink-0" />
                        <Input
                          value={s.location}
                          onChange={(e) => handleSplitChange(idx, "location", e.target.value)}
                          placeholder="Yard / Shop Location"
                          className="h-7 text-xs"
                        />
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Tag className="w-3 h-3 text-gray-400 shrink-0" />
                        <Input
                          value={s.tag}
                          onChange={(e) => handleSplitChange(idx, "tag", e.target.value)}
                          placeholder="Tag #"
                          className="h-7 text-xs font-mono"
                        />
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => handleRemoveSplit(idx)}
                        className="h-7 w-7 text-red-500 hover:text-red-700 hover:bg-red-50"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleSaveSplits}
            disabled={submitting}
            className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold"
          >
            {submitting ? "Saving & Syncing..." : "Save Splits & Sync to InspectFlow"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


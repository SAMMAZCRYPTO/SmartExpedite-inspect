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
import { Textarea } from "@/components/ui/textarea";
import { Truck, CheckCircle, Ship, MapPin, PackageCheck } from "lucide-react";
import { toast } from "sonner";

export default function LogisticsStageDialog({ open, onOpenChange, currentPo, onSuccess }) {
  const [itemNumber, setItemNumber] = useState("10");
  const [stage, setStage] = useState("ex_works"); // packing | ex_works | in_transit | mrv_delivered
  const [qty, setQty] = useState(50);
  const [blAwb, setBlAwb] = useState("AWB-9842512");
  const [carrier, setCarrier] = useState("DHL Global Forwarding");
  const [mrvNo, setMrvNo] = useState("MRV-2026-089");
  const [stampedDnRef, setStampedDnRef] = useState("");
  const [osdNotes, setOsdNotes] = useState("Clean receipt; no OS&D (Over, Short, Damage) noted.");
  const [submitting, setSubmitting] = useState(false);

  const stages = [
    { id: "packing", label: "1. Ready for Dispatch", desc: "Packing & final crating complete", icon: PackageCheck },
    { id: "ex_works", label: "2. Ex-Works Handover", desc: "Handed to freight forwarder (BL/AWB)", icon: Truck },
    { id: "in_transit", label: "3. Port & Customs", desc: "Sea/air transit & customs clearance", icon: Ship },
    { id: "mrv_delivered", label: "4. Site Receipt (MRV)", desc: "Delivered to site, MRV signed off", icon: MapPin },
  ];

  const handleUpdateStage = async () => {
    if (!currentPo) {
      toast.error("Valid PO Number required.");
      return;
    }
    if (!itemNumber.trim()) {
      toast.error("Item Number is required.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch("/api/v1/delivery/update-stage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          po: currentPo,
          item: itemNumber,
          stage: stage,
          qty: qty,
          bl_awb: blAwb,
          carrier: carrier,
          mrv_no: mrvNo,
          stamped_delivery_note_ref: stampedDnRef,
          osd_notes: osdNotes,
          by: "Logistics Coordinator",
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update logistics stage");

      toast.success(`Logistics stage successfully advanced to [${stage.toUpperCase()}] for Item ${itemNumber}!`);
      if (onSuccess) onSuccess(data);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.message || "Error updating logistics stage.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base md:text-lg font-bold text-gray-900">
            <Truck className="w-5 h-5 text-indigo-600" />
            <span>4-Stage Logistics &amp; Site Receipt (MRV) Pipeline</span>
          </DialogTitle>
        </DialogHeader>

        {/* 4-Stage Selection Selector */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {stages.map((st) => {
            const Icon = st.icon;
            const isSelected = stage === st.id;
            return (
              <button
                key={st.id}
                type="button"
                onClick={() => setStage(st.id)}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  isSelected
                    ? "border-indigo-600 bg-indigo-50/80 shadow-xs ring-2 ring-indigo-500/20"
                    : "border-gray-200 bg-white hover:bg-gray-50"
                }`}
              >
                <Icon className={`w-4 h-4 mb-1 ${isSelected ? "text-indigo-600" : "text-gray-500"}`} />
                <p className="text-xs font-bold text-gray-900">{st.label}</p>
                <p className="text-[10px] text-gray-500 line-clamp-1 mt-0.5">{st.desc}</p>
              </button>
            );
          })}
        </div>

        {/* Details Form */}
        <div className="space-y-3 bg-gray-50/70 p-4 rounded-xl border border-gray-200">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <Label className="text-xs text-gray-600">PO Number</Label>
              <Input value={currentPo || ""} disabled className="h-8 text-xs font-mono font-bold bg-white" />
            </div>
            <div>
              <Label className="text-xs text-gray-600">Item Number</Label>
              <Input
                value={itemNumber}
                onChange={(e) => setItemNumber(e.target.value)}
                placeholder="e.g. 10 or 10.1"
                className="h-8 text-xs font-mono font-bold bg-white"
              />
            </div>
            <div>
              <Label className="text-xs text-gray-600">Dispatched / Received Qty</Label>
              <Input
                type="number"
                value={qty}
                onChange={(e) => setQty(parseFloat(e.target.value) || 0)}
                className="h-8 text-xs font-mono font-bold bg-white"
              />
            </div>
          </div>

          {(stage === "ex_works" || stage === "in_transit") && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
              <div>
                <Label className="text-xs text-gray-600">Bill of Lading (BL) / Air Waybill (AWB) #</Label>
                <Input
                  value={blAwb}
                  onChange={(e) => setBlAwb(e.target.value)}
                  placeholder="e.g. AWB-9842512"
                  className="h-8 text-xs font-mono bg-white"
                />
              </div>
              <div>
                <Label className="text-xs text-gray-600">Freight Carrier / Logistics Provider</Label>
                <Input
                  value={carrier}
                  onChange={(e) => setCarrier(e.target.value)}
                  placeholder="e.g. DHL Global / Maersk"
                  className="h-8 text-xs bg-white"
                />
              </div>
            </div>
          )}

          {stage === "mrv_delivered" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
              <div>
                <Label className="text-xs text-gray-600">Material Receiving Voucher (MRV) # *</Label>
                <Input
                  value={mrvNo}
                  onChange={(e) => setMrvNo(e.target.value)}
                  placeholder="e.g. MRV-2026-089"
                  className="h-8 text-xs font-mono font-bold bg-white text-emerald-800"
                />
              </div>
              <div>
                <Label className="text-xs text-gray-600">OS&amp;D (Over, Short &amp; Damage) Inspection Notes</Label>
                <Input
                  value={osdNotes}
                  onChange={(e) => setOsdNotes(e.target.value)}
                  placeholder="Clean receipt / no damage"
                  className="h-8 text-xs bg-white"
                />
              </div>
              <div className="md:col-span-2">
                <Label className="text-xs text-gray-600">Stores Stamped Delivery Note Ref (Optional)</Label>
                <Input
                  value={stampedDnRef}
                  onChange={(e) => setStampedDnRef(e.target.value)}
                  placeholder="e.g. DN-SIGNED-2026-089.pdf"
                  className="h-8 text-xs bg-white font-mono"
                />
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleUpdateStage}
            disabled={submitting}
            className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold"
          >
            {submitting ? "Updating..." : "Commit Logistics Stage & Update Matrix"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


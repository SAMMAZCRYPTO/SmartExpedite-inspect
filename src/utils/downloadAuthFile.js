import { toast } from "sonner";

/**
 * Downloads a protected backend binary export (.xlsx, .docx, .pdf) using window.fetch
 * so authFetch attaches the Bearer token cleanly before triggering browser save.
 */
export async function downloadAuthFile(url, filename) {
  try {
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      toast.error(err.detail || "Failed to export file");
      return;
    }
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objUrl);
  } catch (e) {
    toast.error("File download failed");
  }
}

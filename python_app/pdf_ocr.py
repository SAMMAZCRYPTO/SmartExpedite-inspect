"""
Hybrid PDF Text + OCR Extraction Module for InspectFlow & SmartExpedit
=====================================================================
Combines PyMuPDF (`pymupdf`) native text/coordinate extraction with batch
Windows WinRT OCR (`Windows.Media.Ocr.OcrEngine`) — and optional RapidOCR /
Tesseract fallbacks — so scanned, image-based, or hybrid PDFs work seamlessly
across ALL SmartExpedit & Vendor Portal tabs (Schedules, PO Acknowledgements,
VDRL/SDRL Document Registers, Procurement Plans, and Progress Reports).
"""

import json
import math
import os
import re
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf


_WINRT_MAX_DIM = 2500

_PS_BATCH_OCR_SCRIPT = r"""
param([string]$ManifestPath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await([object]$WinRtTask, [Type]$ResultType) {
    $netTask = $asTaskGeneric.MakeGenericMethod($ResultType).Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) {
    throw "Windows OCR Engine is unavailable for user profile languages."
}

$files = Get-Content -Path $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($files -is [string]) { $files = @($files) }

$results = @()
foreach ($f in $files) {
    $sf = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($f)) ([Windows.Storage.StorageFile])
    $st = Await ($sf.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($st)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
        $words = @()
        foreach ($ln in $res.Lines) {
            foreach ($w in $ln.Words) {
                $r = $w.BoundingRect
                $words += @{
                    s = $w.Text
                    x = [math]::Round([double]$r.X, 2)
                    y = [math]::Round([double]$r.Y, 2)
                    h = [math]::Round([double]$r.Height, 2)
                }
            }
        }
        $results += @{
            file = $f
            text = $res.Text
            words = $words
        }
    } finally {
        $st.Dispose()
    }
}

@{ pages = $results } | ConvertTo-Json -Depth 6 -Compress
"""


def _group_words_into_lines(
    words: List[Dict[str, Any]], page_num: int
) -> List[Dict[str, Any]]:
    """
    Reconstruct horizontal table/prose lines from positioned word tokens `(x, y, s)`
    in the exact shape expected by SmartExpedit's `ffPdfGrids()` & `ffSchedRows()`.
    """
    clean = [w for w in words if str(w.get("s") or "").strip()]
    if not clean:
        return []

    heights = [float(w.get("h") or 10.0) for w in clean if float(w.get("h") or 0) > 1]
    med_h = statistics.median(heights) if heights else 10.0
    y_tol = max(4.0, med_h * 0.58)

    # Sort top-to-bottom by vertical center, then left-to-right
    for w in clean:
        w["_cy"] = float(w["y"]) + float(w.get("h") or med_h) * 0.5
    clean.sort(key=lambda w: (w["_cy"], float(w["x"])))

    rows: List[List[Dict[str, Any]]] = []
    row_cys: List[float] = []
    for w in clean:
        cy = w["_cy"]
        placed = False
        # Compare against the active row(s) near the bottom of rows
        for idx in range(len(rows) - 1, max(-1, len(rows) - 4), -1):
            if abs(cy - row_cys[idx]) <= y_tol:
                rows[idx].append(w)
                row_cys[idx] = sum(item["_cy"] for item in rows[idx]) / len(rows[idx])
                placed = True
                break
        if not placed:
            rows.append([w])
            row_cys.append(cy)

    # Sort rows top-to-bottom, words within each row left-to-right
    paired = sorted(zip(row_cys, rows), key=lambda pr: pr[0])
    lines_out: List[Dict[str, Any]] = []
    for row_cy, row_words in paired:
        row_words.sort(key=lambda w: float(w["x"]))
        items = [
            {
                "s": str(w["s"]).strip(),
                "x": round(float(w["x"]), 1),
                "y": round(float(w["y"]), 1),
            }
            for w in row_words
        ]
        txt = " ".join(it["s"] for it in items)
        lines_out.append(
            {
                "t": txt,
                "items": items,
                "page": page_num,
                "y": round(-float(row_cy), 1),
            }
        )
    return lines_out


def _page_text_is_usable(words: List[Tuple[Any, ...]]) -> bool:
    """
    Returns True if native PDF embedded text words look genuine (vs scanned image
    or custom-encoded garbled font glyphs).
    """
    if len(words) < 4:
        return False
    joined = " ".join(str(w[4] or "") for w in words)
    non_ws = re.sub(r"\s+", "", joined)
    if len(non_ws) < 20:
        return False
    # Reject replacement/private-use/garbled glyph dumps
    alnum = re.findall(r"[A-Za-z0-9]", non_ws)
    words_alpha = re.findall(r"[A-Za-z]{2,}", joined)
    if len(alnum) / max(1, len(non_ws)) < 0.45:
        return False
    if len(words_alpha) < 3:
        return False
    return True


def detect_ocr_engine() -> str:
    """Return the active OCR engine identifier on this host."""
    if os.name == "nt":
        return "winrt-ocr"
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return "rapidocr"
    except Exception:
        pass
    try:
        import pytesseract  # noqa: F401
        return "tesseract"
    except Exception:
        return "none"


def _run_winrt_batch_ocr(png_entries: List[Tuple[int, str, float]]) -> Tuple[Dict[int, List[Dict[str, Any]]], str]:
    """
    Runs Windows built-in WinRT OCR in a single PowerShell batch across all
    scanned page PNGs. Returns `(page_num -> scaled_words, engine_name)`.
    """
    if not png_entries:
        return {}, "winrt-ocr"

    manifest = [entry[1] for entry in png_entries]
    with tempfile.TemporaryDirectory() as td:
        manifest_path = os.path.join(td, "manifest.json")
        ps_path = os.path.join(td, "batch_ocr.ps1")
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf)
        with open(ps_path, "w", encoding="utf-8") as pf:
            pf.write(_PS_BATCH_OCR_SCRIPT)

        raw = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps_path,
                manifest_path,
            ],
            text=True,
            encoding="utf-8",
            timeout=120,
        )
    parsed = json.loads(raw or "{}")
    page_results = parsed.get("pages") or []
    by_file = {str(p.get("file") or ""): p for p in page_results}

    out: Dict[int, List[Dict[str, Any]]] = {}
    for page_num, fpath, zoom in png_entries:
        p_res = by_file.get(fpath) or {}
        raw_words = p_res.get("words") or []
        scaled = []
        inv_zoom = 1.0 / zoom if zoom else 1.0
        for w in raw_words:
            s_txt = str(w.get("s") or "").strip()
            if not s_txt:
                continue
            scaled.append(
                {
                    "s": s_txt,
                    "x": float(w.get("x") or 0.0) * inv_zoom,
                    "y": float(w.get("y") or 0.0) * inv_zoom,
                    "h": max(6.0, float(w.get("h") or 14.0) * inv_zoom),
                }
            )
        out[page_num] = scaled
    return out, "winrt-ocr"


def _run_fallback_ocr(png_entries: List[Tuple[int, str, float]]) -> Tuple[Dict[int, List[Dict[str, Any]]], str]:
    """
    Optional non-Windows fallback (`rapidocr_onnxruntime` or `pytesseract` if installed).
    """
    try:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()
        out: Dict[int, List[Dict[str, Any]]] = {}
        for page_num, fpath, zoom in png_entries:
            res, _ = engine(fpath)
            inv = 1.0 / zoom if zoom else 1.0
            words = []
            for box, text, _score in res or []:
                if not text or not str(text).strip():
                    continue
                xs = [pt[0] for pt in box]
                ys = [pt[1] for pt in box]
                words.append(
                    {
                        "s": str(text).strip(),
                        "x": min(xs) * inv,
                        "y": min(ys) * inv,
                        "h": max(6.0, (max(ys) - min(ys)) * inv),
                    }
                )
            out[page_num] = words
        return out, "rapidocr"
    except Exception:
        pass

    try:
        import pytesseract
        from PIL import Image

        out = {}
        for page_num, fpath, zoom in png_entries:
            data = pytesseract.image_to_data(
                Image.open(fpath), output_type=pytesseract.Output.DICT
            )
            inv = 1.0 / zoom if zoom else 1.0
            words = []
            for i, txt in enumerate(data.get("text") or []):
                if not txt or not str(txt).strip():
                    continue
                words.append(
                    {
                        "s": str(txt).strip(),
                        "x": float(data["left"][i]) * inv,
                        "y": float(data["top"][i]) * inv,
                        "h": max(6.0, float(data["height"][i]) * inv),
                    }
                )
            out[page_num] = words
        return out, "tesseract"
    except Exception as exc:
        raise RuntimeError(f"No OCR engine succeeded: {exc}")


def extract_pdf_with_ocr(
    pdf_bytes: bytes, max_pages: int = 80, force_ocr: bool = False
) -> Dict[str, Any]:
    """
    Hybrid PDF extraction: reads native text words per page with PyMuPDF and
    runs high-DPI OCR automatically on any scanned / image-only / garbled page.
    Returns structured `lines` (with `(x, y)` word coordinates) + concatenated `text`.
    """
    if not pdf_bytes:
        return {
            "ok": False,
            "error": "Empty PDF payload",
            "pages": 0,
            "ocr_pages": [],
            "ocr_used": False,
            "readable": False,
            "text": "",
            "lines": [],
        }

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    limit = min(total_pages, max(1, int(max_pages)))

    page_lines_map: Dict[int, List[Dict[str, Any]]] = {}
    pages_needing_ocr: List[int] = []

    for idx in range(limit):
        p_num = idx + 1
        page = doc[idx]
        native_words = page.get_text("words") or []
        if not force_ocr and _page_text_is_usable(native_words):
            formatted = [
                {
                    "s": str(w[4]).strip(),
                    "x": float(w[0]),
                    "y": float(w[1]),
                    "h": max(6.0, float(w[3]) - float(w[1])),
                }
                for w in native_words
                if str(w[4] or "").strip()
            ]
            page_lines_map[p_num] = _group_words_into_lines(formatted, p_num)
        else:
            pages_needing_ocr.append(p_num)

    engine_used = "pymupdf-native"
    if pages_needing_ocr:
        with tempfile.TemporaryDirectory() as tmp_dir:
            png_entries: List[Tuple[int, str, float]] = []
            for p_num in pages_needing_ocr:
                page = doc[p_num - 1]
                rect = page.rect
                max_pt = max(1.0, float(rect.width), float(rect.height))
                # Render around ~220 DPI (zoom ~3.05), clamped to <= 2500px so WinRT never rejects wide drawings
                zoom = min(3.0, _WINRT_MAX_DIM / max_pt)
                zoom = max(1.0, zoom)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                img_path = os.path.join(tmp_dir, f"page_{p_num}.png")
                pix.save(img_path)
                png_entries.append((p_num, img_path, zoom))

            ocr_words_by_page: Dict[int, List[Dict[str, Any]]] = {}
            if os.name == "nt":
                try:
                    ocr_words_by_page, engine_used = _run_winrt_batch_ocr(png_entries)
                except Exception:
                    ocr_words_by_page, engine_used = _run_fallback_ocr(png_entries)
            else:
                ocr_words_by_page, engine_used = _run_fallback_ocr(png_entries)

            for p_num in pages_needing_ocr:
                w_list = ocr_words_by_page.get(p_num) or []
                page_lines_map[p_num] = _group_words_into_lines(w_list, p_num)

    all_lines: List[Dict[str, Any]] = []
    for p_num in range(1, limit + 1):
        all_lines.extend(page_lines_map.get(p_num) or [])

    full_text = "\n".join(l["t"] for l in all_lines if l.get("t"))
    return {
        "ok": True,
        "pages": total_pages,
        "processed_pages": limit,
        "ocr_pages": pages_needing_ocr,
        "ocr_used": len(pages_needing_ocr) > 0,
        "engine": engine_used,
        "readable": len(full_text.strip()) > 20,
        "text": full_text,
        "lines": all_lines,
    }

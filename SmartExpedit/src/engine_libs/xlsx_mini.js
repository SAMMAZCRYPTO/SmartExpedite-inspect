// ============================================================================
// Compact, dependency-free XLSX writer (hand-built ZIP + OOXML, no external
// libraries) -- used by enquiry_detail.html's "Export To Excel" on the
// Enquiry Details tab. Deliberately smaller/simpler than the full writer in
// mr_analysis_enquiry.html (title + header + plain banded rows only), since
// this just needs to dump the BOM grid, not the MR-PO analysis styling.
// ============================================================================

const MINI_CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    table[n] = c >>> 0;
  }
  return table;
})();
function miniCrc32(bytes) {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) crc = MINI_CRC_TABLE[(crc ^ bytes[i]) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}
function miniU16(n) { return new Uint8Array([n & 0xFF, (n >> 8) & 0xFF]); }
function miniU32(n) { return new Uint8Array([n & 0xFF, (n >> 8) & 0xFF, (n >> 16) & 0xFF, (n >>> 24) & 0xFF]); }
function miniConcat(arrays) {
  let total = 0;
  for (const a of arrays) total += a.length;
  const out = new Uint8Array(total);
  let pos = 0;
  for (const a of arrays) { out.set(a, pos); pos += a.length; }
  return out;
}
function miniBuildZip(files) {
  const enc = new TextEncoder();
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  for (const f of files) {
    const nameBytes = enc.encode(f.name);
    const data = f.data;
    const crc = miniCrc32(data);
    const size = data.length;
    const localHeader = miniConcat([
      miniU32(0x04034b50), miniU16(20), miniU16(0), miniU16(0), miniU16(0), miniU16(0),
      miniU32(crc), miniU32(size), miniU32(size), miniU16(nameBytes.length), miniU16(0),
    ]);
    const localEntry = miniConcat([localHeader, nameBytes, data]);
    localParts.push(localEntry);
    const centralHeader = miniConcat([
      miniU32(0x02014b50), miniU16(20), miniU16(20), miniU16(0), miniU16(0), miniU16(0), miniU16(0),
      miniU32(crc), miniU32(size), miniU32(size), miniU16(nameBytes.length), miniU16(0), miniU16(0), miniU16(0), miniU16(0),
      miniU32(0), miniU32(offset),
    ]);
    centralParts.push(miniConcat([centralHeader, nameBytes]));
    offset += localEntry.length;
  }
  const centralDir = miniConcat(centralParts);
  const centralDirOffset = offset;
  const eocd = miniConcat([
    miniU32(0x06054b50), miniU16(0), miniU16(0), miniU16(files.length), miniU16(files.length),
    miniU32(centralDir.length), miniU32(centralDirOffset), miniU16(0),
  ]);
  return miniConcat([...localParts, centralDir, eocd]);
}
function miniXesc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function miniColLetter(idx) {
  let s = '';
  idx += 1;
  while (idx > 0) {
    const rem = (idx - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    idx = Math.floor((idx - 1) / 26);
  }
  return s;
}

// Same palette as the rest of the suite's exports (mr_analysis_enquiry.html's writer):
// title = dark slate bold text on light-slate fill (F1F5F9); header = white bold on blue
// (1F6FB0); rows band light-blue (DCE9F5) / white (FFFFFF), including numeric cells.
function miniStylesXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.##"/></numFmts>
<fonts count="6">
<font><sz val="11"/><color rgb="FF000000"/><name val="Calibri"/></font>
<font><sz val="13"/><color rgb="FF1E293B"/><name val="Calibri"/><b/></font>
<font><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><b/></font>
<font><sz val="11"/><color rgb="FF166534"/><name val="Calibri"/><b/></font>
<font><sz val="11"/><color rgb="FFB91C1C"/><name val="Calibri"/></font>
<font><sz val="11"/><color rgb="FF94A3B8"/><name val="Calibri"/></font>
</fonts>
<fills count="9">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F6FB0"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDCE9F5"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFFFFF"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFEF2F2"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF8FAFC"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFECFDF5"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD9D9D9"/></left><right style="thin"><color rgb="FFD9D9D9"/></right><top style="thin"><color rgb="FFD9D9D9"/></top><bottom style="thin"><color rgb="FFD9D9D9"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="14">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="1" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="164" fontId="0" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="0" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="164" fontId="3" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="4" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="164" fontId="4" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="5" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="164" fontId="5" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="1" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;
}

// spec = { sheetName, title, columns:[{header,width,numFmt?}], rows: [[cellVal,...], ...] }
// numFmt:'num' on a column renders that cell as a real number with #,##0.## formatting.
function miniBuildSheetXml(spec) {
  const numCols = spec.columns.length;
  const lastCol = miniColLetter(numCols - 1);
  let rowNum = 1;
  const xmlRows = [];

  xmlRows.push(`<row r="${rowNum}" ht="22"><c r="A${rowNum}" s="1" t="inlineStr"><is><t>${miniXesc(spec.title)}</t></is></c>${
    Array.from({length: numCols - 1}, (_, i) => `<c r="${miniColLetter(i+1)}${rowNum}" s="1"/>`).join('')
  }</row>`);
  rowNum++;

  const headerRowNum = rowNum;
  xmlRows.push(`<row r="${rowNum}" ht="20">${spec.columns.map((c, i) =>
    `<c r="${miniColLetter(i)}${rowNum}" s="2" t="inlineStr"><is><t>${miniXesc(c.header)}</t></is></c>`
  ).join('')}</row>`);
  rowNum++;

  /* Optional per-cell tint so an exported sheet reads the way the screen does.
     spec.marks is a map "<rowIndex>:<colIndex>" -> 'win' | 'bad' | 'mute' | 'total',
     and spec.rowMarks a map "<rowIndex>" -> the same, applied to the whole row. */
  const MARK_TEXT = { win:'7', bad:'9', mute:'11', total:'3' };
  const MARK_NUM  = { win:'8', bad:'10', mute:'12', total:'13' };
  const marks = spec.marks || {};
  const rowMarks = spec.rowMarks || {};

  spec.rows.forEach((row, rIdx) => {
    const bandStyle = rIdx % 2 === 0 ? '3' : '4';
    const rowMark = rowMarks[rIdx];
    const cellsXml = row.map((val, cIdx) => {
      const ref = `${miniColLetter(cIdx)}${rowNum}`;
      const isNum = spec.columns[cIdx].numFmt === 'num';
      const mark = marks[rIdx + ':' + cIdx] || rowMark;
      if (isNum) {
        const numStyle = (mark && MARK_NUM[mark]) || (bandStyle === '3' ? '5' : '6');
        /* a blank in a numeric column is a BLANK, not a zero — a totals row that
           reads 0 under "Item #" is worse than no cell at all */
        if (val === '' || val === null || val === undefined)
          return `<c r="${ref}" s="${numStyle}"/>`;
        if (typeof val !== 'number' || !isFinite(val))
          return `<c r="${ref}" s="${(mark && MARK_TEXT[mark]) || bandStyle}" t="inlineStr"><is><t>${miniXesc(val)}</t></is></c>`;
        return `<c r="${ref}" s="${numStyle}"><v>${val}</v></c>`;
      }
      const txtStyle = (mark && MARK_TEXT[mark]) || bandStyle;
      return `<c r="${ref}" s="${txtStyle}" t="inlineStr"><is><t>${miniXesc(val == null ? '' : val)}</t></is></c>`;
    }).join('');
    xmlRows.push(`<row r="${rowNum}" ht="18">${cellsXml}</row>`);
    rowNum++;
  });

  const lastRow = rowNum - 1;
  const colsXml = `<cols>${spec.columns.map((c, i) => `<col min="${i+1}" max="${i+1}" width="${c.width || 16}" customWidth="1"/>`).join('')}</cols>`;

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:${lastCol}${lastRow}"/>
<sheetViews><sheetView showGridLines="0" tabSelected="1" workbookViewId="0"><pane ySplit="${headerRowNum}" topLeftCell="A${headerRowNum+1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
${colsXml}
<sheetData>${xmlRows.join('')}</sheetData>
<autoFilter ref="A${headerRowNum}:${lastCol}${lastRow}"/>
<mergeCells count="1"><mergeCell ref="A1:${lastCol}1"/></mergeCells>
</worksheet>`;
}

function miniAssembleXlsx(sheetName, sheetXml, stylesXmlStr) {
  const enc = new TextEncoder();
  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>`;
  const rootRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`;
  const workbookXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="${miniXesc(sheetName || 'Sheet1')}" sheetId="1" r:id="rId1"/></sheets>
</workbook>`;
  const workbookRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`;
  const files = [
    { name: '[Content_Types].xml', data: enc.encode(contentTypes) },
    { name: '_rels/.rels', data: enc.encode(rootRels) },
    { name: 'xl/workbook.xml', data: enc.encode(workbookXml) },
    { name: 'xl/_rels/workbook.xml.rels', data: enc.encode(workbookRels) },
    { name: 'xl/styles.xml', data: enc.encode(stylesXmlStr) },
    { name: 'xl/worksheets/sheet1.xml', data: enc.encode(sheetXml) },
  ];
  return miniBuildZip(files);
}

function miniBuildXlsx(spec) {
  const sheetXml = miniBuildSheetXml(spec);
  const stylesXmlStr = miniStylesXml();
  return miniAssembleXlsx(spec.sheetName, sheetXml, stylesXmlStr);
}

function downloadMiniXlsx(bytes, filename) {
  const blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Enquiry Details BOM export -- what's shown in that tab: Item/Vocab/Description/Unit/
// Previous Qty/Current Qty/Weight/Prev. PO Supplier, same shape as ENQ_ITEMS rows
// ([itemno, vocab, desc, unit, prev, curr, weight, sup]).
function buildEnquiryDetailsXlsx({ enquiryRef, materialHead, revision, items }) {
  const columns = [
    { header: 'Item No', width: 10 },
    { header: 'Vocab', width: 16 },
    { header: 'Material Description', width: 60 },
    { header: 'Unit', width: 8 },
    { header: 'Previous Qty', width: 13, numFmt: 'num' },
    { header: 'Current Qty', width: 13, numFmt: 'num' },
    { header: 'Weight (MT)', width: 12, numFmt: 'num' },
    { header: 'Prev. PO Supplier', width: 40 },
  ];
  const rows = items.map(it => {
    const [itemno, vocab, desc, unit, prev, curr, weight, sup] = it;
    return [itemno, vocab || '', desc || '', unit || '', prev, curr, weight, sup ? sup.split('/').join(', ') : 'New Item'];
  });
  return miniBuildXlsx({
    sheetName: 'Enquiry Details',
    title: `Enquiry ${enquiryRef} (Rev ${revision}) — ${materialHead} — Enquiry Details`,
    columns,
    rows,
  });
}

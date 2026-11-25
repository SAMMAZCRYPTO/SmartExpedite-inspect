import re,json,sys,openpyxl,warnings
warnings.filterwarnings('ignore')
import os
HERE=os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
EP='engine_libs'
src=open(f'{EP}/expediting_detail.html',encoding='utf8').read()
css=re.search(r'<style>(.*?)</style>',src,re.S).group(1)
markup=src[src.index('<div class="ep-portal"'):src.index('<script src="ep_items_data.js">')]
cut=markup.index('<!-- generic modal shell -->');overlays=markup[cut:];markup=markup[:cut]
main=re.findall(r'<script>(.*?)</script>',src,re.S)[-1]
main=main[:main.index("PO = qs('po');")]
for a,b in {'#0d9488':'#f59e0b','#0f766e':'#b45309','#f0fdfa':'#fffbeb','#ccfbf1':'#fef3c7','#99f6e4':'#fde68a','#14b8a6':'#f59e0b','#5eead4':'#fcd34d','#115e59':'#92400e','#134e4a':'#78350f'}.items():
    css=css.replace(a,b).replace(a.upper(),b);main=main.replace(a,b)
wf=openpyxl.load_workbook('data/Expediting_workflow.xlsx').worksheets[0]
WF=[[wf[f'B{r}'].value,wf[f'C{r}'].value,wf[f'D{r}'].value,wf[f'E{r}'].value=='Yes'] for r in range(4,39)]
recs=open('data/records_raw.json',encoding='utf8').read()
plan=json.load(open('data/plan_rows.json'))
vend=[['2820-2025-74259-A','Rollstud Middle East'],['2820-2025-74462-AC','Petronash FZE']]
libs=['ep_items_data.js','ep_mr_data.js','ep_sdrl_master.js','ep_expediting_data.js','xlsx_mini.js','ep_xlsx_read.js','ep_mr_reader.js','ep_mr_74259.js','ep_exp_work.js','ep_pdf_lib.js','ep_mr_aramco.js']
js=lambda s:s.replace('</script','<\\/script')
shell=open('shell.js',encoding='utf8').read()
EXTRA='''
.ep-btn.primary{color:#1e293b}.ep-btn.primary:hover{background:#fbbf24}
.ep-toolbar,#rail-wrap,#portal-band{display:none!important}
html,body{height:100%;overflow-x:clip}body{background:#f1f5f9;font-family:"IBM Plex Sans",system-ui,"Segoe UI",sans-serif;color:#1e293b}
#sx{display:flex;min-height:100%}.sx-side{width:224px;flex:none;background:#0f172a;color:#cbd5e1;display:flex;flex-direction:column;padding-block:14px;position:sticky;top:0;height:100vh}
.sx-logo{display:flex;gap:10px;align-items:center;padding:0 16px 14px;color:#fff;font-weight:700;font-size:16px}.sx-tile{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,#f59e0b,#ea580c);display:grid;place-items:center;font:700 13px "IBM Plex Mono",monospace;color:#fff}
.sx-n{background:none;border:0;color:inherit;text-align:left;padding:10px 16px;cursor:pointer;width:100%;font:inherit;font-size:14px}.sx-n:hover{background:#1e293b}.sx-n.on{background:#1e293b;color:#fff;box-shadow:inset 3px 0 #f59e0b}
.sx-vh{padding:10px 16px;color:#fff;font-weight:600;box-shadow:inset 3px 0 #f59e0b;background:#1e293b}.sx-foot{margin-top:auto;padding:12px 16px 0;font-size:12px;color:#94a3b8}.sx-foot b{display:block;color:#fbbf24;margin-bottom:3px}.sx-foot button{background:none;border:0;color:#fbbf24;padding:0;cursor:pointer;text-decoration:underline;font:inherit}
.sx-main{flex:1;min-width:0;max-width:100%;overflow-x:clip}#wk{min-width:0}.ep-tabs{overflow-x:auto}.sx-top{background:#fff;border-bottom:1px solid #e2e8f0;padding-block:10px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:flex;gap:12px;align-items:center;flex-wrap:wrap;position:sticky;top:env(safe-area-inset-top,0px);z-index:5}.sx-top h1{flex:1;font-size:20px;margin:0;min-width:150px}.sx-top select{width:auto}
#sx-page{padding-block:16px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
#sx-pos{display:flex;gap:6px;align-items:center}#sx-pos select{max-width:210px}.sx-pop{position:absolute;right:16px;top:50px;width:min(340px,86vw);background:#fff;border:1px solid #e2e8f0;border-radius:10px;box-shadow:0 8px 24px rgba(15,23,42,.18);max-height:340px;overflow:auto;z-index:9}.sx-al{display:block;width:100%;border:0;background:#fffbeb;border-bottom:1px solid #e2e8f0;text-align:left;padding:8px 10px;cursor:pointer;font:inherit;font-size:12px}
.link{background:none;border:0;color:#b45309;cursor:pointer;padding:0;font:inherit;font-weight:600;text-align:left;text-decoration:underline}.sx-aging{font-size:12.5px;margin-left:8px}
.sx-plan td{vertical-align:top}.sx-c{width:100%;border:1px solid #e2e8f0;border-radius:5px;padding:4px 6px;font:inherit;font-size:12px;background:#fff;color:#1e293b;min-width:60px}textarea.sx-c{min-height:44px}.sx-calc{background:#f8fafc}.sx-mn .sx-c{background:#fef3c7;border-left:3px solid #d97706}.sx-mv .sx-c{background:#dbeafe;border-left:3px solid #1d4ed8}.ep-mk-n{background:#fef3c7!important;color:#92400e!important}.ep-mk-v{background:#dbeafe!important;color:#1d4ed8!important}.sx-del td{text-decoration:line-through;opacity:.55}
.sx-pk-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}.sx-pk{display:block;cursor:pointer}.sx-pk input{position:absolute;opacity:0;pointer-events:none}.sx-pk-c{display:flex;gap:10px;align-items:center;border:1px solid #e2e8f0;border-radius:10px;padding:10px;background:#fff;transition:border-color .15s,box-shadow .15s}.sx-pk:hover .sx-pk-c{border-color:#fcd34d}.sx-pk input:checked+.sx-pk-c{border-color:#f59e0b;box-shadow:0 0 0 3px #fef3c7;background:#fffbeb}.sx-pk input:focus-visible+.sx-pk-c{outline:2px solid #b45309;outline-offset:1px}.sx-pk-a{width:38px;height:38px;flex:none;border-radius:50%;background:#1e293b;color:#fbbf24;display:grid;place-items:center;font:600 13px "IBM Plex Mono",monospace}.sx-pk-b{flex:1;min-width:0;display:grid;gap:3px}.sx-pk-n{font-weight:600}.sx-pk-m{font-size:12px;color:#64748b}.sx-pk-bar{height:6px;background:#f1f5f9;border-radius:3px;overflow:hidden}.sx-pk-bar i{display:block;height:100%}.sx-pk-po{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px;font-size:13px}
@media print{.sx-side,.sx-top{display:none}}
.sx-conn{border-left:4px solid #f59e0b}.sx-ul{margin:4px 0 0;padding-left:18px}.sx-chk{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:6px}.sx-chk label,.sx-li{display:flex;gap:6px;align-items:center}.sx-li{padding:3px 0}.sx-chk input,.sx-li input{width:auto}
.sx-ag-h{background:#1e293b;color:#fff;border-radius:8px;padding:12px 14px;display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.sx-bar{margin:8px 0}.sx-bar .t{height:7px;background:#e2e8f0;border-radius:4px;overflow:hidden;margin-top:3px}.sx-bar i{display:block;height:100%;background:#f59e0b}
.sx-tl{display:grid;gap:8px;margin-top:6px}.sx-ts{display:flex;gap:10px;color:#94a3b8}.sx-ts i{width:22px;height:22px;flex:none;border-radius:50%;background:#e2e8f0;display:grid;place-items:center;font:600 11px "IBM Plex Mono",monospace;color:#64748b}.sx-ts span{display:block;font-size:11.5px}.sx-ts.done,.sx-ts.now{color:#1e293b}.sx-ts.done i{background:#059669;color:#fff}.sx-ts.now i{background:#f59e0b;color:#1e293b}
:focus-visible{outline:2px solid #b45309;outline-offset:1px}
@media(max-width:760px){#sx{flex-direction:column}.sx-side{width:100%;height:auto;position:static;flex-direction:row;overflow-x:auto;padding:6px}.sx-logo{padding:0 8px}.sx-logo span:last-child,.sx-foot{display:none}.sx-n{width:auto;white-space:nowrap}.ep-kpis{grid-template-columns:1fr 1fr!important}.ep-fields{grid-template-columns:1fr!important}}
'''
for ed in ['after']:
    label='SmartExpedit Before' if ed=='before' else 'SmartExpedit After'
    h=f'''<title>{label}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>{css}{EXTRA}</style>
<div id="sx"><aside class="sx-side"><div class="sx-logo"><span class="sx-tile">SE</span><span>SmartExpedit</span></div><nav id="sx-nav"></nav><div class="sx-foot"><b id="sx-ed"></b>Sample and MODELLED data. Changes stay in this browser.</div></aside>
<div class="sx-main"><header class="sx-top"><h1 id="sx-h"></h1><span id="sx-pos"></span><label class="ep-sub" for="sx-role">Viewing as</label><select id="sx-role" class="ep-in"></select><button class="ep-btn secondary" id="sx-alert" data-s="alert">Alerts</button><button class="ep-btn secondary" data-s="reset" title="Put the demo back to its sample data">Reset demo</button><div class="sx-pop" id="sx-pop" hidden></div></header>
<div id="sx-page"></div><div id="wk">{markup}</div></div></div>{overlays}<input type="file" id="sx-file" accept=".xlsx" hidden>
'''
    for l in libs:
        h+='<script>'+js(open(l if l=='ep_mr_aramco.js' else f'{EP}/{l}',encoding='utf8').read())+'</script>\n'
    h+='<script>'+js(main)+'</script>\n'
    h+='<script>window.SX_EDITION='+json.dumps(ed)+';window.SX_RECORDS='+js(json.dumps(recs))+';window.SX_PLAN='+js(json.dumps(plan))+';window.SX_WF='+js(json.dumps(WF))+';window.SX_VENDORS='+json.dumps(json.dumps(vend))+';</script>\n'
    h+='<script>'+js(shell)+'</script>\n'
    h+='<script>window.SX_FIELD='+js(open('data/field.json',encoding='utf8').read())+';</script>\n<script>'+js(open('fix2.js',encoding='utf8').read())+'</script>\n'+'<script>'+js(open('fx3.js',encoding='utf8').read())+'</script>\n'
    open('../index.html','w',encoding='utf8').write(h)
    import os
    os.makedirs('../server/static', exist_ok=True)
    open('../server/static/index.html','w',encoding='utf8').write(h)
    print(ed,round(len(h)/1e6,2),'MB')

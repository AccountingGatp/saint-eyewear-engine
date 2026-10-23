"""Portable, explicitly DRAFT Word outputs. Original-template issuance is disabled.
Native chart caches keep values editable/readable without a linked workbook.
These documents are NOT replacements for the missing SOP reference templates.
"""
import base64, io, zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape
from .core import ValidationError, dec, fmt

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
C='http://schemas.openxmlformats.org/drawingml/2006/chart'
WP='http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
KINDS={'financial':'Month-End Financial Report','deepview':'Saint Eyewear Expense Analysis Deepview','quick':'Saint Eyewear Expense Quick View','exceptions':'Exceptions'}

def text(v):return escape(str(v if v is not None else ''))
def para(v,bold=False,size=21,color='000000',keep=False):
 return f'<w:p><w:pPr><w:spacing w:after="110"/>{"<w:keepNext/>" if keep else ""}</w:pPr><w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="{size}"/><w:color w:val="{color}"/>{"<w:b/>" if bold else ""}</w:rPr><w:t xml:space="preserve">{text(v)}</w:t></w:r></w:p>'
def heading(v):return para(v,True,27,'1F3A5F',True)
def money(v):
 if v is None or str(v).strip()=='':return ''
 try:
  n=dec(v);return ('('+f'{abs(n):,.2f}'+')') if n<0 else f'{n:,.2f}'
 except ValidationError:return str(v or '')
def table(headers,rows):
 widths=[max(900,int(9360/len(headers)))]*len(headers)
 if len(headers)==4:widths=[3900,1820,1820,1820]
 result='<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="85" w:type="dxa"/><w:bottom w:w="85" w:type="dxa"/><w:left w:w="95" w:type="dxa"/><w:right w:w="95" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'+''.join(f'<w:gridCol w:w="{x}"/>' for x in widths)+'</w:tblGrid>'
 for i,row in enumerate([headers]+rows):
  result+='<w:tr><w:trPr><w:cantSplit/>'+('<w:tblHeader/>' if i==0 else '')+'</w:trPr>'
  for j,v in enumerate(row):
   color='FFFFFF' if i==0 else '000000'
   try:
    if i>0 and dec(v)<0:color='9C0006'
   except ValidationError:pass
   value=money(v) if i>0 and j>0 else str(v if v is not None else '')
   fill='1F3A5F' if i==0 else ('F2F5F8' if i%2==1 else 'FFFFFF')
   result+=f'<w:tc><w:tcPr><w:tcW w:w="{widths[j]}" w:type="dxa"/><w:shd w:fill="{fill}"/><w:vAlign w:val="center"/></w:tcPr>'+para(value,i==0,19,color)+'</w:tc>'
  result+='</w:tr>'
 return result+'</w:tbl>'+para('')

def chart(categories,series,date_axis=False):
 """The series list is [(clean label, decimal values)]; no raw sheet legend names."""
 xml=f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><c:chartSpace xmlns:c="{C}" xmlns:a="{A}"><c:lang val="en-AU"/><c:chart><c:autoTitleDeleted val="1"/><c:plotArea><c:layout/><c:barChart><c:barDir val="col"/><c:grouping val="clustered"/>'
 for n,(name,vals) in enumerate(series):
  xml+=f'<c:ser><c:idx val="{n}"/><c:order val="{n}"/><c:tx><c:strRef><c:f>Series{n+1}</c:f><c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>{text(name)}</c:v></c:pt></c:strCache></c:strRef></c:tx>'
  xml+='<c:spPr><a:solidFill><a:srgbClr val="'+['1F3A5F','7391AD','B5C8D9'][n%3]+'"/></a:solidFill><a:ln><a:noFill/></a:ln></c:spPr>'
  if date_axis:
   dates=[str((date.fromisoformat(str(x))-date(1899,12,30)).days) for x in categories]
   xml+='<c:cat><c:numRef><c:f>Dates</c:f><c:numCache><c:formatCode>dd mmm</c:formatCode>'+f'<c:ptCount val="{len(dates)}"/>'+''.join(f'<c:pt idx="{i}"><c:v>{x}</c:v></c:pt>' for i,x in enumerate(dates))+'</c:numCache></c:numRef></c:cat>'
  else:xml+='<c:cat><c:strRef><c:f>Categories</c:f><c:strCache>'+f'<c:ptCount val="{len(categories)}"/>'+''.join(f'<c:pt idx="{i}"><c:v>{text(x)}</c:v></c:pt>' for i,x in enumerate(categories))+'</c:strCache></c:strRef></c:cat>'
  xml+='<c:val><c:numRef><c:f>Values</c:f><c:numCache><c:formatCode>#,##0.00</c:formatCode>'+f'<c:ptCount val="{len(vals)}"/>'+''.join(f'<c:pt idx="{i}"><c:v>{dec(x)}</c:v></c:pt>' for i,x in enumerate(vals))+'</c:numCache></c:numRef></c:val></c:ser>'
 all_values=[dec(v) for _,vs in series for v in vs]
 axis_min=min([Decimal(0)]+all_values)
 axis='dateAx' if date_axis else 'catAx'
 xml+=f'<c:axId val="10"/><c:axId val="20"/></c:barChart><c:{axis}><c:axId val="10"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="b"/>'
 if date_axis:xml+='<c:numFmt formatCode="dd mmm" sourceLinked="0"/>'
 xml+=f'<c:crossAx val="20"/><c:crosses val="autoZero"/></c:{axis}><c:valAx><c:axId val="20"/><c:scaling><c:orientation val="minMax"/><c:min val="{axis_min}"/></c:scaling><c:axPos val="l"/><c:majorGridlines/><c:numFmt formatCode="#,##0" sourceLinked="0"/><c:crossAx val="10"/><c:crosses val="autoZero"/></c:valAx></c:plotArea><c:legend><c:legendPos val="b"/><c:layout/></c:legend><c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart></c:chartSpace>'
 return xml

def document(payload):
 kind=payload.get('kind')
 if kind not in KINDS:raise ValidationError('Unknown report type.')
 run=payload['run'];f=run['figures'];flags=f.get('flags',[]);notes=run.get('notes') or {}
 if any(x['severity']=='Block' for x in flags):raise ValidationError('Blocking validation failures prevent document generation.')
 missing=[x['rule'] for x in flags if x['severity']=='Review' and not str(notes.get(x['id'],'')).strip()]
 if missing:raise ValidationError('Reviewer explanations are required for: '+', '.join(missing))
 if not run.get('reviewed_by') or not run.get('reviewed_at'):raise ValidationError('Verified reviewer sign-off is required.')
 m=f['month'];mm=datetime.strptime(m,'%Y-%m').strftime('%B %Y');rev=' (revised)' if f.get('revised_months') else '';name=KINDS[kind]+' - '+mm+rev+' - DRAFT.docx'
 body=para('SAINT EYEWEAR PTY LTD',True,25,'1F3A5F')+para(KINDS[kind]+rev,True,34,'1F3A5F')+para(mm+' | AUD')
 body+=para('DRAFT - NOT APPROVED FOR CLIENT ISSUE',True,22,'9C0006')+para('Original templates and August/September acceptance comparisons have not been verified. This is an internal review output, not an issued client pack.')
 charts=[]
 def addchart(title,cats,series,dates=False):
  nonlocal body
  if not cats:return
  charts.append(chart(cats,series,dates));n=len(charts)
  body+=heading(title)+f'<w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="5943600" cy="2286000"/><wp:docPr id="{n}" name="Chart {n}"/><a:graphic><a:graphicData uri="{C}"><c:chart r:id="chart{n}"/></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'+para('Source: '+('General Ledger transaction detail only.' if 'Vendor' in title else 'DRS only.' if 'Daily' in title else 'Xero Profit and Loss.'))
 months=f['pnl']['display_months'];metrics=f['metrics'];current=metrics[m]
 if kind!='exceptions':
  body+=heading('Financial overview')+table(['Measure']+months,[[label]+[metrics[k].get(key) for k in months] for key,label in [('revenue','Revenue'),('cogs','Cost of goods sold'),('gross','Gross profit'),('marketing','Marketing'),('operating','Operating costs'),('other_income','Other income'),('net','Net profit'),('before_marketing','Profit before marketing')]])
  body+=para('Break-even marketing ratio: '+(f'{dec(current["break_even_pct"]):.2f}%' if current['break_even_pct'] is not None else 'Undefined because sales are zero.'))
  addchart('Revenue, gross profit and net profit',months,[(label,[metrics[k][key] for k in months]) for key,label in [('revenue','Revenue'),('gross','Gross profit'),('net','Net profit')]])
 if kind=='financial':
  for heading_text,key in [('Profit and Loss','pnl'),('Balance Sheet','bs')]:
   source=f[key];labels=list(dict.fromkeys(a for k in months for a in source['months'][k]))
   body+=heading(heading_text+' (AUD)')+table(['Account']+months,[[a]+[source['months'][k].get(a,0) for k in months] for a in labels])
  daily=f['drs']['daily'];addchart('Daily sales',[x['date'] for x in daily],[('DRS sales',[x['sales'] for x in daily])],True)
  for title,key in [('Productwise (DRS basis)','products'),('Countrywise (DRS basis)','countries')]:
   source=f['drs'][key];rows=source['rows'];width=len(source['total'])
   body+=heading(title)+table(['DRS column '+str(j+2) for j in range(width)],rows+[source['total']])
  body+=para('DRS product/country fields retain their exported order. The original reference template and verified column labels are required before client issue.')
 if kind=='deepview':
  addchart('Marketing and running costs',months,[(label,[metrics[k][key] for k in months]) for key,label in [('marketing','Marketing'),('operating','Operating costs')]])
  if f.get('bridge'):
   b=f['bridge'];keys=['revenue_at_prior_margin','margin','marketing','running_costs','other_income'];labels=['Revenue effect','Margin effect','Marketing','Running costs','Other income']
   addchart('Profit bridge contributions',labels,[('Profit movement',[b[k] for k in keys])]);body+=para('Revenue effect uses the previous gross margin. This is not a separately verified unit-volume effect. Other income is shown so the bridge reconciles to net profit.')
  vendors=sorted(f['vendors'].items(),key=lambda kv:abs(dec(kv[1])),reverse=True)[:15]
  body+=heading('Vendor detail - General Ledger only')+table(['Vendor','Amount (AUD)'],[[k,v] for k,v in vendors])
  addchart('Vendor spending',[k for k,v in vendors[:8]],[('GL detail',[v for k,v in vendors[:8]])])
  body+=para('Redo Tech identified transaction detail: A$'+money(f.get('redo_tech_detail',0))+'. This does not replace the Software Expense P&L total.')
 if kind=='exceptions':body+=para('INTERNAL ONLY - NEVER SEND THIS CHECKLIST TO THE CLIENT',True,22,'9C0006')
 body+=heading('Review explanations and open items')
 for flag in flags:
  note=notes.get(flag['id'])
  if kind!='exceptions' and flag['severity']=='Info':continue
  body+=para(f'{flag["rule"]} | {flag["severity"]}: {flag["message"]}',True)
  body+=para(note if note else 'Open item: '+flag['message'])
  if kind=='exceptions' and flag.get('figures'):body+=para(str(flag['figures']))
 body+=heading('Reviewer sign-off')+para('Reviewed by: '+run['reviewed_by'])+para('Review date: '+run['reviewed_at'])+para('Run: '+run['id'])+para('SOP acceptance status: not approved. Do not send to client.')
 body+='<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1000" w:right="1273" w:bottom="1000" w:left="1273"/></w:sectPr>'
 main=f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="{A}" xmlns:c="{C}" xmlns:wp="{WP}"><w:body>{body}</w:body></w:document>'
 parts={'word/document.xml':main,'word/styles.xml':f'<w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="21"/></w:rPr></w:rPrDefault></w:docDefaults></w:styles>','_rels/.rels':f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>'}
 rels=f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="styles" Type="{R}/styles" Target="styles.xml"/>'
 overrides='<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
 for i,data in enumerate(charts,1):
  parts[f'word/charts/chart{i}.xml']=data;rels+=f'<Relationship Id="chart{i}" Type="{R}/chart" Target="charts/chart{i}.xml"/>';overrides+=f'<Override PartName="/word/charts/chart{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>'
 parts['word/_rels/document.xml.rels']=rels+'</Relationships>'
 types='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'+overrides+'</Types>'
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml',types)
  for p,s in parts.items():z.writestr(p,s)
 return {'filename':name,'content':base64.b64encode(out.getvalue()).decode(),'mime':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','draft':True}

"""SOP-derived validation and accounting. Decimal arithmetic; no GL-derived P&L.
This portable engine deliberately fails closed on unsupported or ambiguous exports.
"""
import base64, calendar, hashlib, io, json, re, zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.etree import ElementTree as ET

VERSION='2.1.0-staged-review'
class ValidationError(ValueError): pass
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
DEFAULT_CONFIG={
 'client':'Saint Eyewear Pty Ltd','currency':'AUD','financial_year_start':7,
 'confirmed':False,
 'groups':{
  'revenue':["Sales","Sales Revenue","Sales - Online","Revenue","Fees AfterPay","Fees Paypal","Fees Shopify","Other Tax - US","Paypal Sales","Product Revenue - AU","Product Revenue - CA","Product Revenue - Croatia","Product Revenue - Denmark","Product Revenue - Finland","Product Revenue - France","Product Revenue - Germany","Product Revenue - Hong Kong","Product Revenue - Hungary","Product Revenue - Isle Of Man","Product Revenue - Israel","Product Revenue - Japan","Product Revenue - Other","Product Revenue - Pakistan","Product Revenue - Peru","Product Revenue - Philippines","Product Revenue - Poland","Product Revenue - Portugal","Product Revenue - Singapore","Product Revenue - Sweden","Product Revenue - Switzerland","Product Revenue - Taiwan","Product Revenue - Thailand","Product Revenue - UK","Product Revenue - US","Product Revenue - Vietnam","Product Revenue -Luxembourg","Product Revenue -NZ","Product Revenue – Austria","Product Revenue – Guernsey","Product Revenue – Ireland","Product Revenue – Italy","Product Revenue – Netherlands","Product Revenue – S Africa","Product Revenue – Spain","Product Revenuw -Belgium","Product Revune - UAE","Refunds - France","Refunds - Germany","Refunds - Netherlands","Refunds - Spain","Refund - France","Refunds – Ireland","Refunds AU","Refunds CA","Refunds NZ","Refunds Other","Refunds Peru","Refunds Singapore","Refunds UK","Refunds US","Refunds- Portugal","Refunds-Japan","Shipping Income - AU","Shipping Income - Other"],
  'cogs':['Cost of Goods Sold','Cost of Sales','Purchases','Freight and Delivery - COGS','COGS_Processing fee','Shipping Cost'],
  'marketing':['Advertising','Marketing','Facebook Ads','Google Ads','Meta Ads','Advertising & Marketing','Social Media Ads - AppLovin','Social Media Ads - Google','Social Media Ads - Meta','Social Media Ads - Other','Social Media Ads - Pinterest','Social Media Ads - Snapchat','Social Media Ads - Tiktok'],
  'operating':['Bank Revaluations','Brand Protection Expense','Consulting & Accounting','Contractors- Upwork','Growth Payments','Postage & Courier','Rounding','Subsctiptions - Shopify','Travel - International','Travel - National','Motor Vehicle Expenses','Software Expense','Software','Subscriptions','Professional Services','Accounting','Bookkeeping','Rent','Motor Vehicle','Bank Fees','Merchant Fees','Payment Processing Fees','Processing Fees','Wages and Salaries','Superannuation','Insurance','Telephone & Internet','Office Expenses','Travel','Depreciation','Interest Expense'],
  'other_income':['Other Income','Interest Income'],
 },
 'total_labels':{'revenue':['Total Trading Income','Total Revenue','Total Sales','Total Income'], 'cogs':['Total Cost of Sales','Total Cost of Goods Sold'], 'gross':['Gross Profit'], 'net':['Net Profit','Net Profit / (Loss)','Net Profit/(Loss)'], 'net_assets':['Net Assets'],'equity':['Total Equity'],'earnings':['Current Year Earnings']},
 'drs_sheets':['Daily Reporting','Productwise Sales','Countrywise Sales'],
 'thresholds':{'R1_LINE':'500','R1_PROFIT':'2000','R2':'1','R4':'0.10','R5':'0.20','R6':'3','R8_PERCENT':'0.50','R8_AMOUNT':'5000','R9':'1000','R11':'0.01','R13':'2','R14':'10000'},
 'approved_templates':False,'acceptance_passed':False
}
def norm(x): return re.sub(r'\s+',' ',str(x or '').strip()).casefold()
def dec(x, blank=False):
 if x is None or str(x).strip()=='':
  if blank:return None
  return Decimal(0)
 if isinstance(x,bool):raise ValidationError('A boolean was found where an amount is required.')
 s=str(x).strip().replace(',','').replace('A$','').replace('$','')
 if s in ('-','\u2014'):return Decimal(0)
 if s.startswith('(') and s.endswith(')'):s='-'+s[1:-1]
 try:
  d=Decimal(s)
  if not d.is_finite():raise InvalidOperation()
  return d
 except (InvalidOperation,ValueError):raise ValidationError('Invalid numeric value: '+str(x)[:80])
def numeric(x):
 try:return dec(x,True)
 except ValidationError:return None

def fmt(x):return str(dec(x).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
def shift(m,n):
 y,k=map(int,m.split('-'));z=y*12+k-1+n
 return f'{z//12:04d}-{z%12+1:02d}'
def dt(v):
 if isinstance(v,(date,datetime)):return v.date() if isinstance(v,datetime) else v
 s=str(v or '').strip().replace('Sept ', 'Sep ').replace('-Sept-', '-Sep-')
 for f in ('%Y-%m-%d','%Y-%m-%dT%H:%M:%S','%d/%m/%Y','%d-%m-%Y','%d %b %Y','%d %B %Y','%d-%b-%Y','%d %b %y'):
  try:return datetime.strptime(s,f).date()
  except ValueError:pass
 return None

def month(v):
 d=dt(v)
 if d:return d.strftime('%Y-%m')
 s=str(v or '').strip()
 for f in ('%B %Y','%b %Y','%b-%y','%b-%Y','%B-%Y','%Y-%m'):
  try:return datetime.strptime(s,f).strftime('%Y-%m')
  except ValueError:pass
 return None

def extract_dates(s):
 found=[]
 for p in (r'\b20\d\d-\d\d-\d\d\b',r'\b\d{1,2}[/\-]\d{1,2}[/\-]20\d\d\b',r'\b\d{1,2}[ -][A-Za-z]{3,9}[ -]20\d\d\b'):
  for value in re.findall(p,str(s)):
   d=dt(value)
   if d:found.append(d)
 return found

def safe_zip(raw, maximum=50_000_000):
 if not raw or len(raw)>5_000_000:raise ValidationError('Empty file or file exceeds 5 MB.')
 try:z=zipfile.ZipFile(io.BytesIO(raw))
 except (zipfile.BadZipFile,OSError):raise ValidationError('Not a valid .xlsx/.docx ZIP file. Re-export the original file.')
 infos=z.infolist()
 if len(infos)>4000 or sum(i.file_size for i in infos)>maximum:raise ValidationError('Workbook expands beyond the safe processing limit.')
 if any(i.flag_bits & 1 or '..' in i.filename.split('/') or i.filename.startswith('/') for i in infos):raise ValidationError('Encrypted or unsafe archive is not supported.')
 if any('vbaProject' in i.filename or i.filename.startswith('xl/externalLinks/') for i in infos):raise ValidationError('Macros and external workbook links are not supported. Export an .xlsx snapshot.')
 return z

def xml(z,path):
 raw=z.read(path)
 if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:raise ValidationError('XML entities are not permitted.')
 return ET.fromstring(raw)

def workbook_sheet_names(raw):
 """Read workbook tab names without expanding any worksheet XML."""
 z=safe_zip(raw)
 book=xml(z,'xl/workbook.xml')
 return [sh.get('name') for sh in book.findall('s:sheets/s:sheet',NS)]

def excel(raw, only_sheets=None, max_rows=None):
 """Read cached cell values and styles; never calculate or execute Excel formulas."""
 z=safe_zip(raw)
 try:
  book=xml(z,'xl/workbook.xml'); rel=xml(z,'xl/_rels/workbook.xml.rels')
  links={x.get('Id'):x.get('Target') for x in rel}
  props=book.find('s:workbookPr',NS);base=date(1904,1,1) if props is not None and props.get('date1904') in ('1','true') else date(1899,12,30)
  strings=[]
  if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(x.itertext()) for x in xml(z,'xl/sharedStrings.xml').findall('s:si',NS)]
  styles=[]
  if 'xl/styles.xml' in z.namelist():
   st=xml(z,'xl/styles.xml');formats={int(x.get('numFmtId')):x.get('formatCode','') for x in st.findall('s:numFmts/s:numFmt',NS)}
   for x in st.findall('s:cellXfs/s:xf',NS):
    n=int(x.get('numFmtId','0'));code=re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', '', formats.get(n,''))
    styles.append(n in range(14,23) or n in range(45,48) or bool(re.search(r'[dy]',code,re.I)))
  out={};count=0
  for sh in book.findall('s:sheets/s:sheet',NS):
   if only_sheets is not None and sh.get('name') not in only_sheets:continue
   target=links[sh.get('{'+NS['r']+'}id')];path=target.lstrip('/') if target.startswith('/') else 'xl/'+target
   if '/..' in path:raise ValidationError('Unsafe worksheet relationship.')
   sheet=xml(z,path); rows=[]
   for row in sheet.findall('s:sheetData/s:row',NS):
    rn=int(row.get('r','0'))
    if max_rows is not None and rn>max_rows:break
    if rn<1 or rn>100000:raise ValidationError('Worksheet exceeds 100,000 rows.')
    while len(rows)<rn:rows.append([])
    values=rows[rn-1]
    for cell in row.findall('s:c',NS):
     ref=cell.get('r','');letters=re.match('[A-Z]+',ref)
     if not letters:raise ValidationError('Invalid Excel cell address.')
     col=0
     for c in letters.group():col=col*26+ord(c)-64
     if col>1000:raise ValidationError('Worksheet exceeds 1,000 columns.')
     while len(values)<col:values.append(None)
     count+=1
     if count>500000:raise ValidationError('Workbook exceeds 500,000 cells.')
     ty=cell.get('t','n');v=cell.find('s:v',NS);f=cell.find('s:f',NS)
     if ty=='e':raise ValidationError(f'Excel error in {sh.get("name")}!{ref}; recalculate and export again.')
     if f is not None and (v is None or v.text is None):raise ValidationError(f'Missing cached formula result in {sh.get("name")}!{ref}; recalculate and export again.')
     if ty=='inlineStr':
      inline=cell.find('s:is',NS)
      value=''.join(inline.itertext()) if inline is not None else None
     elif v is None or v.text is None:value=None
     elif ty=='s':value=strings[int(v.text)]
     elif ty=='b':value=v.text=='1'
     elif ty in ('str','d'):value=v.text
     else:
      value=v.text;si=int(cell.get('s','0'))
      if si<len(styles) and styles[si]:value=(base+timedelta(days=int(Decimal(value)))).isoformat()
     values[col-1]=value
   out[sh.get('name')]=rows
  if not out:raise ValidationError('No worksheets found.')
  return out
 except (KeyError,ET.ParseError,IndexError,ValueError,TypeError) as e:
  if isinstance(e,ValidationError):raise
  raise ValidationError('Unsupported or corrupt Excel structure.') from e

def exported(rows):
 found=set()
 for row in rows[:25]:
  for i,v in enumerate(row):
   if re.search(r'\b(exported|generated|run date|printed)\b',str(v or ''),re.I):
    text=' '.join(str(x or '') for x in row[i:i+3]);found.update(x.isoformat() for x in extract_dates(text))
 if len(found)>1:raise ValidationError('Multiple conflicting export dates in the report header.')
 return next(iter(found),None)

def financial(raw,kind,m):
 wb=excel(raw); candidates=[]
 for name,rows in wb.items():
  for ri,row in enumerate(rows[:40]):
   cols=[(j,month(v)) for j,v in enumerate(row) if month(v)]
   if m in [v for _,v in cols] and len(cols)>=3:candidates.append((name,rows,ri,cols))
 if len(candidates)!=1:raise ValidationError(f'{kind}: could not uniquely identify the monthly comparison header for {m}.')
 name,rows,ri,cols=candidates[0]; wanted=[m,shift(m,-1),shift(m,-2)]
 if kind=='Balance Sheet':
  for j,k in cols:
   raw_date=rows[ri][j]
   actual=dt(raw_date)
   y,mo=map(int,k.split('-'))
   last=date(y,mo,calendar.monthrange(y,mo)[1])
   if actual is not None and actual!=last:
    raise ValidationError(f'Balance Sheet: {raw_date} is not the month-end {last}. Export complete calendar month-end balances.')

 if len({v for _,v in cols})!=len(cols):raise ValidationError(f'{kind}: duplicate month columns are ambiguous.')
 if not set(wanted).issubset(v for _,v in cols):raise ValidationError(f'{kind}: current and two consecutive prior months are required.')
 if max(v for _,v in cols)!=m:raise ValidationError(f'{kind}: latest report month differs from selected {m}.')
 title=' '.join(str(x or '') for row in rows[:ri] for x in row)
 if ('profit' not in norm(title) and kind=='P&L') or ('balance sheet' not in norm(title) and kind=='Balance Sheet'):raise ValidationError(f'{kind}: expected report title missing.')
 if 'saint eyewear' not in norm(title):raise ValidationError(f'{kind}: Saint Eyewear entity name is missing or different.')
 first=min(j for j,_ in cols);out={v:{} for _,v in cols}; sections={}; current='';ytd={};lineage={};accounts=set()
 yi=[j for j,v in enumerate(rows[ri]) if norm(v) in ('year to date','year-to-date','ytd')]
 if len(yi)>1:raise ValidationError(f'{kind}: multiple YTD columns.')
 # Distinct Balance Sheet accounts may legitimately share a displayed Xero name
 # when they belong to different sections (e.g. Bank vs Current Liabilities).
 # Classify repeated labels before building the numeric dictionary so neither
 # entry overwrites the other, even where a month happens to be zero.
 repeated={}
 if kind=='Balance Sheet':
  probe_section=''
  for probe in rows[ri+1:]:
   probe_label=next((str(v).strip() for v in probe[:first] if v is not None and str(v).strip()),'')
   if not probe_label:continue
   probe_values=[numeric(probe[j] if j<len(probe) else None) for j,_ in cols]
   if all(v is None for v in probe_values):
    probe_section=probe_label
   else:
    repeated.setdefault(norm(probe_label),[]).append(probe_section)
  for key,sects in repeated.items():
   if len(sects)>1 and (not all(sects) or len(set(norm(v) for v in sects))!=len(sects)):
    raise ValidationError(f'Balance Sheet: repeated account label in the same or unknown section ({key}). Export account codes or supply a reviewed mapping.')
 for rownum,row in enumerate(rows[ri+1:],ri+2):
  label=next((str(v).strip() for v in row[:first] if v is not None and str(v).strip()),'')
  if not label:continue
  values=[numeric(row[j] if j<len(row) else None) for j,_ in cols]
  if all(v is None for v in values):current=label;continue
  is_total=norm(label).startswith('total ') or norm(label) in ('gross profit','net profit','net profit / (loss)','net profit/(loss)','net assets')
  ambiguous=kind=='Balance Sheet' and len(repeated.get(norm(label),[]))>1
  if ambiguous and is_total:raise ValidationError(f'Balance Sheet: duplicated total {label}; explicit reconciliation is required.')
  key=f'{label} [{current}]' if ambiguous else label
  if not is_total:accounts.add(key)
  sections[key]=current
  for (j,k),v in zip(cols,values):
   original=row[j] if j<len(row) else None
   if v is None and original not in (None,''):raise ValidationError(f'{kind}: nonnumeric value at row {rownum}, month {k}.')
   if key in out[k]:raise ValidationError(f'{kind}: repeated account key {key}; account codes or explicit mapping are required.')
   out[k][key]=str(v if v is not None else Decimal(0));lineage[f'{k}|{key}']={'sheet':name,'row':rownum,'column':j+1,'blank':v is None,'source_label':label,'section':current}
  if yi:ytd[key]=str(dec(row[yi[0]] if yi[0]<len(row) else None))
 if not accounts:raise ValidationError(f'{kind}: no account rows extracted.')
 return {'months':out,'display_months':wanted,'accounts':sorted(accounts),'sections':sections,'export_date':exported(rows),'ytd':ytd,'lineage':lineage,'sheet':name}

def general_ledger(raw,m):
 wb=excel(raw);rows=next(iter(wb.values()));header=None
 for i,r in enumerate(rows[:50]):
  h=[norm(x) for x in r]
  if 'date' in h and ('amount' in h or ('debit' in h and 'credit' in h)):header=(i,h);break
 if not header:raise ValidationError('General Ledger: Date and Amount, or Debit and Credit headings, are required.')
 ri,h=header
 title=' '.join(str(v or '') for row in rows[:ri] for v in row)
 # Xero exports typically state their covered period; refuse incomplete monthly exports.
 period=re.search(r'for the period\s+(\d{1,2}\s+[A-Za-z]+\s+20\d\d)\s+to\s+(\d{1,2}\s+[A-Za-z]+\s+20\d\d)',title,re.I)
 if period:
  start,end=dt(period.group(1)),dt(period.group(2))
  y,mo=map(int,m.split('-'))
  expected_start=date(y,mo,1);expected_end=date(y,mo,calendar.monthrange(y,mo)[1])
  if start!=expected_start or end!=expected_end:
   raise ValidationError(f'General Ledger: export covers {period.group(1)} to {period.group(2)}; upload the complete {m} calendar month ({expected_start} to {expected_end}).')
 def idx(*names):return next((i for i,x in enumerate(h) if x in names),None)
 di=idx('date');ai=idx('account','account name');vi=idx('contact','vendor','name');desc=idx('description','details','narration');amt=idx('amount','net amount');debit=idx('debit');credit=idx('credit');ref=idx('reference');account='';tx=[]
 for rn,r in enumerate(rows[ri+1:],ri+2):
  def get(i):return r[i] if i is not None and i<len(r) else None
  if norm(get(di))=='date':continue
  day=dt(get(di))
  if not day:
   row_label=norm(get(di))
   # Xero grouped GL exports include dated transactions followed by subtotal,
   # Net movement and Closing balance rows. These are display summaries, not JEs.
   if row_label=='net movement' or row_label=='total' or row_label.startswith(('total ','opening balance','closing balance')):
    continue
   filled=[str(x).strip() for x in r if x is not None and str(x).strip()]
   if len(filled)==1:
    account=filled[0]
   elif get(di) and any(numeric(get(j)) is not None for j in (amt,debit,credit) if j is not None):
    raise ValidationError(f'General Ledger: unrecognized transaction date at row {rn}.')
   continue
  if day.strftime('%Y-%m')!=m:raise ValidationError('General Ledger transaction month does not match '+m+'.')
  a=str(get(ai) or account).strip()
  if not a:raise ValidationError(f'General Ledger: account name missing at row {rn}.')
  amount=dec(get(amt)) if amt is not None else dec(get(debit))-dec(get(credit))
  description=str(get(desc) or '')
  # The supplied Xero GL has no vendor field; Description often contains a payee.
  # Preserve that provenance rather than claiming the value is a verified contact.
  vendor=str(get(vi) or description).strip()
  tx.append({'date':day.isoformat(),'account':a,'description':description,'vendor':vendor,'vendor_inferred':vi is None,'reference':str(get(ref) or ''),'amount':str(amount),'row':rn})
 if not tx:raise ValidationError('General Ledger: no valid transactions for selected month.')
 return {'transactions':tx,'export_date':exported(rows),'count':len(tx),'vendor_inferred':vi is None}
def daily_reporting(raw,m,config):
 # Exclude large COGS, breakdown and journal working sheets: no report values are taken from them.
 sheet_names=set(workbook_sheet_names(raw))
 if 'Daily Reporting' not in sheet_names:raise ValidationError('DRS missing sheet: Daily Reporting')
 if not sheet_names.intersection({'Productwise Sales','Productwise'}):raise ValidationError('DRS missing sheet: Productwise Sales')
 if not sheet_names.intersection({'Countrywise Sales','Countrywise'}):raise ValidationError('DRS missing sheet: Countrywise Sales')
 wb=excel(raw,only_sheets={'Daily Reporting','Productwise Sales','Productwise','Countrywise Sales','Countrywise'})
 # Accept both the earlier SOP names and the actual Google Sheet export names.
 desired=config.get('drs_sheets') or ['Daily Reporting','Productwise Sales','Countrywise Sales']
 aliases=[['Daily Reporting'],['Productwise Sales','Productwise'],['Countrywise Sales','Countrywise']]
 names=[]
 for i,options in enumerate(aliases):
  choice=next((n for n in [desired[i] if i<len(desired) else '',*options] if n in wb),None)
  if not choice:raise ValidationError('DRS missing sheet: '+ ' or '.join(options))
  names.append(choice)
 rows=wb[names[0]]
 candidates=[]
 for ri,row in enumerate(rows[:3]):
  cols=[(j,dt(v)) for j,v in enumerate(row) if dt(v)]
  if len(cols)>1:candidates.append((ri,cols))
 if len(candidates)!=1:raise ValidationError('DRS: expected one date heading row with daily dates in rows 1-3.')
 _,cols=candidates[0]
 if any(d.strftime('%Y-%m')!=m for _,d in cols):raise ValidationError('DRS daily dates include a different reporting month.')
 if len({d for _,d in cols})!=len(cols):raise ValidationError('DRS: repeated daily dates.')
 expected=calendar.monthrange(int(m[:4]),int(m[5:]))[1]
 dates={d.day for _,d in cols}
 if len(cols)!=expected or dates!=set(range(1,expected+1)):
  raise ValidationError('DRS must contain every calendar day in the selected month (including zero-sales days).')
 labels={}
 for i,row in enumerate(rows[:45]):
  if row and row[0] is not None:
   labels.setdefault(norm(row[0]),i)
 def locate(names,description):
  found=[labels[norm(n)] for n in names if norm(n) in labels]
  if len(set(found))!=1:raise ValidationError(f'DRS: expected exactly one {description} row: {", ".join(names)}.')
  return found[0]
 order_row=locate(['Number of orders','Orders'], 'orders')
 sales_row=locate(['Total sales (A$)','Total sales','Sales'], 'sales')
 refund_row=locate(['Refund','Refunds'], 'refunds')
 data=[]
 for j,d in sorted(cols,key=lambda item:item[1]):
  vals=[]
  for ri in (order_row,sales_row,refund_row):
   v=rows[ri][j] if j<len(rows[ri]) else None
   if v is None or str(v).strip()=='':
    raise ValidationError(f'DRS: missing orders, sales or refunds on {d}. Enter zero explicitly where appropriate.')
   vals.append(dec(v))
  if vals[0]!=vals[0].to_integral_value() or vals[0]<0:raise ValidationError(f'DRS: orders must be a nonnegative integer on {d}.')
  data.append({'date':d.isoformat(),'orders':str(vals[0]),'sales':str(vals[1]),'refunds':str(abs(vals[2]))})
 totals={k:str(sum((dec(x[k]) for x in data),Decimal(0))) for k in ('orders','sales','refunds')}
 def table(name,start,width,totals_allowed):
  rr=wb[name];items=[];total=None
  for rownum,r in enumerate(rr[start-1:],start):
   cells=(r[1:1+width]+[None]*width)[:width]
   if not any(x not in (None,'') for x in cells):continue
   if norm(cells[0]) in {norm(x) for x in totals_allowed}:
    total=cells;break
   # Reject unrelated footer material only after the first summary row, not every
   # preformatted row in the client's Google Sheet workbook.
   if cells[0] is None:continue
   items.append(cells)
  if not items or total is None:
   raise ValidationError(f'DRS {name}: no product/country rows or final Total row.')
  return {'rows':items,'total':total}
 return {'month':m,'daily':data,'totals':totals,
         'products':table(names[1],3,7,['Total Sales','Total']),
         'countries':table(names[2],4,3,['Total','Total Sales'])}
def get_amount(rows,labels,required=True):
 hits=[(k,dec(v)) for k,v in rows.items() if norm(k) in {norm(x) for x in labels}]
 if not hits:
  if required:raise ValidationError('Missing P&L/Balance Sheet line: '+' / '.join(labels))
  return None
 if len(hits)>1 and len({v for _,v in hits})>1:raise ValidationError('Ambiguous totals: '+', '.join(k for k,_ in hits))
 return hits[0][1]

def calculate(pnl,m,config):
 rows=pnl['months'][m];groups={k:Decimal(0) for k in ('revenue','cogs','marketing','operating','other_income')};unknown=[];mapping={}
 for group,names in config['groups'].items():
  if group not in groups:raise ValidationError('Invalid account group: '+group)
  for name in names:
   if norm(name) in mapping:raise ValidationError('An account is mapped to more than one group: '+name)
   mapping[norm(name)]=group
 for a in pnl['accounts']:
  if a not in rows:continue
  group=mapping.get(norm(a))
  if group:groups[group]+=dec(rows[a])
  else:unknown.append({'account':a,'amount':rows[a]})
 revenue=get_amount(rows,config['total_labels']['revenue'],False)
 if revenue is None:revenue=groups['revenue'] if not unknown else None
 if revenue is None:raise ValidationError('Revenue total unavailable; configure account allowlist.')
 gross=get_amount(rows,config['total_labels']['gross']);net=get_amount(rows,config['total_labels']['net'])
 cogs=get_amount(rows,config['total_labels']['cogs'],False)
 if cogs is None:cogs=groups['cogs']
 pbm=net+groups['marketing']
 return {**{k:str(v) for k,v in groups.items()},'revenue':str(revenue),'cogs':str(cogs),'gross':str(gross),'net':str(net),'before_marketing':str(pbm),'margin_pct':str(gross/revenue*100) if revenue else None,'break_even_pct':str(pbm/revenue*100) if revenue else None,'unknown':unknown,'classified_net':str(groups['revenue']-groups['cogs']-groups['marketing']-groups['operating']+groups['other_income'])}

def assess(pnl,bs,gl,drs,m,config=None,previous=None,issued=None):
 config=config or DEFAULT_CONFIG;previous=previous or {};issued=issued or {};t={k:dec(v) for k,v in config['thresholds'].items()};flags=[];coverage={f'R{i}':'evaluated' for i in range(1,15)}
 def add(rule,severity,message,figures=None,group='internal'):
  key=hashlib.sha256((rule+'|'+message).encode()).hexdigest()[:20]
  flags.append({'id':key,'rule':rule,'severity':severity,'message':message,'figures':figures or {},'group':group})
 # Check the financial source totals before displaying headline metrics or allowing review.
 # The supplied August export has cached zero subtotal rows even though account lines are populated.
 for mm in pnl['display_months']:
  values=pnl['months'][mm];sections=pnl['sections']
  section_totals={}
  for account in pnl['accounts']:
   if account in values:
    section=norm(sections.get(account,''))
    section_totals[section]=section_totals.get(section,Decimal(0))+dec(values[account])
  expected_income=section_totals.get('trading income')
  expected_cogs=section_totals.get('cost of sales')
  expected_operating=section_totals.get('operating expenses')
  checks=[('Total Trading Income',expected_income,config['total_labels']['revenue']),
          ('Total Cost of Sales',expected_cogs,config['total_labels']['cogs']),
          ('Total Operating Expenses',expected_operating,['Total Operating Expenses'])]
  for name,expected,aliases in checks:
   recorded=get_amount(values,aliases,False)
   if recorded is not None and expected is not None and abs(recorded-expected)>Decimal('.01'):
    add('SOURCE','Block',f'{mm}: {name} in the Xero export is {fmt(recorded)}, but its underlying account lines sum to {fmt(expected)}. Re-export with correct calculated totals; figures remain unapproved.',{'source_total':fmt(recorded),'sum_of_accounts':fmt(expected),'difference':fmt(expected-recorded)})
  gross=get_amount(values,config['total_labels']['gross'],False)
  profit=get_amount(values,config['total_labels']['net'],False)
  if expected_income is not None and expected_cogs is not None and gross is not None and abs((expected_income-expected_cogs)-gross)>Decimal('.01'):
   add('SOURCE','Block',f'{mm}: Gross Profit does not match trading income less cost of sales.',{'reported_gross':fmt(gross),'sum_of_accounts_gross':fmt(expected_income-expected_cogs)})
  if expected_income is not None and expected_cogs is not None and expected_operating is not None and profit is not None and abs((expected_income-expected_cogs-expected_operating)-profit)>Decimal('.01'):
   add('SOURCE','Block',f'{mm}: Net Profit does not match the net of underlying account lines.',{'reported_net':fmt(profit),'sum_of_accounts_net':fmt(expected_income-expected_cogs-expected_operating)})
 for mm in bs['display_months']:
  row=bs['months'][mm]
  if 'Total Assets' in row and dec(row['Total Assets'])==0 and any(dec(v)!=0 for k,v in row.items() if k not in ('Total Assets','Net Assets','Total Equity')):
   add('SOURCE','Block',f'{mm}: Balance Sheet Total Assets is zero even though underlying account balances are nonzero. Re-export the Balance Sheet with valid totals.')
 if not pnl['export_date'] or not gl['export_date']:add('R3','Block','P&L and GL export dates must both be present in their headers.')
 elif pnl['export_date']!=gl['export_date']:add('R3','Block','P&L and GL export dates differ. Re-export both on the same day.',{'pnl':pnl['export_date'],'gl':gl['export_date']})
 for mm in bs['display_months']:
  b=bs['months'][mm];a=get_amount(b,config['total_labels']['net_assets']);e=get_amount(b,config['total_labels']['equity'])
  if abs(a-e)>t['R2']:add('R2','Block',f'{mm}: Net Assets differs from Total Equity.',{'difference':str(a-e)})
 fy=f'{int(m[:4])-(int(m[5:])<7):04d}-07';periods=[];k=fy
 while k<=m:periods.append(k);k=shift(k,1)
 ytd=get_amount(pnl.get('ytd',{}),config['total_labels']['net'],False)
 if all(k in pnl['months'] for k in periods):
  cumulative=sum((get_amount(pnl['months'][k],config['total_labels']['net']) for k in periods),Decimal(0))
  if ytd is not None and abs(ytd-cumulative)>t['R2']:add('R2','Block','P&L YTD does not equal the sum of P&L months since 1 July.',{'ytd':str(ytd),'sum':str(cumulative)})
  ytd=cumulative
 if ytd is None:add('R2','Block','Current Year Earnings cannot be verified: include a financial-year YTD column or all P&L months since 1 July.')
 else:
  earnings=get_amount(bs['months'][m],config['total_labels']['earnings'])
  if abs(earnings-ytd)>t['R2']:add('R2','Block','Current Year Earnings does not tie to cumulative P&L since 1 July.',{'balance_sheet':str(earnings),'pnl_ytd':str(ytd),'difference':str(earnings-ytd)})
 metrics={k:calculate(pnl,k,config) for k in pnl['display_months']};cur=metrics[m];prior=metrics[shift(m,-1)]
 for k,values in metrics.items():
  for u in values['unknown']:add('MAP','Block',f'{k}: account {u["account"]} has no approved allowlist group.',u)
  if not values['unknown'] and abs(dec(values['classified_net'])-dec(values['net']))>Decimal('.01'):add('MAP','Block',f'{k}: classified P&L does not reconcile to Net Profit.',{'classified_net':values['classified_net'],'net_profit':values['net']})
  if abs(dec(values['revenue'])-dec(values['cogs'])-dec(values['gross']))>Decimal('.01'):add('MAP','Block',f'{k}: revenue less cost of goods does not reconcile to Gross Profit.')
 revised=[]
 if not issued:coverage['R1']='not_evaluated';add('R1','Review','Open item: no issued-pack baseline is stored. Restatements cannot yet be checked. Upload the original issued figures.')
 for k,old in issued.items():
  if k not in pnl['months']:continue
  current=pnl['months'][k]
  for label in set(old)|set(current):
   a=dec(old.get(label,0));b=dec(current.get(label,0));limit=t['R1_PROFIT'] if norm(label) in {norm(x) for x in config['total_labels']['net']} else t['R1_LINE']
   if abs(a-b)>limit:
    revised.append(k);add('R1','Review',f'{k} {label} was restated from {fmt(a)} to {fmt(b)}. The client holds the earlier pack.',{'old':str(a),'new':str(b)},'client')
 r=dec(cur['revenue']);pr=dec(prior['revenue']);net=dec(cur['net']);other=dec(cur['other_income']);market=dec(cur['marketing'])
 if abs(other)>abs(net)*t['R4'] or (net>=0 and net-other<0):add('R4','Review','Other income materially affects the result. Source and explanation needed.',{'other_income':str(other),'net_profit':str(net)},'client')
 if pr and abs((r-pr)/pr)>t['R5']:add('R5','Review',f'Revenue moved {((r-pr)/pr*100):.2f}%. Cause needed: volume, price or refunds.',{'current':str(r),'previous':str(pr)},'client')
 elif not pr and r:add('R5','Review','Revenue changed from zero; a percentage change is undefined.',{'current':str(r),'previous':'0'},'client')
 if cur['margin_pct'] is not None and prior['margin_pct'] is not None:
  delta=dec(cur['margin_pct'])-dec(prior['margin_pct'])
  if abs(delta)>t['R6']:add('R6','Review',f'Gross margin moved {delta:.2f} percentage points to {dec(cur["margin_pct"]):.2f}%.',group='client')
 else:coverage['R6']='not_evaluated';add('R6','Review','Gross margin comparison is undefined because a month has zero revenue.')
 if market>dec(cur['before_marketing']):add('R7','Review' if net<0 else 'Info','Marketing exceeds profit before marketing.',{'marketing':str(market),'before_marketing':cur['before_marketing'],'break_even_pct':cur['break_even_pct']},'client')
 vendors=defaultdict(lambda:Decimal(0));unknown=defaultdict(lambda:Decimal(0));redo=Decimal(0)
 for x in gl['transactions']:
  desc=x['description'];vendor=x['vendor'].strip() or '(Unidentified vendor)'
  if 'redo' in norm(vendor+' '+desc) and 'tech' in norm(vendor+' '+desc):vendor='Redo Tech';redo+=dec(x['amount'])
  vendors[vendor]+=dec(x['amount'])
  if any(k in norm(x['account']+' '+x['vendor']+' '+desc) for k in ('suspense','unknown','unallocated')):unknown[x['account']]+=abs(dec(x['amount']))
 oldvendors=previous.get('vendors')
 if oldvendors is None:coverage['R8']='not_evaluated';add('R8','Review','Open item: prior-month GL/vendor totals are not stored. Vendor movements cannot be checked from the current GL alone.')
 else:
  for v in set(vendors)|set(oldvendors):
   a=dec(oldvendors.get(v,0));b=vendors.get(v,Decimal(0));delta=abs(b-a)
   if delta>t['R8_AMOUNT'] and (not a or delta/abs(a)>t['R8_PERCENT']):add('R8','Review',f'{v} moved from {fmt(a)} to {fmt(b)}. Check timing or coding.',{'old':str(a),'new':str(b)})
 if sum(unknown.values())>t['R9']:add('R9','Review','Uncoded/Unknown/Suspense transaction amounts need explanation.',{k:str(v) for k,v in unknown.items()},'client')
 old_list=previous.get('accounts')
 if old_list is None:
  coverage['R10']='not_evaluated'
  add('R10','Review','Open item: the prior-period account list is missing. A zero comparative amount does not establish that an account is new.')
 else:
  old_accounts={norm(x) for x in old_list}
  for a in pnl['accounts']:
   if norm(a) not in old_accounts:add('R10','Review',f'New account {a}. Confirm treatment.',{'amount':pnl['months'][m].get(a)})
 drs_sales=dec(drs['totals']['sales']);diff=drs_sales-r
 if (r and abs(diff)/abs(r)>t['R11']) or (not r and drs_sales):add('R11','Review','The DRS sales sheet and P&L sales differ.',{'drs':str(drs_sales),'pnl':str(r),'difference':str(diff)},'client')
 seen=defaultdict(list);byaccount=defaultdict(list)
 for x in gl['transactions']:
  byaccount[x['account']].append(x)
  key=(norm(x['vendor']),str(dec(x['amount'])))
  if key[0] and dec(x['amount']):
   matches=[p for p in seen[key] if abs((dt(p['date'])-dt(x['date'])).days)<=3]
   if matches:add('R12','Review',f'Possible duplicate: {x["vendor"]}, {fmt(x["amount"])} within 3 days.',{'rows':[matches[0]['row'],x['row']]})
   seen[key].append(x)
  n=dec(x['amount'])
  if abs(n)>t['R14'] and n%1000==0:add('R14','Info','Large round entry for reviewer attention.',{'account':x['account'],'amount':str(n),'date':x['date']})
 for a,tx in byaccount.items():
  monthly=[x for x in tx if re.search(r'\b(monthly|month total|monthly total)\b',x['description'],re.I)]
  if monthly and len(tx)>len(monthly):add('R12','Review',f'Possible overlap in {a}: monthly total alongside other dated entries.',{'monthly_rows':[x['row'] for x in monthly],'other_rows':[x['row'] for x in tx if x not in monthly]})
 refunds=dec(drs['totals']['refunds']);old_drs=previous.get('drs_totals')
 if not old_drs or not dec(old_drs.get('sales')) or not drs_sales:coverage['R13']='not_evaluated';add('R13','Review','Open item: both current and prior DRS sales/refunds are required for refund-rate movement.')
 else:
  rate=refunds/drs_sales*100;oldrate=dec(old_drs['refunds'])/dec(old_drs['sales'])*100
  if abs(rate-oldrate)>t['R13']:add('R13','Review',f'Refunds were {rate:.2f}% of sales, against {oldrate:.2f}% last month.',group='client')
 bridge=None
 if pr:
  oldmargin=dec(prior['gross'])/pr
  bridge={'start':prior['net'],'revenue_at_prior_margin':str((r-pr)*oldmargin),'margin':str(dec(cur['gross'])-r*oldmargin),'marketing':str(dec(prior['marketing'])-market),'running_costs':str(dec(prior['operating'])-dec(cur['operating'])),'other_income':str(other-dec(prior['other_income'])),'end':cur['net']}
  bridge['tie_difference']=str(dec(bridge['end'])-sum((dec(v) for k,v in bridge.items() if k not in ('end',)),Decimal(0)))
 if not config.get('confirmed'):add('CONFIG','Review','Owner must confirm the proposed thresholds and account mappings before client use.')
 return {'month':m,'pnl':pnl,'bs':bs,'drs':drs,'gl_count':gl['count'],'metrics':metrics,'vendors':{k:str(v) for k,v in vendors.items()},'redo_tech_detail':str(redo),'bridge':bridge,'flags':flags,'coverage':coverage,'revised_months':sorted(set(revised)),'status':'blocked' if any(f['severity']=='Block' for f in flags) else 'review','client_ready':False,'release_limitations':['Original report templates have not been supplied/verified.','August and September issued-pack acceptance tests have not been run.'],'version':VERSION}

def inspect_uploads(payload):
 """Identify four uploaded workbooks from their content, never from filenames or upload order."""
 files=payload.get('files') or {}
 if len(files)!=4 or set(files)!={'pnl','bs','gl','drs'}:
  raise ValidationError('Upload exactly four .xlsx workbooks.')
 detected={};month_candidates=[]
 for uploaded_slot,encoded in files.items():
  try: raw=base64.b64decode(encoded,validate=True)
  except Exception:raise ValidationError('One uploaded workbook has invalid encoding.')
  names=workbook_sheet_names(raw)
  wb=excel(raw,only_sheets={'Daily Reporting'} if 'Daily Reporting' in names else set(names),max_rows=45)
  headings=' '.join(str(v or '') for rows in wb.values() for row in rows[:6] for v in row[:4]).casefold()
  if 'Daily Reporting' in wb:
   kind='drs'
   row=wb['Daily Reporting']
   daily=[dt(v) for line in row[:3] for v in line if dt(v)]
   if not daily:raise ValidationError('DRS: cannot detect reporting month from its daily date row.')
   months={d.strftime('%Y-%m') for d in daily}
   if len(months)!=1:raise ValidationError('DRS: dates span multiple reporting months.')
   month_candidates.append(('DRS',next(iter(months))))
  elif 'general ledger' in headings:
   kind='gl'
  elif 'balance sheet' in headings:
   kind='bs'
  elif 'profit and loss' in headings:
   kind='pnl'
  else:raise ValidationError('Cannot identify one uploaded file. Expected Xero Profit and Loss, Balance Sheet, General Ledger Detail, or the Daily Reporting workbook.')
  if kind in detected:raise ValidationError('Two files appear to be '+kind+'. Upload one of each required report.')
  detected[kind]=uploaded_slot
  if kind in ('pnl','bs'):
   rows=next(iter(wb.values()))
   # The monthly comparison header must identify full month columns.
   candidates=[(ri,[(j,month(v)) for j,v in enumerate(row) if month(v)])
               for ri,row in enumerate(rows[:40])]
   candidates=[(ri,cols) for ri,cols in candidates if len(cols)>=3]
   if len(candidates)==1:
    month_candidates.append((kind,max(m for j,m in candidates[0][1])))
 if set(detected)!={'pnl','bs','gl','drs'}:
  raise ValidationError('Upload one of each: Profit and Loss, Balance Sheet, General Ledger, Daily Reporting Sheet.')
 detected_months={m for kind,m in month_candidates}
 if len(detected_months)!=1:
  raise ValidationError('Files show different reporting months: '+', '.join(k+' '+v for k,v in month_candidates)+'. Upload matching full-month reports.')
 return {'month':next(iter(detected_months)),'source_map':detected}

def parse_file(payload):
 """Parse one canonical source workbook per Python request to contain memory use."""
 m=payload.get('month','')
 if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])',m):raise ValidationError('Choose a valid report month.')
 kind=payload.get('kind')
 if kind not in ('pnl','bs','gl','drs'):raise ValidationError('Unknown source file type.')
 encoded=payload.get('file')
 if not isinstance(encoded,str):raise ValidationError('Missing Excel source file.')
 try:raw=base64.b64decode(encoded,validate=True)
 except Exception:raise ValidationError('Invalid Excel source file encoding.')
 config=json.loads(json.dumps(DEFAULT_CONFIG));config.update(payload.get('config') or {})
 if kind=='pnl':data=financial(raw,'P&L',m)
 elif kind=='bs':data=financial(raw,'Balance Sheet',m)
 elif kind=='gl':data=general_ledger(raw,m)
 else:data=daily_reporting(raw,m,config)
 return {'kind':kind,'data':data,'source_hash':hashlib.sha256(raw).hexdigest()}

def assess_parsed(payload):
 """Assess only already-validated structured results; files never need to be re-read."""
 m=payload.get('month','')
 if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])',m):raise ValidationError('Choose a valid report month.')
 parts=payload.get('parts') or {}
 if set(parts)!=set(('pnl','bs','gl','drs')):raise ValidationError('Four parsed reports are required.')
 for kind,part in parts.items():
  if not isinstance(part,dict) or part.get('kind')!=kind or not isinstance(part.get('data'),dict):
   raise ValidationError('A parsed report has an incorrect source type.')
 config=json.loads(json.dumps(DEFAULT_CONFIG));config.update(payload.get('config') or {})
 result=assess(parts['pnl']['data'],parts['bs']['data'],parts['gl']['data'],parts['drs']['data'],m,config,payload.get('previous'),payload.get('issued'))
 result['source_hashes']={k:parts[k]['source_hash'] for k in ('pnl','bs','gl','drs')}
 return result

def process(payload):
 files=payload.get('files') or {}
 if set(files)!=set(('pnl','bs','gl','drs')):raise ValidationError('Exactly four source files are required.')
 m=payload.get('month','')
 parts={kind:parse_file({'month':m,'kind':kind,'file':files[kind],'config':payload.get('config')})
        for kind in ('pnl','bs','gl','drs')}
 return assess_parsed({'month':m,'parts':parts,'config':payload.get('config'),
                       'previous':payload.get('previous'),'issued':payload.get('issued')})

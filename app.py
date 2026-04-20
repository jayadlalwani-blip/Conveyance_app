import streamlit as st
import pandas as pd
import zipfile, io, re, os
from PIL import Image
import base64
from openai import OpenAI
from datetime import datetime

st.set_page_config(page_title='Monthly Conveyance Processor', layout='wide')
st.title('Monthly Conveyance Processor')
st.caption('Upload screenshots or a ZIP file, then download Excel summary + renamed files ZIP.')

OFFICE_KEYS = ['altimus','pandurang budhkar','century','worli']

def is_office(loc:str):
    t = (loc or '').lower()
    return any(k in t for k in OFFICE_KEYS)

def extract_text(img):
    try:
        client = OpenAI(api_key=st.secrets['OPENAI_API_KEY'])
        buf = io.BytesIO(); img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        resp = client.responses.create(
            model='gpt-4.1-mini',
            input=[{
                'role':'user',
                'content':[
                    {'type':'input_text','text':'Extract ride receipt details: date, time, from, to, fare. Return plain text.'},
                    {'type':'input_image','image_url':f'data:image/png;base64,{b64}'}
                ]
            }]
        )
        return resp.output_text
    except Exception as e:
        return ''

def find(pattern, text, flags=0):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else ''

def parse_receipt(text):
    date = find(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})', text)
    time = find(r'(\d{1,2}:\d{2}\s?(?:AM|PM))', text, re.I)
    fare = find(r'(?:Rs\.?|INR)\s?([\d,.]+)', text, re.I)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    frm, to = '', ''
    for i,l in enumerate(lines):
        if not frm and any(k in l.lower() for k in OFFICE_KEYS): frm = l
        if i+1 < len(lines) and frm and not to: to = lines[i+1]
    if not frm and len(lines) > 1: frm = lines[0]
    if not to and len(lines) > 2: to = lines[1]
    return {'Date':date,'Time':time,'From':frm,'To':to,'Fare':fare}

def normalize_date(s):
    for fmt in ['%d-%m-%Y','%d/%m/%Y','%d %b %Y','%d %B %Y']:
        try:
            return datetime.strptime(s, fmt).strftime('%d-%m-%Y')
        except: pass
    return 'UnknownDate'

uploads = st.file_uploader('Upload images or ZIP', type=['png','jpg','jpeg','zip'], accept_multiple_files=True)
if st.button('Process') and uploads:
    rows=[]
    outzip = io.BytesIO()
    used = {}
    with zipfile.ZipFile(outzip,'w',zipfile.ZIP_DEFLATED) as zout:
        for up in uploads:
            files=[]
            if up.name.lower().endswith('.zip'):
                with zipfile.ZipFile(up) as z:
                    for n in z.namelist():
                        if n.lower().endswith(('.png','.jpg','.jpeg')):
                            files.append((n, z.read(n)))
            else:
                files.append((up.name, up.read()))
            for name,data in files:
                img = Image.open(io.BytesIO(data))
                txt = extract_text(img)
                rec = parse_receipt(txt)
                d = normalize_date(rec['Date'])
                used[d] = used.get(d,0)+1
                suffix = '' if used[d]==1 else f'_{used[d]}'
                ext = '.png'
                newname = f'{d}{suffix}{ext}'
                rec['File Name']=newname
                rec['Office Pickup']='Yes' if is_office(rec['From']) else 'No'
                try:
                    t = datetime.strptime(rec['Time'].upper().replace(' ',''), '%I:%M%p') if rec['Time'] else None
                    cut = datetime.strptime('09:30PM','%I:%M%p')
                    rec['Left Before 9:30 PM']='Yes' if t and t < cut else 'No'
                except:
                    rec['Left Before 9:30 PM']=''
                rows.append(rec)
                buf=io.BytesIO(); img.save(buf, format='PNG')
                zout.writestr('Bills/'+newname, buf.getvalue())
        df=pd.DataFrame(rows)[['File Name','Date','Time','From','To','Fare','Office Pickup','Left Before 9:30 PM']]
        xbuf=io.BytesIO()
        with pd.ExcelWriter(xbuf, engine='openpyxl') as writer:
            df.to_excel(writer,index=False,sheet_name='Summary')
        zout.writestr('Conveyance_Summary.xlsx', xbuf.getvalue())
    st.dataframe(df, use_container_width=True)
    st.download_button('Download Final ZIP', outzip.getvalue(), 'Conveyance_Output.zip', 'application/zip')

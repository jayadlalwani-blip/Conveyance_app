import streamlit as st
import pandas as pd
import zipfile, io, re, requests
from PIL import Image
from datetime import datetime

st.set_page_config(page_title="Monthly Conveyance Processor", layout="wide")

OFFICE_KEYS = ["altimus", "pandurang budhkar", "century", "worli"]

st.title("Monthly Conveyance Processor")
st.caption("Free version using OCR.space")


def is_office(loc):
    text = (loc or "").lower()
    return any(k in text for k in OFFICE_KEYS)


def safe_time_flag(time_text):
    try:
        t = datetime.strptime(time_text.upper().replace(" ", ""), "%I:%M%p")
        cut = datetime.strptime("09:30PM", "%I:%M%p")
        return "Yes" if t < cut else "No"
    except:
        return ""


def extract_text_ocrspace(img):
    try:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        files = {"filename": ("image.png", buf.getvalue())}

        payload = {
            "apikey": "helloworld",
            "language": "eng",
            "isOverlayRequired": False
        }

        r = requests.post(
            "https://api.ocr.space/parse/image",
            files=files,
            data=payload,
            timeout=60
        ).json()

        return r["ParsedResults"][0]["ParsedText"]
    except:
        return ""


def parse_text(text):
    date = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', text)
    time = re.search(r'(\d{1,2}:\d{2}\s?(AM|PM))', text, re.I)
    fare = re.search(r'(Rs\.?\s?[\d,.]+)', text, re.I)

    lines = [x.strip() for x in text.splitlines() if x.strip()]
    frm = lines[0] if len(lines) > 0 else ""
    to = lines[1] if len(lines) > 1 else ""

    return {
        "Date": date.group(1) if date else "",
        "Time": time.group(1) if time else "",
        "From": frm,
        "To": to,
        "Fare": fare.group(1) if fare else ""
    }


uploads = st.file_uploader(
    "Upload images or ZIP",
    type=["png", "jpg", "jpeg", "zip"],
    accept_multiple_files=True
)

if st.button("Process") and uploads:
    rows = []
    used = {}
    outzip = io.BytesIO()

    with zipfile.ZipFile(outzip, "w", zipfile.ZIP_DEFLATED) as zout:
        for up in uploads:
            files = []

            if up.name.lower().endswith(".zip"):
                with zipfile.ZipFile(up) as z:
                    for n in z.namelist():
                        if n.lower().endswith((".png", ".jpg", ".jpeg")):
                            files.append((n, z.read(n)))
            else:
                files.append((up.name, up.read()))

            for name, data in files:
                img = Image.open(io.BytesIO(data)).convert("RGB")
                text = extract_text_ocrspace(img)
                rec = parse_text(text)

                d = rec["Date"] or "UnknownDate"
                used[d] = used.get(d, 0) + 1
                suffix = "" if used[d] == 1 else f"_{used[d]}"
                newname = f"{d}{suffix}.png"

                rows.append({
                    "File Name": newname,
                    **rec,
                    "Office Pickup": "Yes" if is_office(rec["From"]) else "No",
                    "Left Before 9:30 PM": safe_time_flag(rec["Time"])
                })

                buf = io.BytesIO()
                img.save(buf, format="PNG")
                zout.writestr("Bills/" + newname, buf.getvalue())

        df = pd.DataFrame(rows)
        excel = io.BytesIO()
        with pd.ExcelWriter(excel, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)

        zout.writestr("Conveyance_Summary.xlsx", excel.getvalue())

    st.dataframe(df, use_container_width=True)
    st.download_button(
        "Download Final ZIP",
        outzip.getvalue(),
        "Conveyance_Output.zip",
        "application/zip"
    )

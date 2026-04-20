import streamlit as st
import pandas as pd
import zipfile, io, re, os, json, base64
from PIL import Image
from datetime import datetime
from openai import OpenAI

st.set_page_config(page_title="Monthly Conveyance Processor", layout="wide")

st.title("Monthly Conveyance Processor")
st.caption("Upload screenshots or ZIP, process receipts, download Excel + ZIP")

OFFICE_KEYS = ["altimus", "pandurang budhkar", "century", "worli"]


def is_office(loc):
    t = (loc or "").lower()
    return any(k in t for k in OFFICE_KEYS)


def extract_receipt_data(img):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        prompt = """
Read this Uber or Rapido ride receipt screenshot.

Return ONLY valid JSON in this exact format:
{
  "date": "",
  "time": "",
  "from": "",
  "to": "",
  "fare": ""
}

Rules:
- Use DD-MM-YYYY for date
- Keep time exactly as visible
- Extract full pickup location
- Extract full drop location
- Fare should be numeric only
- If any field missing, leave blank
"""

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64}",
                        },
                    ],
                }
            ],
        )

        txt = response.output_text.strip()
        return json.loads(txt)

    except Exception:
        return {
            "date": "",
            "time": "",
            "from": "",
            "to": "",
            "fare": "",
        }


def safe_time_flag(time_text):
    try:
        t = datetime.strptime(time_text.upper().replace(" ", ""), "%I:%M%p")
        cut = datetime.strptime("09:30PM", "%I:%M%p")
        return "Yes" if t < cut else "No"
    except Exception:
        return ""


uploads = st.file_uploader(
    "Upload images or ZIP",
    type=["png", "jpg", "jpeg", "zip"],
    accept_multiple_files=True,
)

if st.button("Process") and uploads:
    rows = []
    used_dates = {}
    outzip = io.BytesIO()

    with zipfile.ZipFile(outzip, "w", zipfile.ZIP_DEFLATED) as zout:

        for up in uploads:
            files = []

            if up.name.lower().endswith(".zip"):
                with zipfile.ZipFile(up) as z:
                    for name in z.namelist():
                        if name.lower().endswith((".png", ".jpg", ".jpeg")):
                            files.append((name, z.read(name)))
            else:
                files.append((up.name, up.read()))

            for original_name, data in files:
                try:
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                except Exception:
                    continue

                data_json = extract_receipt_data(img)

                date_val = data_json.get("date", "").strip()
                time_val = data_json.get("time", "").strip()
                from_val = data_json.get("from", "").strip()
                to_val = data_json.get("to", "").strip()
                fare_val = data_json.get("fare", "").strip()

                base_date = date_val if date_val else "UnknownDate"
                used_dates[base_date] = used_dates.get(base_date, 0) + 1
                suffix = "" if used_dates[base_date] == 1 else f"_{used_dates[base_date]}"

                file_name = f"{base_date}{suffix}.png"

                row = {
                    "File Name": file_name,
                    "Date": date_val,
                    "Time": time_val,
                    "From": from_val,
                    "To": to_val,
                    "Fare": fare_val,
                    "Office Pickup": "Yes" if is_office(from_val) else "No",
                    "Left Before 9:30 PM": safe_time_flag(time_val),
                }

                rows.append(row)

                img_buf = io.BytesIO()
                img.save(img_buf, format="PNG")
                zout.writestr("Bills/" + file_name, img_buf.getvalue())

        df = pd.DataFrame(rows)

        if not df.empty:
            df = df[
                [
                    "File Name",
                    "Date",
                    "Time",
                    "From",
                    "To",
                    "Fare",
                    "Office Pickup",
                    "Left Before 9:30 PM",
                ]
            ]

        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Summary")

        zout.writestr("Conveyance_Summary.xlsx", excel_buf.getvalue())

    st.success("Processing complete")
    st.dataframe(df, use_container_width=True)

    st.download_button(
        "Download Final ZIP",
        outzip.getvalue(),
        file_name="Conveyance_Output.zip",
        mime="application/zip",
    )

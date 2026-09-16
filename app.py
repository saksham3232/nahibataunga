"""
ATTENDANCE MANAGER - STREAMLIT FRONTEND
----------------------------------------
Talks to the Google Apps Script Web App (see AppsScript_Code.gs) which
reads/writes directly to your Google Sheet.

SETUP:
1. Deploy AppsScript_Code.gs as a Web App (see instructions at top of that file).
2. Paste the deployed Web App URL below into APPS_SCRIPT_URL.
3. Run:  pip install -r requirements.txt
4. Run:  streamlit run streamlit_app.py
"""

import streamlit as st
import requests
import pandas as pd
from datetime import date

# ------------------------------------------------------------------
# 1. PASTE YOUR DEPLOYED GOOGLE APPS SCRIPT WEB APP URL HERE
# ------------------------------------------------------------------
# APPS_SCRIPT_URL = "https://script.google.com/macros/s/XXXXXXXXXXXXXXXXXXXXXXXX/exec"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwCXrMODHAMOVyu5VYOTxluhVaEPT7RtsWGguCP7i1xmEMEVRCNt9UQcBCBfgtJXLpv/exec"
# APPS_SCRIPT_URL = st.secrets["APPS_SCRIPT_URL"]

st.set_page_config(page_title="Attendance Manager", page_icon="📋", layout="centered")


def make_headers_unique(headers):
    """
    Cleans up header labels for display and guarantees no duplicates,
    so pandas/pyarrow never chokes on a table with repeated column names.
    - Shortens ISO timestamps like '2026-09-16T07:00:00.000Z' down to '2026-09-16'.
    - Appends (2), (3)... to any header that repeats.
    """
    cleaned = []
    for h in headers:
        h_str = str(h)
        if "T" in h_str and h_str.endswith("Z") and len(h_str) >= 20:
            h_str = h_str.split("T")[0]
        cleaned.append(h_str)

    seen = {}
    unique = []
    for h in cleaned:
        if h not in seen:
            seen[h] = 1
            unique.append(h)
        else:
            seen[h] += 1
            unique.append(f"{h} ({seen[h]})")
    return unique


def call_api(payload: dict) -> dict:
    """Sends a POST request to the Apps Script backend and returns parsed JSON."""
    try:
        resp = requests.post(APPS_SCRIPT_URL, data=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"success": False, "message": f"Request failed: {e}"}

st.title("📋 Attendance Manager")

if not APPS_SCRIPT_URL:
    st.error("Apps Script URL is not configured.")
    st.stop()

if "XXXXXXXXXXXXXXXXXXXXXXXX" in APPS_SCRIPT_URL:
    st.warning(
        "⚠️ You haven't set your Apps Script Web App URL yet. "
        "Deploy AppsScript_Code.gs and paste the URL into `APPS_SCRIPT_URL` in this file."
    )

# Date selector - controls which date column attendance is written to
selected_date = st.date_input("📅 Select attendance date", value=date.today())
date_str = selected_date.strftime("%Y-%m-%d")

tab_mark, tab_add, tab_view = st.tabs(["✅ Mark Attendance", "➕ Add Student", "📊 View Records"])

# --------------------------- MARK ATTENDANCE ---------------------------
with tab_mark:
    st.subheader(f"Mark attendance for {date_str}")

    st.caption(
        "Full roll no format example: **2026073001** = Prefix `20260730` + last 2 digits `01`."
    )

    prefix = st.text_input(
        "Roll No Prefix (fixed part, e.g. class/batch code)",
        value="20260730",
        key="mark_prefix",
    )

    last_two_input = st.text_area(
        "Enter last 2 digits of each Roll No, comma-separated",
        placeholder="e.g. 01, 05, 12, 23, 44",
        key="mark_last_two",
        height=100,
    )

    if st.button("Mark Present", type="primary"):
        prefix_clean = prefix.strip()
        raw_values = [v.strip() for v in last_two_input.split(",") if v.strip() != ""]

        if not prefix_clean:
            st.warning("Please enter the roll no prefix.")
        elif not raw_values:
            st.warning("Please enter at least one last-two-digit value.")
        else:
            results = []
            for v in raw_values:
                if not v.isdigit():
                    results.append({"input": v, "rollno": "-", "status": "❌ Invalid (not a number)"})
                    continue
                # zero-pad to 2 digits (so "1" becomes "01")
                padded = v.zfill(2)
                full_rollno = f"{prefix_clean}{padded}"
                api_result = call_api(
                    {
                        "action": "markAttendance",
                        "rollno": full_rollno,
                        "date": date_str,
                        "name": "",
                    }
                )
                if api_result.get("success"):
                    status = "ℹ️ Already marked" if api_result.get("already") else "✅ Marked present"
                else:
                    status = f"❌ {api_result.get('message', 'Failed')}"
                results.append({"input": v, "rollno": full_rollno, "status": status})

            st.write(f"**Results for {date_str}:**")
            st.dataframe(pd.DataFrame(results), width='stretch', hide_index=True)

            success_count = sum(1 for r in results if r["status"].startswith("✅"))
            already_count = sum(1 for r in results if r["status"].startswith("ℹ️"))
            fail_count = sum(1 for r in results if r["status"].startswith("❌"))
            st.success(
                f"Done: {success_count} newly marked, {already_count} already present, {fail_count} failed."
            )

# --------------------------- ADD STUDENT ---------------------------
with tab_add:
    st.subheader("Add a new student (optional pre-registration)")
    new_roll = st.text_input("Roll No", key="add_rollno")
    new_name = st.text_input("Name", key="add_name")

    if st.button("Add Student"):
        if not new_roll.strip():
            st.warning("Please enter a roll number.")
        else:
            result = call_api(
                {"action": "addStudent", "rollno": new_roll.strip(), "name": new_name.strip()}
            )
            if result.get("success"):
                st.success(result.get("message"))
            else:
                st.error(result.get("message", "Something went wrong."))

# --------------------------- VIEW RECORDS ---------------------------
with tab_view:
    st.subheader("Full attendance sheet")
    if st.button("Refresh Data"):
        st.session_state["refresh"] = True

    result = call_api({"action": "getSheetData"})
    if result.get("success"):
        headers = result.get("headers", [])
        rows = result.get("rows", [])
        if headers:
            headers = make_headers_unique(headers)
            df = pd.DataFrame(rows, columns=headers)
            # Cast everything to string for display: Google Sheets returns a mix of
            # numbers (1) and blank strings ("") in attendance columns, which pyarrow
            # cannot serialize as one consistent column type otherwise.
            df = df.astype(str).replace("nan", "")
            st.dataframe(df, width='stretch')
        else:
            st.info("No data yet. Mark some attendance first!")
    else:
        st.error(result.get("message", "Could not load sheet data."))

    st.divider()
    st.subheader(f"Attendance just for {date_str}")
    day_result = call_api({"action": "getAttendance", "date": date_str})
    if day_result.get("success"):
        attendance = day_result.get("attendance", [])
        if attendance:
            df_day = pd.DataFrame(attendance)
            df_day["present"] = df_day["present"].map({True: "✅ Present", False: "❌ Absent"})
            st.dataframe(df_day, width='stretch')
        else:
            st.info(f"No date column found yet for {date_str}. Mark attendance to create it.")
    else:
        st.error(day_result.get("message", "Could not load attendance for this date."))

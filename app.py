"""
lokarichhokri — Sales & Earnings Tracker
=========================================
Product ID format:  {MAKER_CODE}{PRODUCT_NO:02d}{COLOUR_SHORT}-{TOTAL_COST}
Example:            DS01RAS-1300
  DS  → Dhruva (maker code from makers.csv)
  01  → product_no 01 = Tulip Coaster  (from products.csv)
  RAS → colour shortcode
  1300→ total cost (ignored for earning calc; product_no drives the maker's cut)
"""

import streamlit as st
import pandas as pd
import json, os, re
from datetime import datetime, date
import plotly.graph_objects as go

# ── File paths ────────────────────────────────────────────────────────────────
PRODUCTS_FILE  = "products.csv"
MAKERS_FILE    = "makers.csv"
INVENTORY_FILE = "inventory.csv"
SALES_FILE     = "sales.csv"
STATE_FILE     = "state.json"   # stores month label + any runtime overrides

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="lokarichhokri",
    page_icon="🧶",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Poppins:wght@300;400;500;600&display=swap');

:root{
    --tc:#B5442A; --tcl:#D4896A; --tcp:#F2D4C8;
    --cream:#FDF6F0; --dark:#6B1F1F;
}
html,body{font-family:'Poppins',sans-serif; color:#6B1F1F !important;}
/* Do NOT set color on [class*="css"] — it overrides metric text */
.stApp, .main .block-container{color:#6B1F1F !important;}

.stApp{
    background:var(--cream);
    background-image:
        radial-gradient(circle at 20% 80%,rgba(181,68,42,.06) 0%,transparent 50%),
        radial-gradient(circle at 80% 20%,rgba(212,137,106,.08) 0%,transparent 50%);
}

/* brand */
.brand-title{
    font-family:'Playfair Display',serif;
    font-size:2.6rem; color:var(--tc);
    margin:0; letter-spacing:2px; font-style:italic;
}
.brand-sub{
    font-size:.8rem; color:var(--tcl);
    letter-spacing:4px; text-transform:uppercase; margin-top:.2rem;
}
.lace{color:var(--tcl);font-size:1.1rem;letter-spacing:10px;}

/* cards */
.maker-card{
    background:white; border-radius:18px; padding:1.4rem;
    box-shadow:0 4px 20px rgba(181,68,42,.1);
    border:2px solid var(--tcp); text-align:center;
    position:relative; overflow:hidden;
}
.maker-card::before{
    content:''; position:absolute; top:0;left:0;right:0;
    height:5px; background:var(--tc);
}
.maker-name{font-family:'Playfair Display',serif;font-size:1.15rem;color:var(--dark);}
.maker-cut{font-size:1.9rem;font-weight:700;color:var(--tc);}
.maker-sales{font-size:.78rem;color:var(--tcl);margin-top:.2rem;}

/* sidebar */
section[data-testid="stSidebar"]{background:var(--dark) !important;}
section[data-testid="stSidebar"] *{color:var(--cream) !important;}
section[data-testid="stSidebar"] label{
    color:var(--tcp) !important; font-size:.78rem;
    text-transform:uppercase; letter-spacing:1px;
}

/* buttons */
.stButton>button{
    background:var(--tc) !important; color:white !important;
    border:none !important; border-radius:25px !important;
    padding:.45rem 1.5rem !important; font-weight:600 !important;
    width:100%; letter-spacing:.5px !important;
}
.stButton>button:hover{background:var(--dark) !important;}

/* metrics — force all text visible against white background */
[data-testid="metric-container"]{
    background:white; border-radius:14px; padding:.9rem;
    border:1.5px solid var(--tcp);
    box-shadow:0 2px 10px rgba(181,68,42,.08);
}
[data-testid="metric-container"] label,
[data-testid="metric-container"] p,
[data-testid="metric-container"] div,
[data-testid="metric-container"] span{
    color:var(--dark) !important;
    opacity:1 !important;
}
[data-testid="metric-container"] label{
    font-size:.72rem !important;
    text-transform:uppercase !important;
    letter-spacing:1px !important;
    font-weight:600 !important;
}
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] *,
[data-testid="stMetricValue"] div,
[data-testid="stMetricValue"] span{
    color:var(--tc) !important;
    font-family:'Playfair Display',serif !important;
    font-size:1.5rem !important;
    font-weight:700 !important;
    opacity:1 !important;
}
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] *{
    color:var(--tcl) !important;
    opacity:1 !important;
}

/* section titles */
.sec{
    font-family:'Playfair Display',serif; color:var(--dark);
    font-size:1.35rem; margin:1.5rem 0 .7rem;
    border-bottom:1.5px solid var(--tcp); padding-bottom:.3rem;
}

/* table tweaks */
[data-testid="stDataFrame"] th{
    background:var(--tcp) !important; color:var(--dark) !important;
}

/* admin badge */
.admin-badge{
    display:inline-block; background:var(--tc); color:white;
    font-size:.7rem; padding:2px 8px; border-radius:10px;
    font-weight:600; letter-spacing:1px; vertical-align:middle;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADERS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def load_products():
    """Load product catalog from products.csv"""
    if not os.path.exists(PRODUCTS_FILE):
        return pd.DataFrame(columns=["product_no","product_name","makers_cut",
                                     "profit","platform_40pct","total_cost"])
    df = pd.read_csv(PRODUCTS_FILE)
    df["product_no"] = df["product_no"].astype(str).str.zfill(2)
    return df

@st.cache_data(ttl=30)
def load_makers():
    """Load maker definitions from makers.csv"""
    if not os.path.exists(MAKERS_FILE):
        return pd.DataFrame(columns=["code","name","initials"])
    return pd.read_csv(MAKERS_FILE)

@st.cache_data(ttl=10)
def load_inventory():
    """Load full inventory list"""
    if not os.path.exists(INVENTORY_FILE):
        return pd.DataFrame(columns=["Product","Maker","Surname","Colour",
                                     "Amount","Cost","Product_ID"])
    return pd.read_csv(INVENTORY_FILE)

@st.cache_data(ttl=5)
def load_sales_csv():
    """Load raw sales CSV"""
    if not os.path.exists(SALES_FILE):
        return pd.DataFrame(columns=["Product_ID","Date","Note"])
    df = pd.read_csv(SALES_FILE)
    if "Product_ID" not in df.columns:
        return pd.DataFrame(columns=["Product_ID","Date","Note"])
    df = df.dropna(subset=["Product_ID"])
    df["Product_ID"] = df["Product_ID"].astype(str).str.strip()
    if "Date" not in df.columns:
        df["Date"] = ""
    if "Note" not in df.columns:
        df["Note"] = ""
    return df

def load_state():
    default = {"month_label": datetime.now().strftime("%B %Y")}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
            default.update(s)
        except:
            pass
    return default

def save_state(s):
    with open(STATE_FILE,"w") as f:
        json.dump(s, f, indent=2)

# ══════════════════════════════════════════════════════════════════════════════
# PRODUCT-ID PARSER
# ══════════════════════════════════════════════════════════════════════════════

def parse_pid(pid: str, makers_df: pd.DataFrame, products_df: pd.DataFrame):
    """
    Parse a Product_ID like DS01RAS-1300
    Returns dict with maker_code, maker_name, product_no, product_name,
                        makers_cut, colour_code, total_cost  — or None on failure.
    """
    pid = str(pid).strip().upper()

    # Find which maker code matches the start of the PID
    maker_row = None
    maker_code = None
    for _, row in makers_df.iterrows():
        code = str(row["code"]).upper()
        if pid.startswith(code):
            maker_row = row
            maker_code = code
            break

    if maker_row is None:
        return None

    remainder = pid[len(maker_code):]   # e.g. "01RAS-1300"

    # Extract 2-digit product number
    m = re.match(r"^(\d{2})(.*)", remainder)
    if not m:
        return None
    product_no = m.group(1)             # "01"
    rest = m.group(2)                   # "RAS-1300"

    # Look up product
    prod_row = products_df[products_df["product_no"] == product_no]
    if prod_row.empty:
        return None
    prod_row = prod_row.iloc[0]

    # Extract total_cost from end if present (after dash)
    total_cost_from_id = None
    dash_m = re.search(r"-(\d+)$", rest)
    if dash_m:
        total_cost_from_id = int(dash_m.group(1))

    return {
        "maker_code":   maker_code,
        "maker_name":   str(maker_row["name"]),
        "product_no":   product_no,
        "product_name": str(prod_row["product_name"]),
        "makers_cut":   float(prod_row["makers_cut"]),
        "total_cost":   total_cost_from_id or float(prod_row["total_cost"]),
        "colour_code":  rest.split("-")[0] if "-" in rest else rest,
        "pid":          pid,
    }

# ══════════════════════════════════════════════════════════════════════════════
# COMPUTE EARNINGS FROM SALES CSV
# ══════════════════════════════════════════════════════════════════════════════

def compute_earnings(sales_df, makers_df, products_df, month_filter=None):
    """
    Walk every row in sales_df, parse the Product_ID,
    accumulate makers_cut per maker.
    Returns:
        maker_earnings dict  { maker_name: { total_cut, sales_count, items[] } }
        enriched_sales list  [ row dict with parsed fields ]
        errors list
    """
    maker_earnings = {}
    for _, r in makers_df.iterrows():
        maker_earnings[str(r["name"])] = {"total_cut": 0.0, "sales_count": 0, "items": []}

    enriched = []
    errors = []

    for _, row in sales_df.iterrows():
        pid = str(row.get("Product_ID","")).strip()
        sale_date = str(row.get("Date","")).strip()
        note = str(row.get("Note","")).strip()

        # Month filter
        if month_filter:
            try:
                sd = datetime.strptime(sale_date[:10], "%Y-%m-%d")
                ym = sd.strftime("%Y-%m")
                if ym != month_filter:
                    continue
            except:
                pass  # if no date, include it

        parsed = parse_pid(pid, makers_df, products_df)
        if parsed is None:
            errors.append(f"Could not parse: {pid}")
            continue

        mname = parsed["maker_name"]
        cut   = parsed["makers_cut"]

        if mname not in maker_earnings:
            maker_earnings[mname] = {"total_cut": 0.0, "sales_count": 0, "items": []}

        maker_earnings[mname]["total_cut"]    += cut
        maker_earnings[mname]["sales_count"]  += 1
        maker_earnings[mname]["items"].append(parsed)

        enriched.append({
            "Date":         sale_date,
            "Product ID":   pid,
            "Maker":        mname,
            "Product":      parsed["product_name"],
            "Colour":       parsed["colour_code"],
            "Maker's Cut":  f"₹{cut:,.0f}",
            "Total Cost":   f"₹{parsed['total_cost']:,.0f}",
            "Note":         note,
        })

    return maker_earnings, enriched, errors

# ══════════════════════════════════════════════════════════════════════════════
# SALES CSV WRITER
# ══════════════════════════════════════════════════════════════════════════════

def append_sale_to_csv(pid, note=""):
    """Append a new sale row to sales.csv"""
    row = pd.DataFrame([{
        "Product_ID": pid.strip().upper(),
        "Date": str(date.today()),
        "Note": note,
    }])
    if os.path.exists(SALES_FILE) and os.path.getsize(SALES_FILE) > 10:
        row.to_csv(SALES_FILE, mode="a", header=False, index=False)
    else:
        row.to_csv(SALES_FILE, index=False)
    load_sales_csv.clear()  # bust cache

# ══════════════════════════════════════════════════════════════════════════════
# LOAD ALL DATA
# ══════════════════════════════════════════════════════════════════════════════

products_df  = load_products()
makers_df    = load_makers()
inventory_df = load_inventory()
sales_df     = load_sales_csv()
state        = load_state()

month_lbl    = state.get("month_label", datetime.now().strftime("%B %Y"))

# Determine current month filter (YYYY-MM)
try:
    month_filter = datetime.strptime(month_lbl, "%B %Y").strftime("%Y-%m")
except:
    month_filter = None

# Compute
maker_earnings, enriched_sales, parse_errors = compute_earnings(
    sales_df, makers_df, products_df, month_filter
)
all_earnings, all_enriched, _ = compute_earnings(
    sales_df, makers_df, products_df, None
)

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## lokarichhokri")
    st.markdown("---")

    role = st.radio("View as", ["Admin", "Maker"], label_visibility="collapsed")
    is_admin = (role == "Admin")

    if is_admin:
        st.markdown('<span class="admin-badge">ADMIN</span>', unsafe_allow_html=True)
        st.markdown("### Record a Sale")

        entry_mode = st.radio("", ["Type Product ID", "Pick from Inventory"], label_visibility="collapsed")

        if entry_mode == "Type Product ID":
            pid_in = st.text_input("Product ID", placeholder="DS01RAS-1300").strip().upper()
            note_in = st.text_input("Note (optional)")
            if st.button("Record Sale"):
                if pid_in:
                    parsed = parse_pid(pid_in, makers_df, products_df)
                    if parsed:
                        append_sale_to_csv(pid_in, note_in)
                        st.success(f"Recorded! ₹{parsed['makers_cut']:,.0f} → {parsed['maker_name']}")
                        st.rerun()
                    else:
                        st.error("Could not parse this Product ID. Check maker code and product number.")
                else:
                    st.warning("Enter a Product ID first.")

        else:
            if not inventory_df.empty and "Product_ID" in inventory_df.columns:
                inv_ids = inventory_df["Product_ID"].dropna().astype(str).tolist()
                # Show unsold only
                sold_ids = set(sales_df["Product_ID"].astype(str).tolist())
                unsold = [x for x in inv_ids if x not in sold_ids]
                if unsold:
                    chosen = st.selectbox("Select item sold", unsold)
                    note_in2 = st.text_input("Note (optional)", key="note2")
                    if st.button("Record Sale", key="btn2"):
                        parsed = parse_pid(chosen, makers_df, products_df)
                        if parsed:
                            append_sale_to_csv(chosen, note_in2)
                            st.success(f"Recorded! ₹{parsed['makers_cut']:,.0f} → {parsed['maker_name']}")
                            st.rerun()
                        else:
                            st.error("Could not parse this Product ID.")
                else:
                    st.info("All inventory items recorded as sold.")
            else:
                st.warning("No inventory loaded. Upload inventory.csv")

        st.markdown("---")
        st.markdown("### Upload Files")

        with st.expander("Upload Sales CSV"):
            st.caption("Columns: Product_ID, Date (YYYY-MM-DD), Note")
            up_sales = st.file_uploader("sales.csv", type="csv", key="up_sales")
            if up_sales:
                try:
                    df_up = pd.read_csv(up_sales)
                    df_up.to_csv(SALES_FILE, index=False)
                    load_sales_csv.clear()
                    st.success("Sales file updated!")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        with st.expander("Upload Inventory CSV"):
            st.caption("Columns: Product, Maker, Surname, Colour, Amount, Cost, Product_ID")
            up_inv = st.file_uploader("inventory.csv", type="csv", key="up_inv")
            if up_inv:
                try:
                    df_up = pd.read_csv(up_inv)
                    df_up.to_csv(INVENTORY_FILE, index=False)
                    load_inventory.clear()
                    st.success("Inventory updated!")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        with st.expander("Upload Product Catalog"):
            st.caption("Columns: product_no, product_name, makers_cut, profit, platform_40pct, total_cost")
            up_prod = st.file_uploader("products.csv", type="csv", key="up_prod")
            if up_prod:
                try:
                    df_up = pd.read_csv(up_prod)
                    df_up.to_csv(PRODUCTS_FILE, index=False)
                    load_products.clear()
                    st.success("Product catalog updated!")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        st.markdown("---")
        st.markdown("### Month")
        new_month = st.text_input("Current month", value=month_lbl)
        if st.button("Set Month"):
            state["month_label"] = new_month
            save_state(state)
            st.success(f"Month set to {new_month}")
            st.rerun()

    else:
        # Maker view — pick name
        maker_names = makers_df["name"].tolist() if not makers_df.empty else []
        selected_maker = st.selectbox("Select your name", maker_names)
        st.markdown(f"Viewing earnings for **{selected_maker}**")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:1.8rem 0 0.2rem;">
    <h1 class="brand-title">lokarichhokri</h1>
    <p class="brand-sub">Crochet · Craft · Create</p>
    <div class="lace">✦ ✿ ✦ ✿ ✦</div>
</div>
""", unsafe_allow_html=True)

st.markdown(f'<div style="text-align:center;color:#8B3A3A;font-size:.85rem;'
            f'letter-spacing:2px;margin-bottom:1.2rem;">{month_lbl.upper()}</div>',
            unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAKER VIEW — simplified personal dashboard
# ══════════════════════════════════════════════════════════════════════════════

if not is_admin:
    me = selected_maker
    my_data = maker_earnings.get(me, {"total_cut":0,"sales_count":0,"items":[]})
    my_all  = all_earnings.get(me, {"total_cut":0,"sales_count":0,"items":[]})

    st.markdown(f'<div class="sec">Your Earnings — {me}</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("This Month's Cut", f"₹{my_data['total_cut']:,.0f}")
    c2.metric("Items Sold This Month", my_data["sales_count"])
    c3.metric("Total Earned (all time)", f"₹{my_all['total_cut']:,.0f}")

    st.markdown('<div class="sec">Your Sales This Month</div>', unsafe_allow_html=True)
    my_sales = [s for s in enriched_sales if s["Maker"] == me]
    if my_sales:
        st.dataframe(pd.DataFrame(my_sales)[["Date","Product ID","Product","Colour","Maker's Cut","Note"]],
                     use_container_width=True, hide_index=True)
    else:
        st.info("No sales recorded for you this month yet.")

    st.markdown("""
    <div style="text-align:center;padding:2rem 0 .5rem;color:#D4896A;font-size:.78rem;">
        ✦ ✿ ✦ &nbsp; lokarichhokri &nbsp; ✦ ✿ ✦
    </div>""", unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN VIEW
# ══════════════════════════════════════════════════════════════════════════════

# ── Maker earnings cards ──────────────────────────────────────────────────────
st.markdown('<div class="sec">Maker Earnings — This Month</div>', unsafe_allow_html=True)

total_cut = sum(v["total_cut"] for v in maker_earnings.values())
mcols = st.columns(max(len(makers_df), 1))

for i, (_, mrow) in enumerate(makers_df.iterrows()):
    mname = str(mrow["name"])
    mcode = str(mrow["code"])
    mdata = maker_earnings.get(mname, {"total_cut":0,"sales_count":0})
    pct   = (mdata["total_cut"]/total_cut*100) if total_cut else 0
    with mcols[i]:
        st.markdown(f"""
        <div class="maker-card">
            <div class="maker-name">{mname}</div>
            <div style="font-family:monospace;font-size:.72rem;background:#F2D4C8;
                        border-radius:6px;padding:1px 7px;display:inline-block;
                        color:#6B1F1F;margin:.25rem 0;">{mcode}</div>
            <div class="maker-cut">₹{mdata['total_cut']:,.0f}</div>
            <div class="maker-sales">{mdata['sales_count']} items · {pct:.1f}% of total</div>
        </div>
        """, unsafe_allow_html=True)

# ── Summary metrics ───────────────────────────────────────────────────────────
st.markdown('<div class="sec">Summary</div>', unsafe_allow_html=True)

total_revenue_all = sum(v["total_cut"] for v in all_earnings.values())
s1,s2,s3,s4 = st.columns(4)
s1.metric("Total Maker Cuts This Month", f"₹{total_cut:,.0f}")
s2.metric("Sales This Month", len(enriched_sales))
s3.metric("Total Sales Ever", len(sales_df))
if maker_earnings:
    best = max(maker_earnings, key=lambda k: maker_earnings[k]["total_cut"])
    s4.metric("Top Earner", best)

# ── Profit split chart ────────────────────────────────────────────────────────
if total_cut > 0:
    st.markdown('<div class="sec">Profit Split</div>', unsafe_allow_html=True)
    ch1, ch2 = st.columns(2)

    with ch1:
        labels = [str(r["name"]) for _,r in makers_df.iterrows()]
        values = [maker_earnings.get(str(r["name"]),{"total_cut":0})["total_cut"]
                  for _,r in makers_df.iterrows()]
        fig = go.Figure(go.Pie(
            labels=labels, values=values, hole=.55,
            marker_colors=["#B5442A","#8B3A3A","#D4896A","#c0392b"],
            textfont_size=12,
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_family="Poppins", showlegend=True,
            margin=dict(t=10,b=10,l=10,r=10), height=260,
            annotations=[dict(text=f"₹{total_cut:,.0f}",x=.5,y=.5,
                              font_size=13,showarrow=False,
                              font_color="#6B1F1F",font_family="Playfair Display")]
        )
        st.plotly_chart(fig, use_container_width=True)

    with ch2:
        if enriched_sales:
            prod_totals = {}
            for s in enriched_sales:
                cut_val = float(str(s["Maker's Cut"]).replace("₹","").replace(",",""))
                prod_totals[s["Product"]] = prod_totals.get(s["Product"],0) + cut_val
            fig2 = go.Figure(go.Bar(
                x=list(prod_totals.values()), y=list(prod_totals.keys()),
                orientation="h", marker_color="#B5442A",
                marker_line_color="#6B1F1F", marker_line_width=1,
            ))
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_family="Poppins", xaxis_title="Maker's Cut (₹)",
                height=260, margin=dict(t=10,b=10,l=10,r=10),
            )
            st.plotly_chart(fig2, use_container_width=True)

# ── Sales log ─────────────────────────────────────────────────────────────────
st.markdown('<div class="sec">Sales This Month</div>', unsafe_allow_html=True)

if enriched_sales:
    df_show = pd.DataFrame(enriched_sales)
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    csv_out = df_show.to_csv(index=False)
    st.download_button(
        "Download Sales Report (CSV)", csv_out,
        file_name=f"lokarichhokri_{month_lbl.replace(' ','_')}.csv",
        mime="text/csv"
    )
else:
    st.info("No sales recorded this month. Add entries to sales.csv or use the sidebar.")

# ── Parse errors ──────────────────────────────────────────────────────────────
if parse_errors:
    with st.expander(f"Parse errors ({len(parse_errors)})"):
        for e in parse_errors:
            st.warning(e)

# ── Product catalog ───────────────────────────────────────────────────────────
st.markdown('<div class="sec">Product Catalog</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["Product List", "Inventory", "Edit Catalog"])

with tab1:
    if not products_df.empty:
        display_p = products_df.copy()
        display_p.columns = ["No.", "Product Name","Maker's Cut (₹)","Profit (₹)","Platform 40% (₹)","Total Cost (₹)"]
        st.dataframe(display_p, use_container_width=True, hide_index=True)
    else:
        st.info("No products.csv found. Upload one from the sidebar.")

with tab2:
    if not inventory_df.empty:
        sold_ids = set(sales_df["Product_ID"].astype(str).tolist())
        inv_show = inventory_df.copy()
        inv_show["Status"] = inv_show["Product_ID"].apply(
            lambda x: "Sold" if str(x) in sold_ids else "Available"
        )
        st.dataframe(inv_show, use_container_width=True, hide_index=True)
        avail = (inv_show["Status"] == "Available").sum()
        sold  = (inv_show["Status"] == "Sold").sum()
        ia, ib = st.columns(2)
        ia.metric("Available", avail)
        ib.metric("Sold", sold)
    else:
        st.info("No inventory.csv found. Upload one from the sidebar.")

with tab3:
    st.caption("Edit the product catalog inline. Changes save to products.csv.")
    if not products_df.empty:
        edited = st.data_editor(
            products_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "product_no":     st.column_config.TextColumn("No.", width="small"),
                "product_name":   st.column_config.TextColumn("Product Name"),
                "makers_cut":     st.column_config.NumberColumn("Maker's Cut ₹", min_value=0),
                "profit":         st.column_config.NumberColumn("Profit ₹", min_value=0),
                "platform_40pct": st.column_config.NumberColumn("Platform 40% ₹", min_value=0),
                "total_cost":     st.column_config.NumberColumn("Total Cost ₹", min_value=0),
            },
            hide_index=True,
            key="prod_editor"
        )
        if st.button("Save Product Catalog"):
            edited.to_csv(PRODUCTS_FILE, index=False)
            load_products.clear()
            st.success("Product catalog saved!")
            st.rerun()
    else:
        st.info("Upload a products.csv first.")

# ── Product ID key ────────────────────────────────────────────────────────────
st.markdown('<div class="sec">Product ID Key</div>', unsafe_allow_html=True)

st.markdown("""
<div style="background:white;border-radius:14px;padding:1.2rem 1.5rem;
            border:1.5px solid #F2D4C8;box-shadow:0 2px 8px rgba(181,68,42,.07);
            font-size:.88rem;color:#6B1F1F;line-height:2;">
<b>Format:</b> &nbsp;<code style="background:#F2D4C8;padding:2px 8px;border-radius:6px;
font-size:.95rem;">{MAKER_CODE}{PRODUCT_NO:02d}{COLOUR_SHORT}-{TOTAL_COST}</code><br>
<b>Example:</b> &nbsp;<code style="background:#F2D4C8;padding:2px 8px;border-radius:6px;">DS01RAS-1300</code>
&nbsp;→ Dhruva (DS) · Tulip Coaster (01) · Raspberry colour · ₹1300 total cost<br>
<b>Earning logic:</b> &nbsp;Product number (01–08) maps to Maker's Cut in the product catalog above.
</div>
""", unsafe_allow_html=True)

if not makers_df.empty:
    key_cols = st.columns(len(makers_df))
    for i, (_, r) in enumerate(makers_df.iterrows()):
        with key_cols[i]:
            st.markdown(f"""
            <div style="background:white;border-radius:10px;padding:.8rem;
                        border:1.5px solid #F2D4C8;margin-top:.5rem;text-align:center;">
                <div style="font-weight:600;color:#6B1F1F;">{r['name']}</div>
                <div style="font-family:monospace;font-size:1.1rem;color:#B5442A;
                            background:#F2D4C8;border-radius:6px;padding:2px 10px;
                            display:inline-block;margin:.3rem 0;">{r['code']}</div>
            </div>
            """, unsafe_allow_html=True)

if not products_df.empty:
    st.markdown("<div style='margin-top:.8rem;'></div>", unsafe_allow_html=True)
    p_cols = st.columns(4)
    for i, (_, r) in enumerate(products_df.iterrows()):
        with p_cols[i % 4]:
            st.markdown(f"""
            <div style="background:white;border-radius:10px;padding:.7rem;
                        border:1.5px solid #F2D4C8;margin-bottom:.5rem;
                        box-shadow:0 2px 6px rgba(181,68,42,.06);">
                <div style="font-family:monospace;font-size:.85rem;color:#B5442A;
                            font-weight:700;">{r['product_no']}</div>
                <div style="font-weight:600;color:#6B1F1F;font-size:.88rem;">{r['product_name']}</div>
                <div style="color:#D4896A;font-size:.75rem;">
                    Maker's cut: ₹{r['makers_cut']:,.0f} &nbsp;|&nbsp; Total: ₹{r['total_cost']:,.0f}
                </div>
            </div>
            """, unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:2rem 0 .8rem;color:#D4896A;font-size:.78rem;">
    ✦ ✿ ✦ &nbsp; lokarichhokri &nbsp; ✦ ✿ ✦
</div>
""", unsafe_allow_html=True)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from fraud_detector import load_transactions, make_transactions, score_dataframe

st.set_page_config(page_title="Fraud Shield", page_icon="🐀", layout="wide")

st.title("Fraud Shield for small businesses")
st.caption("Finds suspicious payments and refunds before the money is gone.")

with st.sidebar:
    st.header("Settings")
    alert_pct = st.slider("Flag the most unusual % of transactions", 0.5, 5.0, 1.0, 0.5,
                          help="Lower means fewer alerts. Higher catches more fraud but means more false alarms.")
    st.markdown("---")
    st.markdown(
        "**How it works**\n\n"
        "For every transaction the model looks at how far it is from the most similar normal "
        "transactions (KNN). Amount compared to that customer's usual, time of day, refunds, "
        "and how many charges happened in the last hour all count. Far from everything normal "
        "means suspicious."
    )

TEMPLATE = (
    "customer,timestamp,amount,is_refund,is_fraud\n"
    "C0001,2026-03-02 09:15:00,4.50,0,0\n"
    "C0002,2026-03-02 09:42:10,12.00,0,0\n"
    "C0001,2026-03-03 09:20:30,4.75,0,0\n"
    "C0003,2026-03-03 14:05:00,8.25,1,0\n"
)


def pretty_demo():
    # one built-in demo: regulars with six months of history, fraud that stands out
    df = make_transactions(n=5000, fraud_rate=0.01, n_customers=120, seed=7, scale=0.5, noise=0.0, days=180)
    df["customer"] = [f"C{int(c):04d}" for c in df["customer"]]
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.round("s")
    df["amount"] = df["amount"].round(2)
    return df.sort_values("timestamp").reset_index(drop=True)


@st.cache_data(show_spinner="Building the demo data (runs once)...")
def demo_data():
    return pretty_demo()


@st.cache_data(show_spinner="Scoring transactions (runs once)...")
def run_scoring(raw):
    # the model is fit one time. reasons are written for the top 5% so the slider can go up to 5%
    # without running anything again, it only moves the alert line
    df, model, _ = score_dataframe(raw, alert_pct=5.0, clean_pct=2.0)
    return df, model.k


source = st.radio("Data", ["Demo data", "Upload my CSV"], horizontal=True)
raw = None
if source == "Demo data":
    st.caption("This demo uses made-up data where each customer has months of history and the fraud "
               "is fairly easy to spot. Real data is messier, so expect lower accuracy there.")
    raw = demo_data()
else:
    st.info(
        "CSV tip: use these columns, in this order\n\n"
        "1. `customer`: who paid (a name or ID)\n"
        "2. `timestamp`: date and time, like `2026-03-02 09:15:00`\n"
        "3. `amount`: a number, like `4.50`\n"
        "4. `is_refund` (optional): `1` if it was a refund, otherwise `0`\n"
        "5. `is_fraud` (optional): `1` if you already know it was fraud. It is only used to show how "
        "many real frauds were caught, never to find them.\n\n"
        "Column names must match exactly (capital letters don't matter) and the order above is the "
        "safe one. One row per transaction, no blank rows. Dollar signs are fine.\n\n"
        "It works best with at least a few hundred transactions and several past purchases per customer, "
        "because it learns what is normal for each customer."
    )
    st.code(TEMPLATE, language="csv")
    st.download_button("Download this example as a template", TEMPLATE, "transactions_template.csv", "text/csv")
    up = st.file_uploader("Transaction export (CSV)", type="csv")
    if up is not None:
        try:
            raw, skipped = load_transactions(up)
            if skipped:
                st.warning(f"Skipped {skipped} rows with a missing or unreadable customer, timestamp or amount.")
        except ValueError as e:
            st.error(str(e))
        except Exception:
            st.error("Could not read that file as a CSV. Check that it matches the tip above.")

if raw is not None:
    df, k = run_scoring(raw)
    thr = np.percentile(df["fraud_score"], 100 - alert_pct)
    flagged = df[df["fraud_score"] >= thr].sort_values("fraud_score", ascending=False)
    has_labels = "is_fraud" in df.columns

    cols = st.columns(4)
    cols[0].metric("Transactions scanned", f"{len(df):,}")
    cols[1].metric("Flagged for review", f"{len(flagged):,}")
    if has_labels:
        caught = int(flagged["is_fraud"].sum())
        total = int(df["is_fraud"].sum())
        cols[2].metric("Real frauds caught", f"{caught} of {total}")
        cols[3].metric("Fraud dollars caught", f"${flagged.loc[flagged['is_fraud'] == 1, 'amount'].sum():,.0f}")
    else:
        cols[2].metric("Dollars in flagged items", f"${flagged['amount'].sum():,.0f}")
        cols[3].metric("Average flagged amount", f"${flagged['amount'].mean():,.0f}")

    st.subheader("Transactions to review")
    show = flagged[["timestamp", "customer", "amount", "is_refund", "fraud_score", "reasons"]].copy()
    show["amount"] = show["amount"].round(2)
    show["fraud_score"] = show["fraud_score"].round(2)
    show["is_refund"] = show["is_refund"].astype(bool)
    if has_labels:
        show.insert(0, "really fraud?", np.where(flagged["is_fraud"] == 1, "yes", "no"))
    st.dataframe(show, hide_index=True, height=420)
    st.download_button("Download flagged list (CSV)", show.to_csv(index=False),
                       "flagged_transactions.csv", "text/csv")

    st.subheader("Where the alert line sits")
    fig, ax = plt.subplots(figsize=(9, 3))
    top = np.percentile(df["fraud_score"], 99.7)
    bins = np.linspace(df["fraud_score"].min(), top, 60)
    if has_labels:
        ax.hist(df.loc[df["is_fraud"] == 0, "fraud_score"].clip(upper=top), bins=bins, alpha=0.7, label="normal")
        ax.hist(df.loc[df["is_fraud"] == 1, "fraud_score"].clip(upper=top), bins=bins, alpha=0.8, label="fraud")
    else:
        ax.hist(df["fraud_score"].clip(upper=top), bins=bins, alpha=0.8, label="all transactions")
    ax.axvline(thr, color="k", ls="--", label="alert line")
    ax.set_xlabel("unusualness score (higher = more suspicious)")
    ax.set_yscale("log")
    ax.legend()
    st.pyplot(fig)
    plt.close(fig)
    st.caption(f"The model compared each transaction with its {k} nearest neighbors.")
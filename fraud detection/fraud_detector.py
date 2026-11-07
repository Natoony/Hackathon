import argparse

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import average_precision_score, precision_recall_curve

# usage:
#   python fraud_detector.py                    run on fake data
#   python fraud_detector.py --runs 5           repeat with 5 seeds and average
#   python fraud_detector.py --interactive      check one transaction by hand
#   python fraud_detector.py --csv file.csv     score a real export
# csv needs: customer, timestamp, amount (optional: is_refund, is_fraud)

BASE_DATE = pd.Timestamp("2026-01-01")

FEATURES = ["log_amount", "hour_sin", "hour_cos", "is_refund",
            "log_gap", "amount_vs_usual", "hour_dev", "recent_count"]

# how much each feature counts in the distance. amount compared to the customer's
# normal matters most, the two hour features together would double count time of day
WEIGHTS = np.array([1, 0.5, 0.5, 1, 1, 3, 1.5, 1])

# a customer needs at least this many other transactions before we trust their own "usual"
MIN_HISTORY = 3


def make_transactions(n=20000, fraud_rate=0.01, n_customers=300, seed=42, scale=1.0, noise=1.0, days=90):
    # scale multiplies every amount (a cafe is small, a boutique is bigger)
    # noise controls how many odd-but-legit transactions there are (1.0 = the hard test setting)
    rng = np.random.default_rng(seed)
    usual = rng.lognormal(3.0, 0.6, n_customers)

    # most customers shop in the daytime, some in the evening, a few late at night
    kind = rng.choice(3, n_customers, p=[0.8, 0.12, 0.08])
    center = np.where(kind == 0, rng.uniform(10, 16, n_customers),
                      np.where(kind == 1, rng.uniform(19, 21, n_customers),
                               rng.uniform(23, 25, n_customers)))
    visits = rng.lognormal(0, 0.8, n_customers)
    visits = visits / visits.sum()

    n_fraud = max(int(n * fraud_rate), 5)
    n_legit = n - n_fraud
    n_rep = int(n_legit * 0.04 * noise)
    n_base = n_legit - n_rep

    # normal transactions, including some big purchases and refunds
    cust = rng.choice(n_customers, n_base, p=visits)
    base = usual[cust] * rng.lognormal(0, 0.35, n_base)
    refund = (rng.random(n_base) < 0.03).astype(int)
    big = (rng.random(n_base) < 0.03 * noise) & (refund == 0)
    amount = np.where(refund == 1, base * rng.uniform(0.3, 1.0, n_base), base)
    amount = np.where(big, base * rng.uniform(2, 4, n_base), amount)
    hour = (center[cust] + rng.normal(0, 2, n_base)) % 24
    day = rng.integers(0, days, n_base)
    minute = day * 1440 + hour * 60
    legit = pd.DataFrame({
        "customer": cust, "amount": amount, "is_refund": refund,
        "minute": minute, "is_fraud": 0,
    })

    # normal customers sometimes buy again a few minutes later
    pick = rng.choice(n_base, n_rep, replace=False)
    repeat = pd.DataFrame({
        "customer": cust[pick], "amount": amount[pick] * rng.uniform(0.3, 1.5, n_rep),
        "is_refund": 0, "minute": minute[pick] + rng.uniform(1, 10, n_rep), "is_fraud": 0,
    })

    # fraud: night purchase, big refund, card testing burst, account takeover
    rows = []
    while len(rows) < n_fraud:
        c = int(rng.integers(0, n_customers))
        d = int(rng.integers(0, days))
        u = usual[c]
        day_min = d * 1440
        kind = rng.choice(["night", "refund", "burst", "takeover"], p=[0.3, 0.2, 0.25, 0.25])
        if kind == "night":
            rows.append((c, u * rng.uniform(4, 12), 0, day_min + rng.uniform(0, 5) * 60))
        elif kind == "refund":
            t = ((center[c] + rng.normal(0, 2)) % 24) * 60
            rows.append((c, u * rng.uniform(2, 5), 1, day_min + t))
        elif kind == "burst":
            t = day_min + rng.uniform(8, 22) * 60
            for _ in range(int(rng.integers(3, 6))):
                rows.append((c, rng.uniform(1, 4), 0, t))
                t += rng.uniform(0.5, 2)
            if rng.random() < 0.5:
                rows.append((c, u * rng.uniform(3, 8), 0, t))
        else:
            t = ((center[c] + rng.normal(0, 2)) % 24) * 60
            rows.append((c, u * rng.uniform(4, 9), 0, day_min + t))
    fraud = pd.DataFrame(rows[:n_fraud], columns=["customer", "amount", "is_refund", "minute"])
    fraud["is_fraud"] = 1

    df = pd.concat([legit, repeat, fraud], ignore_index=True)
    df["timestamp"] = BASE_DATE + pd.to_timedelta(df["minute"], unit="m")
    df["amount"] = df["amount"] * scale
    return df.drop(columns="minute")


def hour_gap(hour, typical):
    # distance between two times of day in hours (0 to 12), wraps around midnight
    return np.abs((hour - typical + 12) % 24 - 12)


def engineer(amount, usual, hour, typical_hour, is_refund, gap, recent):
    amount = np.atleast_1d(np.asarray(amount, float))
    usual = np.atleast_1d(np.asarray(usual, float))
    hour = np.atleast_1d(np.asarray(hour, float))
    typical_hour = np.atleast_1d(np.asarray(typical_hour, float))
    is_refund = np.atleast_1d(np.asarray(is_refund, float))
    gap = np.atleast_1d(np.asarray(gap, float))
    recent = np.atleast_1d(np.asarray(recent, float))
    return np.column_stack([
        np.log1p(amount),
        np.sin(2 * np.pi * hour / 24),  # hour as a circle so 23:00 is close to 00:00
        np.cos(2 * np.pi * hour / 24),
        is_refund,
        np.log1p(gap),
        np.log((amount + 1) / (usual + 1)),  # compared to this customer's normal
        hour_gap(hour, typical_hour),
        np.log1p(recent),
    ])


def loo_median(v):
    # median of the other values for every element (leave one out)
    m = len(v)
    s = np.sort(v)
    r = np.argsort(np.argsort(v, kind="stable"), kind="stable")
    L = m - 1

    def rem(j):
        return np.where(j < r, s[j], s[j + 1])

    if L % 2:
        return rem(L // 2)
    return (rem(L // 2 - 1) + rem(L // 2)) / 2


def prepare(df):
    df = df.copy()
    if "is_refund" not in df:
        df["is_refund"] = 0
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["customer", "timestamp"]).reset_index(drop=True)

    codes = pd.factorize(df["customer"])[0]
    cuts = np.flatnonzero(np.diff(codes)) + 1
    starts = np.r_[0, cuts]
    sizes = np.diff(np.r_[starts, len(df)])
    groups = np.split(np.arange(len(df)), cuts)

    mins = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds().to_numpy() / 60
    amount = df["amount"].to_numpy(float)
    hour = (df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60).to_numpy(float)

    # minutes since this customer's previous transaction
    gap = np.r_[np.nan, np.diff(mins)]
    gap[starts] = np.nan
    gap = np.where(np.isnan(gap), np.nanmedian(gap) if np.isfinite(gap).any() else 10080, gap)

    # what's normal for this customer, not counting the transaction itself
    usual = np.full(len(df), np.nan)
    for idx in groups:
        if len(idx) >= MIN_HISTORY + 1:
            usual[idx] = loo_median(amount[idx])
    usual[np.isnan(usual)] = np.median(amount)

    ang = 2 * np.pi * hour / 24
    s, c = np.sin(ang), np.cos(ang)
    s_loo = np.repeat(np.add.reduceat(s, starts), sizes) - s
    c_loo = np.repeat(np.add.reduceat(c, starts), sizes) - c
    typical = (np.arctan2(s_loo, c_loo) % (2 * np.pi)) * 24 / (2 * np.pi)
    all_typical = (np.arctan2(s.sum(), c.sum()) % (2 * np.pi)) * 24 / (2 * np.pi)
    typical[np.repeat(sizes, sizes) < MIN_HISTORY + 1] = all_typical

    # how many transactions this customer made in the hour before
    key = codes * (mins.max() + 100000) + mins
    recent = np.arange(len(df)) - np.searchsorted(key, key - 60, side="left")

    df["min_since_last"] = gap
    df["usual"] = usual
    df["hour"] = hour
    df["typical_hour"] = typical
    df["recent"] = recent

    X = engineer(amount, usual, hour, typical, df["is_refund"], gap, recent)
    return df, X


class Standardizer:
    def fit(self, X):
        self.mean_ = X.mean(axis=0)
        self.std_ = X.std(axis=0)
        self.std_[self.std_ == 0] = 1.0
        return self

    def transform(self, X):
        return (X - self.mean_) / self.std_

    def fit_transform(self, X):
        return self.fit(X).transform(X)


class KNNAnomalyDetector:
    # score = average distance to the k closest transactions, bigger = more suspicious
    def __init__(self, k=10, metric="euclidean", chunk=400):
        self.k, self.metric, self.chunk = k, metric, chunk

    def fit(self, X):
        self.X_ref = np.asarray(X, float)
        self._sq = (self.X_ref ** 2).sum(axis=1)
        return self

    def _distances(self, A):
        if self.metric == "euclidean":
            d2 = (A ** 2).sum(axis=1)[:, None] + self._sq[None, :] - 2 * A @ self.X_ref.T
            return np.sqrt(np.maximum(d2, 0))
        if self.metric == "manhattan":
            return np.abs(A[:, None, :] - self.X_ref[None, :, :]).sum(axis=2)
        raise ValueError("Unsupported distance metric")

    def score_many(self, X, ks, self_idx=None):
        # one pass that gives the score for several values of k
        # self_idx[i] = position of row i inside the reference set (-1 if not in it),
        # so a point is never counted as its own neighbor
        X = np.asarray(X, float)
        kmax = min(max(ks), len(self.X_ref) - 1)
        step = self.chunk if self.metric == "euclidean" else 50
        out = np.empty((len(X), len(ks)))
        for start in range(0, len(X), step):
            d = self._distances(X[start:start + step])
            if self_idx is not None:
                idx = self_idx[start:start + step]
                ok = idx >= 0
                d[np.flatnonzero(ok), idx[ok]] = np.inf
            near = np.sort(np.partition(d, kmax - 1, axis=1)[:, :kmax], axis=1)
            cum = np.cumsum(near, axis=1)
            for j, k in enumerate(ks):
                k = min(k, kmax)
                out[start:start + step, j] = cum[:, k - 1] / k
        return out

    def score(self, X, self_idx=None):
        return self.score_many(X, [self.k], self_idx)[:, 0]


class FraudModel:
    # standardize -> throw out the most suspicious reference rows -> knn score
    def __init__(self, k=None, clean_pct=2.0, clean_k=50, default_k=50,
                 candidates=(10, 20, 50, 100, 150), weights=WEIGHTS):
        self.k, self.clean_pct, self.clean_k = k, clean_pct, clean_k
        self.default_k, self.candidates, self.weights = default_k, candidates, weights

    def _prep(self, X):
        return self.scaler.transform(X) * self.weights

    def fit(self, X, X_val=None, y_val=None):
        self.scaler = Standardizer().fit(X)
        Xs = self._prep(X)
        n = len(Xs)
        self_idx = np.arange(n)
        ref = Xs

        # frauds sitting in the reference make other frauds look normal,
        # so drop the top few percent before scoring (no labels needed)
        if self.clean_pct > 0 and n > 20:
            first = KNNAnomalyDetector(min(self.clean_k, n - 1)).fit(Xs)
            s = first.score(Xs, self_idx)
            keep = s < np.percentile(s, 100 - self.clean_pct)
            ref = Xs[keep]
            self_idx = np.full(n, -1)
            self_idx[keep] = np.arange(keep.sum())

        knn = KNNAnomalyDetector(1).fit(ref)
        self.cv_ = {}
        if self.k is None:
            if X_val is not None:
                ks = [k for k in self.candidates if k < len(ref)]
                sc = knn.score_many(self._prep(X_val), ks)
                aucs = [average_precision_score(y_val, sc[:, i]) for i in range(len(ks))]
                self.cv_ = dict(zip(ks, aucs))
                self.k = ks[int(np.argmax(aucs))]
            else:
                self.k = self.default_k
        knn.k = min(self.k, len(ref) - 1)
        self.knn = knn
        self.train_scores = knn.score(Xs, self_idx)
        return self

    def score(self, X):
        return self.knn.score(self._prep(X))


def fmt_hour(h):
    hh = int(h) % 24
    mm = int(round((h - int(h)) * 60)) % 60
    return f"{(hh % 12) or 12}:{mm:02d} {'AM' if hh < 12 else 'PM'}"


def explain(row, z, top=3):
    # turn the most unusual features of a transaction into plain english
    reasons, seen = [], set()
    for j in np.argsort(-np.abs(z)):
        if abs(z[j]) < 1.5 or len(reasons) >= top:
            break
        name = FEATURES[j]
        key, text = name, None
        if name in ("amount_vs_usual", "log_amount"):
            key = "amount"
            ratio = (row["amount"] + 1) / (row["usual"] + 1)
            if ratio >= 1.5:
                text = f"amount ${row['amount']:,.2f} is {ratio:.1f}x this customer's usual ${row['usual']:,.2f}"
            elif ratio <= 0.5:
                text = f"tiny charge (${row['amount']:,.2f}) compared to their usual ${row['usual']:,.2f}"
        elif name in ("hour_dev", "hour_sin", "hour_cos"):
            key = "hour"
            dev = hour_gap(row["hour"], row["typical_hour"])
            if dev >= 4:
                text = (f"at {fmt_hour(row['hour'])}, {dev:.0f} hours away from when this "
                        f"customer usually shops ({fmt_hour(row['typical_hour'])})")
        elif name == "recent_count":
            n = int(row["recent"])
            if n >= 1:
                text = f"{n} other charge{'s' if n > 1 else ''} in the previous hour"
        elif name == "log_gap":
            if row["min_since_last"] < 10:
                text = f"only {row['min_since_last']:.1f} minutes after their previous charge"
        elif name == "is_refund":
            if row["is_refund"]:
                text = "it is a refund"
        if text and key not in seen:
            reasons.append(text)
            seen.add(key)
    return "; ".join(reasons) if reasons else "unusual mix of amount, time and activity"


def score_dataframe(raw, alert_pct=1.0, k=None, clean_pct=None):
    # fit on the data itself and flag the top alert_pct percent, with reasons
    df, X = prepare(raw)
    clean = 2 * alert_pct if clean_pct is None else clean_pct
    model = FraudModel(k=k, clean_pct=clean).fit(X)
    scores = model.train_scores
    thr = np.percentile(scores, 100 - alert_pct)
    df["fraud_score"] = scores
    df["flagged"] = scores >= thr
    Z = model.scaler.transform(X)
    reasons = np.full(len(df), "", dtype=object)
    for i in np.flatnonzero(df["flagged"].to_numpy()):
        reasons[i] = explain(df.iloc[i], Z[i])
    df["reasons"] = reasons
    return df, model, thr


def best_threshold(scores, y):
    # threshold with the highest F1 on the validation set
    p, r, t = precision_recall_curve(y, scores)
    f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
    return t[np.argmax(f1)]


def evaluate(name, y, scores, threshold):
    pred = scores >= threshold
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "model": name, "precision": precision, "recall": recall, "f1": f1,
        "frauds_caught": tp, "frauds_missed": fn, "false_alarms": fp,
        "pr_auc": average_precision_score(y, scores),
    }


def run_once(args, seed, quiet=False):
    df = make_transactions(n=args.n, fraud_rate=args.fraud_rate, seed=seed)
    df, X = prepare(df)
    y = df["is_fraud"].values
    if not quiet:
        print(f"  {len(df):,} transactions, {int(y.sum())} fraud ({y.mean():.2%})\n")

    # 70% train, 15% validation, 15% test
    X_tr, X_rest, y_tr, y_rest = train_test_split(X, y, test_size=0.30, stratify=y, random_state=seed)
    X_va, X_te, y_va, y_te = train_test_split(X_rest, y_rest, test_size=0.50, stratify=y_rest, random_state=seed)

    # knn never uses the training labels, only k and the threshold use y_va
    clean = args.clean_pct if args.clean_pct is not None else 2 * args.alert_pct
    model = FraudModel(k=args.k, clean_pct=clean).fit(X_tr, X_va, y_va)
    if not quiet and model.cv_:
        print("Choosing k on the validation set:")
        for k, auc in model.cv_.items():
            print(f"    k={k:<4} validation PR-AUC {auc:.3f}")
        print(f"  -> using k={model.k}\n")

    va, te = model.score(X_va), model.score(X_te)
    thr_nolabels = np.percentile(model.train_scores, 100 - args.alert_pct)
    thr_tuned = best_threshold(va, y_va)
    results = pd.DataFrame([
        evaluate(f"KNN (no labels, top {args.alert_pct:g}%)", y_te, te, thr_nolabels),
        evaluate("KNN (threshold tuned)", y_te, te, thr_tuned),
    ]).set_index("model")
    return results, model, thr_tuned, y_te, te


def run_demo(args):
    print("Generating synthetic transactions...")
    results, model, thr_tuned, y_te, te = run_once(args, args.seed)

    print("=" * 78)
    print(f" TEST RESULTS  ({int(y_te.sum())} frauds among {len(y_te):,} transactions)")
    print("=" * 78)
    print(results.round(3).to_string())
    print("=" * 78)
    print(f"Accuracy not shown: always guessing 'normal' would get {1 - y_te.mean():.1%}.\n")

    best = results["f1"].idxmax()
    row = results.loc[best]
    per_alarm = row["frauds_caught"] / max(row["false_alarms"], 1)
    print(f"Best by F1: {best} -> caught {int(row['frauds_caught'])}/{int(y_te.sum())} frauds, "
          f"{per_alarm:.2f} frauds per false alarm.\n")

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.5))
    p, r, _ = precision_recall_curve(y_te, te)
    ax[0].plot(r, p, label=f"KNN (PR-AUC {average_precision_score(y_te, te):.2f})")
    ax[0].axhline(y_te.mean(), color="gray", ls=":", label="random guessing")
    ax[0].set(xlabel="Recall (frauds caught)", ylabel="Precision (alerts that are real)",
              title="Precision-Recall curve")
    ax[0].legend()

    bins = np.linspace(0, np.percentile(te, 99.5), 50)
    ax[1].hist(te[y_te == 0], bins=bins, alpha=0.6, density=True, label="normal")
    ax[1].hist(te[y_te == 1], bins=bins, alpha=0.6, density=True, label="fraud")
    ax[1].axvline(thr_tuned, color="k", ls="--", label="tuned threshold")
    ax[1].set(xlabel="KNN score (avg distance to neighbors)", title="Fraud scores higher")
    ax[1].legend()
    plt.tight_layout()
    plt.savefig("fraud_results.png", dpi=130)
    print("Saved plot to fraud_results.png")
    if not args.no_plot:
        plt.show()

    if args.interactive:
        interactive(model, thr_tuned)


def run_benchmark(args):
    frames = []
    for i in range(args.runs):
        seed = args.seed + i
        print(f"run {i + 1}/{args.runs} (seed {seed})...", flush=True)
        res, model, *_ = run_once(args, seed, quiet=True)
        res["k"] = model.k
        frames.append(res.reset_index())
    allr = pd.concat(frames)
    cols = ["precision", "recall", "f1", "pr_auc"]
    mean = allr.groupby("model")[cols].mean()
    std = allr.groupby("model")[cols].std()
    out = mean.round(3).astype(str) + " +/- " + std.round(3).astype(str)
    print("\n" + "=" * 78)
    print(f" AVERAGE OVER {args.runs} DATASETS (mean +/- std)")
    print("=" * 78)
    print(out.to_string())
    print("=" * 78)
    print("k chosen per run:", [int(f["k"].iloc[0]) for f in frames])


def interactive(model, threshold):
    print("\n" + "=" * 50)
    print(" TRANSACTION CHECKER")
    print("=" * 50)
    while True:
        try:
            amount = float(input("\n Amount ($): "))
            usual = float(input(" This customer's usual amount ($): "))
            hour = float(input(" Hour of day (0-23): "))
            typical = float(input(" Hour they usually shop (0-23): "))
            refund = input(" Is it a refund? (y/n): ").strip().lower() == "y"
            gap = float(input(" Minutes since their last transaction: "))
            recent = float(input(" Their transactions in the last hour: "))
        except ValueError:
            print(" Please enter numbers.")
            continue
        x = engineer(amount, usual, hour, typical, float(refund), gap, recent)
        s = model.score(x)[0]
        print("-" * 50)
        verdict = "SUSPICIOUS - review this" if s >= threshold else "looks normal"
        print(f" Score {s:.2f} vs threshold {threshold:.2f}: {verdict}")
        print("-" * 50)
        if input(" Check another? (y/n): ").strip().lower() != "y":
            break


def load_transactions(source):
    # reads a csv (a path or an uploaded file) and cleans it up
    # returns (dataframe, number of rows that had to be skipped)
    # raises ValueError with a plain message if the file can't be used
    raw = pd.read_csv(source)
    raw.columns = [str(c).strip().lower().replace(" ", "_") for c in raw.columns]
    missing = {"customer", "timestamp", "amount"} - set(raw.columns)
    if missing:
        raise ValueError(f"Missing column(s): {', '.join(sorted(missing))}. "
                         f"Columns found: {', '.join(raw.columns)}")

    n0 = len(raw)
    if not pd.api.types.is_numeric_dtype(raw["amount"]):
        raw["amount"] = raw["amount"].astype(str).str.replace(r"[$,\s]", "", regex=True)
    raw["amount"] = pd.to_numeric(raw["amount"], errors="coerce")
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], errors="coerce")
    raw = raw.dropna(subset=["customer", "timestamp", "amount"]).copy()
    skipped = n0 - len(raw)
    if len(raw) < 30:
        raise ValueError(f"Only {len(raw)} usable rows. Need at least 30 transactions "
                         "(more is better, a few hundred or more works best).")

    if "is_refund" not in raw:
        raw["is_refund"] = 0
    raw["is_refund"] = pd.to_numeric(raw["is_refund"], errors="coerce").fillna(0).clip(0, 1).astype(int)
    # some exports show refunds as negative amounts
    neg = raw["amount"] < 0
    raw.loc[neg, "is_refund"] = 1
    raw["amount"] = raw["amount"].abs()
    if "is_fraud" in raw:
        raw["is_fraud"] = pd.to_numeric(raw["is_fraud"], errors="coerce").fillna(0).clip(0, 1).astype(int)
    return raw.reset_index(drop=True), skipped


def run_csv(args):
    try:
        raw, skipped = load_transactions(args.csv)
    except ValueError as e:
        raise SystemExit(f"Problem with the CSV: {e}")
    if skipped:
        print(f"Skipped {skipped} rows with a missing or unreadable customer, timestamp or amount.")
    df, model, thr = score_dataframe(raw, args.alert_pct, args.k, args.clean_pct)
    flagged = df[df["flagged"]].sort_values("fraud_score", ascending=False)
    flagged.to_csv("flagged_transactions.csv", index=False)

    print(f"Scored {len(df):,} transactions, flagged the top {args.alert_pct:g}% ({len(flagged)}).")
    print("Saved to flagged_transactions.csv. Top 10:\n")
    pd.set_option("display.max_colwidth", 90)
    print(flagged[["customer", "timestamp", "amount", "fraud_score", "reasons"]].head(10).to_string(index=False))
    if "is_fraud" in df:
        r = evaluate("KNN (CSV)", df["is_fraud"].values, df["fraud_score"].values, thr)
        print(f"\nAgainst your is_fraud labels: precision {r['precision']:.2f}, recall {r['recall']:.2f}")


def parse_args():
    ap = argparse.ArgumentParser(description="KNN fraud detection for small businesses")
    ap.add_argument("--csv", help="score a real transaction csv instead of fake data")
    ap.add_argument("--interactive", action="store_true", help="check single transactions after training")
    ap.add_argument("--no-plot", action="store_true", help="save the plot without opening a window")
    ap.add_argument("--runs", type=int, default=1, help="repeat on this many random datasets and average")
    ap.add_argument("--n", type=int, default=20000, help="number of fake transactions")
    ap.add_argument("--fraud-rate", type=float, default=0.01)
    ap.add_argument("--k", type=int, default=None, help="neighbors (default: picked on validation, 50 for --csv)")
    ap.add_argument("--clean-pct", type=float, default=None,
                    help="percent of most suspicious training rows dropped from the reference (default 2x alert-pct)")
    ap.add_argument("--alert-pct", type=float, default=1.0, help="no-label mode: flag top X%% of scores")
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.csv:
        run_csv(args)
    elif args.runs > 1:
        run_benchmark(args)
    else:
        run_demo(args)
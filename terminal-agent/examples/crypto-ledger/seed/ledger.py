"""Deliberately defective starting point for a reproducible agent exercise."""


def analyze(rows):
    report = {"accepted_rows": 0, "duplicate_rows": 0, "rejected_rows": 0,
              "warnings": [], "timeline": [], "symbols": {}}
    for row in rows:
        report["accepted_rows"] += 1
        report["timeline"].append({"trade_id": row["trade_id"], "timestamp": row["timestamp"]})
        bucket = report["symbols"].setdefault(row["symbol"], {
            "net_quantity": 0.0, "net_cashflow_usdt": 0.0, "fees_usdt": 0.0})
        quantity, price, fee = float(row["quantity"]), float(row["price_usdt"]), float(row["fee_usdt"])
        sign = 1 if row["side"] == "buy" else -1
        bucket["net_quantity"] += sign * quantity
        bucket["net_cashflow_usdt"] += -sign * quantity * price
        bucket["fees_usdt"] += fee
    report["timeline"].sort(key=lambda row: row["timestamp"])
    for bucket in report["symbols"].values():
        for key, value in bucket.items():
            bucket[key] = str(value)
    return report

"""Command-line interface for OSRS exchange prices."""

from __future__ import annotations

import argparse
import csv
import difflib
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from .api import ApiError, Item, PricesClient


def coins(value: int | None) -> str:
    return "n/a" if value is None else f"{value:,} gp"


def local_time(timestamp: int | None) -> str:
    if timestamp is None:
        return "n/a"
    return datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def find_items(items: list[Item], query: str, limit: int = 10) -> list[Item]:
    normalized = query.casefold().strip()
    exact = [item for item in items if item.name.casefold() == normalized]
    if exact:
        return exact
    partial = [item for item in items if normalized in item.name.casefold()]
    if partial:
        return sorted(partial, key=lambda item: (len(item.name), item.name))[:limit]
    names = {item.name.casefold(): item for item in items}
    matches = difflib.get_close_matches(normalized, names, n=limit, cutoff=0.45)
    return [names[name] for name in matches]


def resolve_item(client: PricesClient, query: str) -> Item:
    if query.isdigit():
        item_id = int(query)
        for item in client.mapping():
            if item.id == item_id:
                return item
        raise ApiError(f"Unknown item ID {item_id}")
    matches = find_items(client.mapping(), query)
    if not matches:
        raise ApiError(f'No items match "{query}"')
    if len(matches) > 1:
        choices = "\n".join(f"  {item.id:<6} {item.name}" for item in matches)
        raise ApiError(f'Multiple items match "{query}":\n{choices}\nUse an item ID or a more specific name.')
    return matches[0]


def show_price(client: PricesClient, query: str) -> None:
    item = resolve_item(client, query)
    price = client.latest(item.id)
    high, low = price.get("high"), price.get("low")
    trade_result = low - high if high is not None and low is not None else None
    result_pct = (trade_result / high * 100) if trade_result is not None and high else None
    print(f"{item.name} (ID {item.id})")
    print(f"Instant buy (high):  {coins(high):>16}  {local_time(price.get('highTime'))}")
    print(f"Instant sell (low):  {coins(low):>16}  {local_time(price.get('lowTime'))}")
    suffix = f" ({result_pct:.2f}%)" if result_pct is not None else ""
    print(f"Buy → sell result:   {coins(trade_result):>16}{suffix}")
    print(f"High Alchemy value:  {coins(item.highalch):>16}")
    print(f"GE buy limit:        {coins(item.limit).removesuffix(' gp') if item.limit else 'n/a':>16}")


def search(client: PricesClient, query: str) -> None:
    matches = find_items(client.mapping(), query)
    if not matches:
        raise ApiError(f'No items match "{query}"')
    print(f"{'ID':<8} {'Item':<45} Members")
    for item in matches:
        print(f"{item.id:<8} {item.name:<45} {'yes' if item.members else 'no'}")


def history(client: PricesClient, query: str, timestep: str, points: int) -> None:
    item = resolve_item(client, query)
    rows = client.timeseries(item.id, timestep)[-points:]
    print(f"{item.name} — {timestep} history")
    print(f"{'Time':<26} {'Avg high':>14} {'Avg low':>14} {'High vol':>10} {'Low vol':>10}")
    for row in rows:
        print(
            f"{local_time(row.get('timestamp')):<26} "
            f"{coins(row.get('avgHighPrice')):>14} {coins(row.get('avgLowPrice')):>14} "
            f"{row.get('highPriceVolume') or 0:>10,} {row.get('lowPriceVolume') or 0:>10,}"
        )


def all_price_rows(client: PricesClient, members_only: bool = False) -> list[dict[str, object]]:
    """Join the item mapping to a single bulk latest-price response."""
    prices = client.latest_all()
    rows = []
    for item in client.mapping():
        if members_only and not item.members:
            continue
        price = prices.get(item.id)
        if price is None:
            continue
        high, low = price.get("high"), price.get("low")
        rows.append(
            {
                "id": item.id,
                "name": item.name,
                "members": item.members,
                "buy_limit": item.limit,
                "high_alch": item.highalch,
                "high": high,
                "high_time": price.get("highTime"),
                "low": low,
                "low_time": price.get("lowTime"),
                "buy_sell_profit": low - high if high is not None and low is not None else None,
            }
        )
    return sorted(rows, key=lambda row: str(row["name"]).casefold())


def write_all_csv(rows: list[dict[str, object]], destination: TextIO) -> None:
    fields = (
        "id",
        "name",
        "members",
        "buy_limit",
        "high_alch",
        "high",
        "high_time",
        "low",
        "low_time",
        "buy_sell_profit",
    )
    writer = csv.DictWriter(destination, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)


def show_all(client: PricesClient, output: Path | None, members_only: bool) -> None:
    rows = all_price_rows(client, members_only)
    if output:
        try:
            with output.open("w", encoding="utf-8", newline="") as destination:
                write_all_csv(rows, destination)
        except OSError as error:
            raise ApiError(f"Could not write {output}: {error}") from error
        print(f"Wrote {len(rows):,} prices to {output}")
        return

    print(f"{'ID':<8} {'Item':<36} {'Buy at':>14} {'Sell at':>14} {'High alch':>14} {'Result':>14}")
    for row in rows:
        print(
            f"{row['id']:<8} {str(row['name'])[:36]:<36} "
            f"{coins(row['high']):>14} {coins(row['low']):>14} "
            f"{coins(row['high_alch']):>14} {coins(row['buy_sell_profit']):>14}"
        )
    print(f"\n{len(rows):,} items")


def optional_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


def load_price_csv(source: Path) -> list[dict[str, str]]:
    try:
        with source.open(encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            required = {"id", "name", "high", "high_alch"}
            missing = required.difference(reader.fieldnames or ())
            if missing:
                raise ApiError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
            return list(reader)
    except OSError as error:
        raise ApiError(f"Could not read {source}: {error}") from error


def alch_analysis(
    rows: list[dict[str, str]], nature_rune_price: int | None = None
) -> tuple[list[dict[str, object]], int]:
    if nature_rune_price is None:
        nature = next((row for row in rows if row["name"].casefold() == "nature rune"), None)
        nature_rune_price = optional_int(nature.get("high")) if nature else None
    if nature_rune_price is None:
        raise ApiError("No nature rune buy price found; pass --nature-rune-price PRICE")

    analyzed = []
    for row in rows:
        buy_price = optional_int(row.get("high"))
        high_alch = optional_int(row.get("high_alch"))
        net_profit = (
            high_alch - buy_price - nature_rune_price
            if high_alch is not None and buy_price is not None
            else None
        )
        total_cost = buy_price + nature_rune_price if buy_price is not None else None
        roi = net_profit / total_cost * 100 if net_profit is not None and total_cost else None
        analyzed.append(
            {
                **row,
                "nature_rune_price": nature_rune_price,
                "alch_total_cost": total_cost,
                "net_alch_profit": net_profit,
                "alch_roi_pct": round(roi, 4) if roi is not None else None,
            }
        )
    return analyzed, nature_rune_price


def sort_analysis(rows: list[dict[str, object]], sort_by: str, ascending: bool) -> list[dict[str, object]]:
    columns = {
        "profit": "net_alch_profit",
        "roi": "alch_roi_pct",
        "name": "name",
        "buy-price": "high",
        "high-alch": "high_alch",
    }
    column = columns[sort_by]

    def key(row: dict[str, object]) -> tuple[bool, object]:
        value = row.get(column)
        if column == "name":
            value = str(value).casefold()
        elif isinstance(value, str):
            value = optional_int(value)
        # Missing values remain last in either direction by sorting them separately.
        return value is None, value if value is not None else 0

    populated = [row for row in rows if row.get(column) not in (None, "")]
    missing = [row for row in rows if row.get(column) in (None, "")]
    return sorted(populated, key=key, reverse=not ascending) + missing


def analyze_csv(
    source: Path,
    output: Path | None,
    sort_by: str,
    ascending: bool,
    nature_rune_price: int | None,
    profitable_only: bool,
) -> None:
    rows, rune_price = alch_analysis(load_price_csv(source), nature_rune_price)
    if profitable_only:
        rows = [row for row in rows if isinstance(row["net_alch_profit"], int) and row["net_alch_profit"] > 0]
    rows = sort_analysis(rows, sort_by, ascending)

    if output:
        try:
            with output.open("w", encoding="utf-8", newline="") as destination:
                fields = list(rows[0]) if rows else [
                    "id", "name", "high_alch", "high", "nature_rune_price",
                    "alch_total_cost", "net_alch_profit", "alch_roi_pct",
                ]
                writer = csv.DictWriter(destination, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        except OSError as error:
            raise ApiError(f"Could not write {output}: {error}") from error
        print(f"Wrote {len(rows):,} analyzed items to {output} (nature rune: {rune_price:,} gp)")
        return

    print(f"Nature rune instant-buy price: {rune_price:,} gp")
    print(f"{'ID':<8} {'Item':<38} {'Buy at':>13} {'High alch':>13} {'Net profit':>13} {'ROI':>9}")
    for row in rows:
        roi = row["alch_roi_pct"]
        roi_text = "n/a" if roi is None else f"{roi:.2f}%"
        print(
            f"{row['id']:<8} {str(row['name'])[:38]:<38} {coins(optional_int(row.get('high'))):>13} "
            f"{coins(optional_int(row.get('high_alch'))):>13} {coins(row['net_alch_profit']):>13} {roi_text:>9}"
        )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Query OSRS Grand Exchange prices")
    result.add_argument("--contact", help="email/Discord text included in the API User-Agent")
    sub = result.add_subparsers(dest="command", required=True)
    price = sub.add_parser("price", help="show the latest price and immediate buy/sell result")
    price.add_argument("item", help="exact item name or numeric item ID")
    find = sub.add_parser("search", help="search for an item name")
    find.add_argument("query")
    bulk = sub.add_parser("all", help="fetch all latest prices in one request")
    bulk.add_argument("--output", type=Path, metavar="FILE.csv", help="write results as CSV")
    bulk.add_argument("--members-only", action="store_true", help="only include members' items")
    analyze = sub.add_parser("analyze", help="calculate High Alchemy profit from an exported CSV")
    analyze.add_argument("csv", type=Path, help="CSV created by the all command")
    analyze.add_argument("--sort", choices=("profit", "roi", "name", "buy-price", "high-alch"), default="profit")
    analyze.add_argument("--ascending", action="store_true", help="sort lowest to highest")
    analyze.add_argument("--profitable-only", action="store_true", help="exclude zero-profit, losing, and unavailable items")
    analyze.add_argument("--nature-rune-price", type=int, metavar="GP", help="override the nature rune price found in the CSV")
    analyze.add_argument("--output", type=Path, metavar="FILE.csv", help="write analyzed rows as CSV")
    chart = sub.add_parser("history", help="show recent average prices")
    chart.add_argument("item", help="exact item name or numeric item ID")
    chart.add_argument("--timestep", choices=("5m", "1h", "6h", "24h"), default="1h")
    chart.add_argument("--points", type=int, choices=range(1, 366), default=24, metavar="1-365")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    client = PricesClient(contact=args.contact)
    try:
        if args.command == "price":
            show_price(client, args.item)
        elif args.command == "search":
            search(client, args.query)
        elif args.command == "history":
            history(client, args.item, args.timestep, args.points)
        elif args.command == "all":
            show_all(client, args.output, args.members_only)
        else:
            analyze_csv(
                args.csv, args.output, args.sort, args.ascending,
                args.nature_rune_price, args.profitable_only,
            )
    except ApiError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

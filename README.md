# OSRS Price CLI

A dependency-free command-line tool for live Old School RuneScape Grand Exchange
prices. Data comes from the OSRS Wiki real-time prices API.

## Install

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

The API asks tools to identify themselves. Put an email address or Discord handle
in the environment (or pass `--contact` before the command):

```bash
export OSRS_PRICE_CONTACT="your-name@example.com"
```

## Use

```bash
osrs-price search "whip"
osrs-price price "Abyssal whip"
osrs-price price 4151
osrs-price history "Abyssal whip" --timestep 1h --points 24
osrs-price all
osrs-price all --members-only
osrs-price all --output prices.csv
osrs-price analyze prices.csv --profitable-only
osrs-price analyze prices.csv --sort roi --output alch-analysis.csv
osrs-price --contact "your-name@example.com" price 4151
```

The `all` command makes one bulk price request rather than one request per item.
CSV output includes item IDs and names, membership status, buy limits, High
Alchemy values, high and low prices and timestamps, and the result of buying
high then selling low.

The `analyze` command works offline on a bulk CSV. It uses the nature rune's
instant-buy price from that file and calculates `high_alch - high - nature rune`
for every item. Sort by `profit`, `roi`, `name`, `buy-price`, or `high-alch`;
add `--ascending` to reverse the default descending order.

`high` is the most recent instant-buy price and `low` is the most recent
instant-sell price. The displayed buy/sell result is `low - high`, which is the
gain or loss from buying instantly and then selling instantly before Grand
Exchange tax. It will normally be negative.

## Test

```bash
python -m unittest discover -s tests
```

API documentation: https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices

"""Currency seed data (code, name, symbol, exponent). Used by the Alembic migration and by tests."""

CURRENCIES: list[tuple[str, str, str, int]] = [
    ("INR", "Indian Rupee", "₹", 2),
    ("USD", "US Dollar", "$", 2),
    ("EUR", "Euro", "€", 2),
    ("GBP", "Pound Sterling", "£", 2),
    ("JPY", "Japanese Yen", "¥", 0),
    ("AUD", "Australian Dollar", "A$", 2),
    ("CAD", "Canadian Dollar", "CA$", 2),
    ("CHF", "Swiss Franc", "CHF", 2),
    ("CNY", "Chinese Yuan", "CN¥", 2),
    ("HKD", "Hong Kong Dollar", "HK$", 2),
    ("SGD", "Singapore Dollar", "S$", 2),
    ("NZD", "New Zealand Dollar", "NZ$", 2),
    ("AED", "UAE Dirham", "AED", 2),
    ("SAR", "Saudi Riyal", "SAR", 2),
    ("KWD", "Kuwaiti Dinar", "KWD", 3),
    ("BHD", "Bahraini Dinar", "BHD", 3),
    ("OMR", "Omani Rial", "OMR", 3),
    ("QAR", "Qatari Riyal", "QAR", 2),
    ("THB", "Thai Baht", "฿", 2),
    ("MYR", "Malaysian Ringgit", "RM", 2),
    ("IDR", "Indonesian Rupiah", "Rp", 2),
    ("PHP", "Philippine Peso", "₱", 2),
    ("VND", "Vietnamese Dong", "₫", 0),
    ("KRW", "South Korean Won", "₩", 0),
    ("LKR", "Sri Lankan Rupee", "Rs", 2),
    ("NPR", "Nepalese Rupee", "NPRs", 2),
    ("PKR", "Pakistani Rupee", "PKRs", 2),
    ("BDT", "Bangladeshi Taka", "৳", 2),
    ("ZAR", "South African Rand", "R", 2),
    ("BRL", "Brazilian Real", "R$", 2),
    ("MXN", "Mexican Peso", "MX$", 2),
    ("SEK", "Swedish Krona", "kr", 2),
    ("NOK", "Norwegian Krone", "NOkr", 2),
    ("DKK", "Danish Krone", "DKkr", 2),
    ("TRY", "Turkish Lira", "₺", 2),
]


# Category tree (our own list, OQ-D3). Parents get ids 101..107; children get ids 1..N in the order below,
# so id 1 = General -> Uncategorized (the default). (parent_slug, parent_name, icon, [(child_slug_suffix, name, icon)])
CATEGORY_TREE: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
    ("entertainment", "Entertainment", "entertainment", [
        ("games", "Games", "games"), ("movies", "Movies", "movies"), ("music", "Music", "music"),
        ("sports", "Sports", "sports"), ("events", "Events", "events"), ("other", "Other", "other"),
    ]),
    ("food", "Food & drink", "food", [
        ("groceries", "Groceries", "groceries"), ("restaurants", "Restaurants", "restaurants"),
        ("coffee", "Coffee & tea", "coffee"), ("snacks", "Snacks", "snacks"), ("drinks", "Drinks", "drinks"),
        ("other", "Other", "other"),
    ]),
    ("home", "Home", "home", [
        ("rent", "Rent", "rent"), ("mortgage", "Mortgage", "mortgage"), ("furniture", "Furniture", "furniture"),
        ("household", "Household supplies", "household"), ("maintenance", "Maintenance", "maintenance"),
        ("services", "Services", "services"), ("other", "Other", "other"),
    ]),
    ("life", "Life", "life", [
        ("clothing", "Clothing", "clothing"), ("gifts", "Gifts", "gifts"), ("medical", "Medical", "medical"),
        ("education", "Education", "education"), ("insurance", "Insurance", "insurance"),
        ("pets", "Pets", "pets"), ("childcare", "Childcare", "childcare"), ("other", "Other", "other"),
    ]),
    ("transport", "Transport", "transport", [
        ("taxi", "Taxi", "taxi"), ("fuel", "Fuel", "fuel"), ("parking", "Parking", "parking"),
        ("bus_train", "Bus & train", "train"), ("flights", "Flights", "flights"), ("hotel", "Hotel", "hotel"),
        ("other", "Other", "other"),
    ]),
    ("utilities", "Utilities", "utilities", [
        ("electricity", "Electricity", "electricity"), ("water", "Water", "water"), ("gas", "Gas", "gas"),
        ("internet", "Internet", "internet"), ("phone", "Phone", "phone"), ("other", "Other", "other"),
    ]),
    ("general", "General", "general", [
        ("uncategorized", "Uncategorized", "uncategorized"), ("other", "Other", "other"),
    ]),
]
# The default category must be id 1 (General -> Uncategorized): put the General children first in id order.
_ordered = sorted(CATEGORY_TREE, key=lambda p: p[0] != "general")


def category_rows() -> list[dict]:
    """Flat rows for the `categories` table: parents (ids 101..) then children (ids 1..), sort_index within level."""
    parents, children = [], []
    child_id = 1
    for pos, (slug, name, icon, kids) in enumerate(CATEGORY_TREE):
        pid = 101 + pos
        parents.append({"id": pid, "parent_id": None, "slug": slug, "name": name, "icon": icon, "sort_index": pos})
    pid_by_slug = {p["slug"]: p["id"] for p in parents}
    for slug, name, icon, kids in _ordered:
        for i, (suffix, kname, kicon) in enumerate(kids):
            children.append({
                "id": child_id, "parent_id": pid_by_slug[slug], "slug": f"{slug}.{suffix}", "name": kname,
                "icon": kicon, "sort_index": i,
            })
            child_id += 1
    return parents + children

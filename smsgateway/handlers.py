"""
Understanding an SMS. Each project (the service a phone belongs to) has its own set of keywords and handlers; a handler
takes the message and returns the reply text (or None for no reply). Today there is one project, "mkulima" (farmers and
inputs). A school project can be added later as another entry in PROJECTS without touching the gateway.

Mkulima keywords (Swahili and English):
    SWALI <question>        a farming question, answered by an agronomist or the AI
    BEI <product> [region]  prices and shops that have it in stock, for example: BEI mbolea Arusha
    HALI [order number]     where an order is
    LUGHA SW | EN           change the language of replies
    MSAADA                  what to send
    STOP / START            stop or restart messages
Anything else of five words or more is treated as a farming question; anything shorter gets the help message.
"""
import re

from django.db.models import Q
from django.utils import timezone

from . import text
from .models import Contact


STRINGS = {
    "sw": {
        "help": ("Mkulima Smart. Tuma: SWALI <swali lako> | BEI <bidhaa> <mkoa>, mfano BEI mbolea Arusha | "
                 "HALI <namba ya oda> | LUGHA EN | STOP kujiondoa"),
        "stopped": "Umejiondoa. Hutapata ujumbe kutoka kwetu. Tuma START kuanza tena.",
        "started": "Karibu tena Mkulima Smart. Tuma MSAADA kuona unachoweza kuuliza.",
        "language_set": "Sawa. Nitajibu kwa Kiswahili.",
        "language_help": "Tuma LUGHA SW kwa Kiswahili au LUGHA EN kwa Kiingereza.",
        "price_ask": "Andika bidhaa unayotaka, mfano BEI mbolea Arusha.",
        "price_none": "Hatukupata {query}{where} kwenye duka lenye bidhaa. Jaribu jina lingine au mkoa mwingine.",
        "status_none": "Hatukupata oda yenye namba hiyo kwa simu yako. Angalia namba kisha tuma HALI <namba>.",
        "status_nothing": "Hatuna oda iliyosajiliwa kwa namba yako ya simu.",
        "status_line": "Oda {number}: {status}.{note}",
        "error": "Samahani, kuna hitilafu kidogo. Tafadhali jaribu tena baada ya dakika chache.",
        "status": {"pending": "inasubiri duka", "confirmed": "imethibitishwa", "dispatched": "imetumwa", "delivered": "imefika",
                   "cancelled": "imefutwa", "processing": "inaandaliwa", "shipped": "imetumwa"},
    },
    "en": {
        "help": ("Mkulima Smart. Send: SWALI <your question> | BEI <product> <region>, e.g. BEI fertilizer Arusha | "
                 "HALI <order number> | LUGHA SW | STOP to opt out"),
        "stopped": "You have opted out. You will not get messages from us. Send START to begin again.",
        "started": "Welcome back to Mkulima Smart. Send HELP to see what you can ask.",
        "language_set": "Okay. I will reply in English.",
        "language_help": "Send LUGHA SW for Swahili or LUGHA EN for English.",
        "price_ask": "Write the product you want, for example BEI fertilizer Arusha.",
        "price_none": "We found no shop with {query}{where} in stock. Try another name or region.",
        "status_none": "We found no order with that number for your phone. Check the number and send HALI <number>.",
        "status_nothing": "We have no order registered for your phone number.",
        "status_line": "Order {number}: {status}.{note}",
        "error": "Sorry, something went wrong. Please try again in a few minutes.",
        "status": {"pending": "waiting for the shop", "confirmed": "confirmed", "dispatched": "on its way", "delivered": "delivered",
                   "cancelled": "cancelled", "processing": "being prepared", "shipped": "on its way"},
    },
}


def t(language, key):
    return STRINGS.get(language, STRINGS["sw"])[key]


# ---------------------------------------------------------------------------
# Reading the message
# ---------------------------------------------------------------------------

MKULIMA_KEYWORDS = {
    "swali": "ask", "ask": "ask", "question": "ask", "uliza": "ask",
    "bei": "price", "price": "price", "gharama": "price",
    "hali": "status", "status": "status", "oda": "status", "order": "status",
    "lugha": "language", "language": "language",
    "msaada": "help", "help": "help", "menu": "help",
    "stop": "stop", "sitisha": "stop", "acha": "stop", "unsubscribe": "stop",
    "start": "start", "anza": "start", "ndiyo": "start",
}


def parse(keywords, body):
    """Returns (handler name, the rest of the message). Keywords are shortcuts; any other text is a natural conversation."""
    words = (body or "").split()
    if not words:
        return "help", ""
    first = re.sub(r"[^\w]", "", words[0].lower())
    if first in keywords:
        return keywords[first], " ".join(words[1:]).strip()
    return "ask", " ".join(words)


# ---------------------------------------------------------------------------
# Mkulima handlers: each takes (inbound, contact, args) and returns the reply text, or None
# ---------------------------------------------------------------------------

def help_reply(inbound, contact, args):
    return t(contact.language, "help")


def stop(inbound, contact, args):
    Contact.objects.filter(pk=contact.pk).update(opted_out=True)
    contact.opted_out = True
    return t(contact.language, "stopped")


def start(inbound, contact, args):
    Contact.objects.filter(pk=contact.pk).update(opted_out=False)
    contact.opted_out = False
    return t(contact.language, "started")


def language(inbound, contact, args):
    word = re.sub(r"[^\w]", "", (args or "").split(" ")[0].lower()) if args else ""
    if word in ("en", "eng", "english", "kiingereza"):
        new = "en"
    elif word in ("sw", "swa", "kiswahili", "swahili"):
        new = "sw"
    else:
        return t(contact.language, "language_help")
    Contact.objects.filter(pk=contact.pk).update(language=new)
    contact.language = new
    return t(new, "language_set")


def ask(inbound, contact, args):
    """A farming question: the same assistant that answers WhatsApp (an agronomist when one is free, otherwise the AI)."""
    from assistant import engine
    from gova_pp.diagnosis import DiagnosisError

    question = (args or inbound.body).strip()
    try:
        result = engine.handle_message(
            phone=inbound.sender, language=contact.language, text=question, external_id=f"sms-{inbound.pk}", channel="sms",
        )
    except DiagnosisError as exc:
        kind = "err_service" if exc.status >= 500 or exc.status == 503 else "err_empty"
        return engine.fallback_text(kind, contact.language)
    return result.get("reply_text") or None


STOP_WORDS = {"ya", "za", "wa", "la", "kwa", "na", "ni", "the", "of", "for", "in", "at", "bei", "price"}

CATEGORY_WORDS = {
    "mbolea": "fertilizer", "fertilizer": "fertilizer", "fertiliser": "fertilizer", "fertilizers": "fertilizer",
    "mbegu": "seeds", "seed": "seeds", "seeds": "seeds",
    "miche": "seedlings", "seedling": "seedlings", "seedlings": "seedlings",
    "dawa": "pesticides", "viuatilifu": "pesticides", "pesticide": "pesticides", "pesticides": "pesticides",
    "jembe": "tools", "zana": "tools", "tools": "tools",
    "kuku": "feed", "mifugo": "feed", "feed": "feed",
    "kompost": "compost", "compost": "compost",
}


def _region_in(query):
    from operations.models import TANZANIA_REGIONS

    lowered = f" {query.lower()} "
    for name in sorted((name for name, _ in TANZANIA_REGIONS), key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", lowered):
            return name
    return ""


def stock_context(message, region=""):
    """Lines of in-stock items matching what the farmer wrote (up to 8, cheapest first), for the assistant to quote. Empty if none."""
    from inputs.models import ShopStockItem
    from website.templatetags.money import tzs

    region = region or _region_in(message)
    words = [w for w in re.findall(r"\w+", message.lower()) if len(w) >= 3 and w not in STOP_WORDS]
    categories = {CATEGORY_WORDS[w] for w in words if w in CATEGORY_WORDS}
    names = [w for w in words if w not in CATEGORY_WORDS]
    if not categories and not names:
        return ""
    today = timezone.localdate()
    stock = ShopStockItem.objects.filter(
        is_active=True, quantity__gte=1, shop__is_active=True, shop__onboarding_completed=True,
    ).select_related("shop")
    match = Q(category__in=categories)
    for word in names:
        match |= Q(name__icontains=word) | Q(brand__icontains=word)
    stock = stock.filter(match)
    if region:
        stock = stock.filter(Q(shop__region__iexact=region) | Q(shop__location__icontains=region))
    lines = []
    for item in stock.order_by("selling_price", "name")[:20]:
        if item.expiry_date and item.expiry_date < today:
            continue
        shop = item.shop
        lines.append(f"- {item.name}: TSh {tzs(item.selling_price)}, {shop.business_name or shop.seller_name}, {shop.region or 'region unknown'}, {text.local_format(shop.phone_number)}")
        if len(lines) == 8:
            break
    return "\n".join(lines)


def price(inbound, contact, args):
    """BEI mbolea Arusha: up to three in-stock items with the shop and its number."""
    from inputs.models import ShopStockItem
    from website.templatetags.money import tzs

    region = _region_in(args)
    remainder = re.sub(rf"(?i)(?<!\w){re.escape(region)}(?!\w)", " ", args) if region else args
    tokens = [w for w in re.findall(r"\w+", remainder.lower()) if len(w) >= 3 and w not in STOP_WORDS]
    if not tokens:
        return t(contact.language, "price_ask")

    stock = ShopStockItem.objects.filter(
        is_active=True, quantity__gte=1, shop__is_active=True, shop__onboarding_completed=True,
    ).select_related("shop")
    for token in tokens:
        match = Q(name__icontains=token) | Q(brand__icontains=token)
        if token in CATEGORY_WORDS:
            match |= Q(category=CATEGORY_WORDS[token])
        stock = stock.filter(match)
    if region:
        stock = stock.filter(Q(shop__region__iexact=region) | Q(shop__location__icontains=region))
    today = timezone.localdate()
    found = [item for item in stock.order_by("selling_price", "name")[:12] if not item.expiry_date or item.expiry_date >= today][:3]
    if not found:
        where = (f" in {region}" if contact.language == "en" else f" mkoa wa {region}") if region else ""
        return t(contact.language, "price_none").format(query=" ".join(tokens), where=where)
    lines = []
    for item in found:
        shop = item.shop
        lines.append(f"{item.name}: TSh {tzs(item.selling_price)}, {shop.business_name or shop.seller_name} {text.local_format(shop.phone_number)}")
    return "\n".join(lines)


def status(inbound, contact, args):
    """HALI 12 / HALI MS-12 / HALI <Kikapu order id>: the order's status, only for the phone that placed it."""
    from inputs.models import FarmerOrder
    from website.models import Order

    key = text.phone_key(inbound.sender)
    code = (args or "").strip().split(" ")[0] if args else ""
    strings = STRINGS.get(contact.language, STRINGS["sw"])["status"]

    website_orders = Order.objects.filter(phone_number__endswith=key) if key else Order.objects.none()
    farmer_orders = FarmerOrder.objects.filter(farmer_phone__endswith=key) if key else FarmerOrder.objects.none()

    found = None
    if code:
        digits = re.sub(r"\D", "", code)
        if code.upper().startswith("MS-") and digits:
            found = farmer_orders.filter(pk=int(digits)).first()
        elif digits and digits == code:
            found = website_orders.filter(pk=int(digits)).first() or farmer_orders.filter(pk=int(digits)).first()
        if found is None:
            found = farmer_orders.filter(external_order_id__iexact=code).first()
        if found is None:
            return t(contact.language, "status_none")
    else:
        latest = [o for o in (website_orders.order_by("-created_at").first(), farmer_orders.order_by("-created_at").first()) if o]
        if not latest:
            return t(contact.language, "status_nothing")
        found = max(latest, key=lambda order: order.created_at)

    if isinstance(found, FarmerOrder):
        number, note = found.order_number, (f" {found.shop_note}" if found.shop_note else "")
    else:
        number, note = f"#{found.pk}", ""
    return t(contact.language, "status_line").format(number=number, status=strings.get(found.status, found.status), note=note)


PROJECTS = {
    "mkulima": {
        "keywords": MKULIMA_KEYWORDS,
        "handlers": {
            "ask": ask, "price": price, "status": status, "language": language, "help": help_reply, "stop": stop, "start": start,
        },
        # these may still be answered for someone who opted out
        "allowed_when_opted_out": {"start", "help"},
        # these are slow (they may call the AI), so they are answered by the background worker, not while the phone waits
        "deferred": {"ask"},
    },
}

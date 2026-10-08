"""
Crop photo diagnosis and marketplace product recommendation.

A farmer sends a photo; GPT-4o returns a structured diagnosis (what the crop is,
what is wrong, what to do, which kinds of product help); we then match that against
products actually on sale in the marketplace and return the best few.
"""
import base64
import io
import json
import logging
import mimetypes
import os
from urllib.parse import urlparse

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger("gova_pp")

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

PROBLEM_TYPES = {"pest", "disease", "weed", "nutrient_deficiency", "soil", "water_stress", "healthy", "other", "not_agricultural"}

# Marketplace category slugs (website/category_defaults.py) that address each kind of problem.
PROBLEM_CATEGORY_SLUGS = {
    "pest": ["crop-protection"],
    "disease": ["crop-protection"],
    "weed": ["crop-protection"],
    "nutrient_deficiency": ["fertilizers", "soil-health"],
    "soil": ["soil-health", "fertilizers"],
    "water_stress": ["irrigation"],
}


class DiagnosisError(Exception):
    """A problem the farmer/app should hear about (bad image, service not configured, model failure)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Getting the image into a form OpenAI can read
# ---------------------------------------------------------------------------

def _data_url(raw, mime):
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _check_image_bytes(raw):
    """Reject non-images and oversized files. Returns the detected mime type."""
    if len(raw) > MAX_IMAGE_BYTES:
        raise DiagnosisError("The image is larger than 8 MB.")
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
            mime = Image.MIME.get(image.format)
    except Exception:
        raise DiagnosisError("That file is not a valid image.")
    if mime not in ALLOWED_IMAGE_TYPES:
        raise DiagnosisError("Use a JPG, PNG or WebP photo.")
    return mime


def image_from_upload(uploaded):
    """An uploaded file (multipart `image`) -> data URL."""
    raw = uploaded.read(MAX_IMAGE_BYTES + 1)
    mime = _check_image_bytes(raw)
    return _data_url(raw, mime)


def resolve_image(image_url):
    """
    A URL the app/chat gives us -> something OpenAI can fetch. Photos stored on this
    server (under MEDIA_URL) are read from disk and sent inline, since OpenAI cannot
    reach localhost or private addresses. Anything else is passed through as a URL.
    """
    parsed = urlparse(image_url)
    media_url = settings.MEDIA_URL if settings.MEDIA_URL.startswith("/") else f"/{settings.MEDIA_URL}"

    if parsed.path.startswith(media_url):
        relative = parsed.path[len(media_url):]
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        path = os.path.realpath(os.path.join(media_root, relative))
        # Never read outside MEDIA_ROOT (e.g. /media/../../settings.py).
        try:
            inside = os.path.commonpath([media_root, path]) == media_root
        except ValueError:  # e.g. different drives on Windows
            inside = False
        if not inside:
            raise DiagnosisError("Invalid image path.")
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                raw = handle.read(MAX_IMAGE_BYTES + 1)
            mime = _check_image_bytes(raw)
            return _data_url(raw, mime)
        if not parsed.netloc:
            raise DiagnosisError("Image file not found on the server.", status=404)

    if parsed.scheme not in ("http", "https"):
        raise DiagnosisError("Image URL must be http(s) or a /media/ path.")
    return image_url


# ---------------------------------------------------------------------------
# Asking the model
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert agronomist helping smallholder farmers in Tanzania through the Mkulima Smart platform.
Look at the farmer's photo and reply with ONE JSON object and nothing else, with exactly these keys:

  "crop":                 the crop or plant shown (e.g. "Maize"), or "" if unclear
  "problem_type":         one of: pest, disease, weed, nutrient_deficiency, soil, water_stress, healthy, other, not_agricultural
  "problem":              short name of the specific problem (e.g. "Fall armyworm", "Maize streak virus"), or "" if healthy
  "confidence":           "low", "medium" or "high" - how sure you are from this photo
  "urgency":              "low", "medium" or "high"
  "summary":              one or two plain sentences saying what you see
  "advice":               practical steps the farmer can take now, as short markdown bullets
  "product_search_terms": 3 to 6 lowercase ENGLISH keywords for products that would help, as a shop would name them
                          (e.g. ["fungicide", "mancozeb"], ["insecticide", "cypermethrin"], ["npk", "fertilizer"]).
                          Use [] if the plant is healthy or the photo is not agricultural.
  "needs_expert":         true if you are unsure, the damage is severe, or an extension officer should see it

Rules:
- Write "summary" and "advice" in {language_name}. Keep "product_search_terms" in English.
- Never give pesticide doses or mixing rates. Say to follow the product label and wear protective gear.
- If the photo is not a plant, crop, soil or farm problem, use problem_type "not_agricultural".
- If you cannot tell what is wrong, say so, set confidence "low" and needs_expert true. Do not guess confidently.
{context}"""

LANGUAGE_NAMES = {"sw": "Swahili", "en": "English"}


def request_diagnosis(image_for_openai, context=None, language="en"):
    """Call GPT-4o with the photo. Returns the raw parsed JSON dict."""
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        raise DiagnosisError("Photo analysis is not configured on this server.", status=503)

    context_text = ""
    if context:
        context_text = (
            "\nAbout the farmer: "
            f"name {context.get('farmer_name', 'unknown')}, location {context.get('farmer_location', 'unknown')}, "
            f"subject '{context.get('subject', '')}'."
        )

    from openai import OpenAI

    try:
        client = OpenAI(api_key=api_key, timeout=45)
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=900,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.format(language_name=LANGUAGE_NAMES.get(language, "English"), context=context_text)},
                {"role": "user", "content": [
                    {"type": "text", "text": "Please diagnose this photo from my farm."},
                    {"type": "image_url", "image_url": {"url": image_for_openai, "detail": "high"}},
                ]},
            ],
        )
        content = response.choices[0].message.content or ""
    except Exception as exc:
        logger.error("OpenAI diagnosis failed: %s", exc)
        raise DiagnosisError("Could not analyse the photo right now. Please try again.", status=502)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.error("OpenAI diagnosis returned non-JSON: %.200s", content)
        raise DiagnosisError("Could not read the analysis. Please try again.", status=502)
    if not isinstance(data, dict):
        raise DiagnosisError("Could not read the analysis. Please try again.", status=502)
    return data


def normalize_diagnosis(raw):
    """Coerce model output into a predictable shape; the model's JSON is never trusted as-is."""
    problem_type = str(raw.get("problem_type") or "other").strip().lower()
    if problem_type not in PROBLEM_TYPES:
        problem_type = "other"

    def level(value, default):
        value = str(value or "").strip().lower()
        return value if value in ("low", "medium", "high") else default

    terms = []
    for term in raw.get("product_search_terms") or []:
        term = str(term).strip().lower()
        if len(term) >= 3 and term not in terms:
            terms.append(term[:40])
    terms = terms[:6]

    return {
        "crop": str(raw.get("crop") or "").strip()[:80],
        "problem_type": problem_type,
        "problem": str(raw.get("problem") or "").strip()[:120],
        "confidence": level(raw.get("confidence"), "low"),
        "urgency": level(raw.get("urgency"), "medium"),
        "summary": str(raw.get("summary") or "").strip()[:600],
        "advice": str(raw.get("advice") or "").strip()[:2000],
        "product_search_terms": terms,
        "needs_expert": bool(raw.get("needs_expert")) or str(raw.get("confidence", "")).lower() == "low",
    }


def diagnosis_to_markdown(diagnosis):
    """Plain-text version of the diagnosis for clients that only show the old `analysis` string."""
    parts = []
    headline = " - ".join(p for p in (diagnosis["crop"], diagnosis["problem"]) if p)
    if headline:
        parts.append(f"**{headline}**")
    if diagnosis["summary"]:
        parts.append(diagnosis["summary"])
    if diagnosis["advice"]:
        parts.append(diagnosis["advice"])
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Matching marketplace products
# ---------------------------------------------------------------------------

def recommend_products(diagnosis, request=None, limit=3):
    """
    In-stock, active marketplace products that fit the diagnosis, best first.
    A product must be in a category that addresses the problem type or match one of the
    model's search terms; matches on the product name outrank matches in the description.
    """
    from website.models import Product

    problem_type = diagnosis["problem_type"]
    if problem_type in ("healthy", "not_agricultural"):
        return []

    slugs = PROBLEM_CATEGORY_SLUGS.get(problem_type, [])
    terms = diagnosis["product_search_terms"]
    if not slugs and not terms:
        return []

    query = Q()
    if slugs:
        query |= Q(category__slug__in=slugs)
    for term in terms:
        query |= Q(name__icontains=term) | Q(description__icontains=term)

    candidates = (
        Product.objects.filter(query, is_active=True, stock__gt=0)
        .select_related("category")
        .prefetch_related("images")[:200]
    )

    crop = diagnosis["crop"].lower()
    scored = []
    for product in candidates:
        name, description = product.name.lower(), (product.description or "").lower()
        matched = [t for t in terms if t in name or t in description]
        in_category = product.category.slug in slugs
        if not matched and not in_category:
            continue
        score = 3 * sum(t in name for t in terms) + sum(t in description for t in terms)
        score += 2 if in_category else 0
        score += 2 if crop and (crop in name or crop in description) else 0
        scored.append((score, product, matched))

    scored.sort(key=lambda item: (-item[0], item[1].name))

    results = []
    for score, product, matched in scored[:limit]:
        image = next((i for i in product.images.all() if i.is_primary), None) or next(iter(product.images.all()), None)
        image_url = image.image.url if image and image.image else None
        url = product.get_absolute_url()
        if request is not None:
            url = request.build_absolute_uri(url)
            image_url = request.build_absolute_uri(image_url) if image_url else None
        results.append({
            "id": product.pk,
            "name": product.name,
            "category": product.category.name,
            "price": float(product.price),
            "discount_price": float(product.discount_price) if product.discount_price else None,
            "stock": product.stock,
            "requires_quote": product.requires_quote,
            "image": image_url,
            "url": url,
            "matched_terms": matched,
        })
    return results

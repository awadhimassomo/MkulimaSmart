"""Labelling, the automatic train/validation/test split, and building the export zip."""
import csv
import hashlib
import io
import json
import tempfile
import zipfile

from django.conf import settings
from django.db.models import Count
from django.utils.text import slugify
from PIL import Image, ImageOps

from assistant.models import Message

from .models import DatasetExport, LabeledImage, PROBLEM_TYPES

# Shown as suggestions in the labelling form; agronomists can type anything else.
CROPS = [
    "Maize", "Rice", "Beans", "Cassava", "Sweet potato", "Tomato", "Onion", "Banana", "Coffee", "Cashew", "Cocoa", "Tea",
    "Cotton", "Sunflower", "Sesame", "Mango", "Citrus", "Avocado", "Pineapple", "Papaya", "Sorghum", "Irish potato", "Cabbage",
]
PROBLEMS = [
    "Healthy", "Fall armyworm", "Maize streak virus", "Maize lethal necrosis", "Gray leaf spot", "Northern leaf blight",
    "Black pod", "Anthracnose", "Late blight", "Early blight", "Coffee leaf rust", "Coffee berry disease",
    "Cassava mosaic disease", "Cassava brown streak disease", "Banana Xanthomonas wilt", "Black sigatoka", "Powdery mildew",
    "Bacterial wilt", "Aphids", "Whiteflies", "Stem borer", "Nitrogen deficiency", "Phosphorus deficiency", "Potassium deficiency",
]

MAX_EDGE = 1024
SPLIT_TRAIN, SPLIT_VAL = 80, 90  # farmers hashed into 0-99: below 80 train, 80-89 validation, 90-99 test
CANDIDATES = 300


def split_for(conversation_id):
    """Stable and by farmer: everything one farmer sent goes to the same set, so tests never contain training photos."""
    salt = getattr(settings, "TRAINING_SPLIT_SALT", "mkulima-v1")
    bucket = int(hashlib.sha256(f"{salt}:{conversation_id}".encode()).hexdigest(), 16) % 100
    if bucket < SPLIT_TRAIN:
        return LabeledImage.TRAIN
    return LabeledImage.VAL if bucket < SPLIT_VAL else LabeledImage.TEST


def _key(text):
    return slugify(text or "")[:80] or "unknown"


# ---------------------------------------------------------------------------
# What there is to label
# ---------------------------------------------------------------------------

def ai_guess(message):
    """What the AI answered to this photo: crop, problem, how sure it was."""
    reply = message.replies.filter(role="assistant").order_by("pk").first()
    diagnosis = (reply.payload or {}).get("diagnosis") if reply else None
    if not diagnosis:
        return None
    return {
        "crop": diagnosis.get("crop", ""), "problem": diagnosis.get("problem", ""), "problem_type": diagnosis.get("problem_type", "other"),
        "unsure": bool(diagnosis.get("needs_expert")) or diagnosis.get("crop_confidence") == "low" or diagnosis.get("confidence") == "low",
        "summary": diagnosis.get("summary", ""),
    }


def labelable(queryset=None):
    """Photos from farmers who agreed, with the file on disk, that nobody has labelled yet."""
    base = queryset if queryset is not None else Message.objects.all()
    return base.filter(kind="image", conversation__training_consent=True, label__isnull=True).exclude(photo="").exclude(photo__isnull=True)


def next_photo(skipped=()):
    """The next photo to label: ones the AI was unsure about first, then the newest."""
    candidates = list(labelable().exclude(pk__in=list(skipped)).select_related("conversation").order_by("-pk")[:CANDIDATES])
    if not candidates:
        return None, 0
    guesses = {m.pk: ai_guess(m) for m in candidates}
    candidates.sort(key=lambda m: (not (guesses[m.pk] or {}).get("unsure", True), -m.pk))
    return candidates[0], labelable().count()


# ---------------------------------------------------------------------------
# Saving a label
# ---------------------------------------------------------------------------

class LabelError(ValueError):
    pass


def save_label(message, data, user, source):
    """Create or replace the label for one photo. `data`: crop, problem, problem_type, reject, reject_reason."""
    if message.kind != "image" or not message.photo:
        raise LabelError("This message has no stored photo.")
    if message.conversation.training_consent is not True:
        raise LabelError("The farmer has not agreed to share this photo, so it cannot be labelled.")

    guess = ai_guess(message) or {}
    split = split_for(message.conversation_id)
    fields = {"label_source": source, "labeled_by": user, "ai_crop": (guess.get("crop") or "")[:80], "ai_problem": (guess.get("problem") or "")[:120], "split": split}

    if data.get("reject"):
        fields.update(is_rejected=True, reject_reason=(data.get("reject_reason") or "Not usable")[:120], crop="", crop_key="", problem="", problem_key="", problem_type="other")
    else:
        crop = " ".join((data.get("crop") or "").split())[:80]
        problem_type = data.get("problem_type") or "other"
        if problem_type not in dict(PROBLEM_TYPES):
            raise LabelError("Choose what kind of problem it is.")
        problem = " ".join((data.get("problem") or "").split())[:120]
        if problem_type == "healthy" and not problem:
            problem = "Healthy"
        if len(crop) < 2:
            raise LabelError("Write which crop this is.")
        if not problem:
            raise LabelError("Write what the problem is, or choose Healthy.")
        fields.update(
            is_rejected=False, reject_reason="", crop=crop, crop_key=_key(crop), problem=problem, problem_key=_key(problem), problem_type=problem_type,
        )
    label, _ = LabeledImage.objects.update_or_create(message=message, defaults=fields)
    return label


# ---------------------------------------------------------------------------
# Numbers for the dashboard
# ---------------------------------------------------------------------------

def eligible():
    """Labels that go into an export: a human confirmed them, usable, and the farmer still agrees."""
    return LabeledImage.objects.filter(is_rejected=False, message__conversation__training_consent=True)


def stats():
    good = eligible()
    rows = {}
    for row in good.values("crop", "crop_key", "problem", "problem_key", "split").annotate(n=Count("pk")):
        key = (row["crop_key"], row["problem_key"])
        entry = rows.setdefault(key, {"crop": row["crop"], "problem": row["problem"], "train": 0, "val": 0, "test": 0})
        entry[row["split"]] += row["n"]
    classes = sorted(rows.values(), key=lambda r: -(r["train"] + r["val"] + r["test"]))
    for entry in classes:
        entry["total"] = entry["train"] + entry["val"] + entry["test"]

    checked = good.exclude(ai_crop="")
    agree = sum(1 for label in checked.only("crop", "problem", "ai_crop", "ai_problem") if label.ai_agrees)
    return {
        "consented_photos": Message.objects.filter(kind="image", conversation__training_consent=True).exclude(photo="").count(),
        "to_label": labelable().count(),
        "labelled": good.count(),
        "rejected": LabeledImage.objects.filter(is_rejected=True).count(),
        "splits": {s: good.filter(split=s).count() for s in (LabeledImage.TRAIN, LabeledImage.VAL, LabeledImage.TEST)},
        "classes": classes,
        "ai_checked": checked.count(),
        "ai_agree": agree,
        "declined": Message.objects.filter(kind="image", conversation__training_consent=False).count(),
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _clean_jpeg(path):
    """The photo as a plain JPEG: rotated upright, longest side at most MAX_EDGE, and no EXIF (so no GPS or camera details)."""
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((MAX_EDGE, MAX_EDGE))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=90)
    return out.getvalue()


README = """Mkulima Smart crop photo dataset

Folders: train/, val/ and test/, then one folder per class named <crop>__<problem>.
labels.csv has one row per photo. classes.json counts photos per class and set.

Every photo was labelled by a person (an agronomist), and the farmer agreed to its use for improving crop diagnosis.
Photos are split by farmer, so no farm appears in more than one set. Location data was removed from the images and no
names or phone numbers are included. Please keep it that way.
"""


def build_export(user):
    """Returns (open zip file positioned at the start, DatasetExport). Duplicates and unreadable files are skipped."""
    buffer = tempfile.TemporaryFile()
    seen, skipped, rows = set(), 0, []
    counts = {s: 0 for s in (LabeledImage.TRAIN, LabeledImage.VAL, LabeledImage.TEST)}
    classes = {}

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for label in eligible().select_related("message", "message__conversation").order_by("pk"):
            try:
                data = _clean_jpeg(label.message.photo.path)
            except Exception:
                skipped += 1
                continue
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen:
                skipped += 1
                continue
            seen.add(digest)
            path = f"{label.split}/{label.class_key}/{label.pk}.jpg"
            archive.writestr(path, data)
            counts[label.split] += 1
            classes.setdefault(label.class_key, {"crop": label.crop, "problem": label.problem, "train": 0, "val": 0, "test": 0})[label.split] += 1
            rows.append([
                path, label.split, label.crop, label.problem, label.problem_type, label.label_source,
                "yes" if label.ai_agrees else "no", label.message.conversation.region, f"{label.message.created_at:%Y-%m}",
            ])

        sheet = io.StringIO()
        writer = csv.writer(sheet)
        writer.writerow(["path", "split", "crop", "problem", "problem_type", "labelled_by", "ai_agreed", "region", "month"])
        writer.writerows(rows)
        archive.writestr("labels.csv", sheet.getvalue())
        archive.writestr("classes.json", json.dumps(classes, indent=2, ensure_ascii=False, sort_keys=True))
        archive.writestr("README.txt", README)

    export = DatasetExport.objects.create(
        exported_by=user, image_count=sum(counts.values()), class_count=len(classes), split_counts=counts, skipped=skipped,
    )
    buffer.seek(0)
    return buffer, export

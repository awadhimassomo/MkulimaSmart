"""
Labelled photos for building our own crop-diagnosis model.

An agronomist looks at a farmer's photo (only photos the farmer agreed to share, see assistant.consent) and says what
crop it is and what is wrong. That confirmed label, not the AI's guess, is what the dataset is made of. Each labelled photo
is placed in the train, validation or test set automatically, by farmer, so one farm's photos never land in two sets.
"""
from django.conf import settings
from django.db import models

PROBLEM_TYPES = [
    ("disease", "Disease"),
    ("pest", "Pest"),
    ("nutrient_deficiency", "Nutrient deficiency"),
    ("water_stress", "Water stress"),
    ("weed", "Weed"),
    ("soil", "Soil"),
    ("healthy", "Healthy"),
    ("other", "Other"),
]


class LabeledImage(models.Model):
    TRAIN, VAL, TEST = "train", "val", "test"
    SPLIT_CHOICES = [(TRAIN, "Train"), (VAL, "Validation"), (TEST, "Test")]
    SOURCE_CHOICES = [("agronomist", "Agronomist"), ("ops", "Administrator")]

    message = models.OneToOneField("assistant.Message", on_delete=models.CASCADE, related_name="label")
    crop = models.CharField(max_length=80)
    crop_key = models.CharField(max_length=80, db_index=True)
    problem = models.CharField(max_length=120)
    problem_key = models.CharField(max_length=120, db_index=True)
    problem_type = models.CharField(max_length=20, choices=PROBLEM_TYPES, default="other")
    is_rejected = models.BooleanField(default=False, help_text="Not usable: blurry, not a crop, or no clear subject.")
    reject_reason = models.CharField(max_length=120, blank=True)
    label_source = models.CharField(max_length=12, choices=SOURCE_CHOICES, default="agronomist")
    labeled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="+")
    labeled_at = models.DateTimeField(auto_now=True)
    ai_crop = models.CharField(max_length=80, blank=True, help_text="What the AI said at the time, kept to measure how often it was right.")
    ai_problem = models.CharField(max_length=120, blank=True)
    split = models.CharField(max_length=5, choices=SPLIT_CHOICES, db_index=True)

    class Meta:
        ordering = ["-labeled_at"]

    def __str__(self):
        return f"{self.crop} / {self.problem} ({self.split})"

    @property
    def class_key(self):
        return f"{self.crop_key}__{self.problem_key}"

    @property
    def ai_agrees(self):
        return bool(self.ai_crop) and self.ai_crop.strip().lower() == self.crop.strip().lower() and (
            self.ai_problem.strip().lower() == self.problem.strip().lower()
        )


class DatasetExport(models.Model):
    """A record of each time the dataset was downloaded."""

    exported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    image_count = models.PositiveIntegerField(default=0)
    class_count = models.PositiveIntegerField(default=0)
    split_counts = models.JSONField(default=dict, blank=True)
    skipped = models.PositiveIntegerField(default=0, help_text="Labelled photos left out (file missing, unreadable or a duplicate).")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Export of {self.image_count} photos on {self.created_at:%Y-%m-%d %H:%M}"

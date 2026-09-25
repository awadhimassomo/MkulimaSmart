from django import forms

from operations.forms import StyledModelForm
from operations.models import TANZANIA_REGIONS

from .models import IMAGE_VALIDATORS, ShopStockItem, WholesaleProduct

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES_PER_UPLOAD = 8

CROP_SUGGESTIONS = [
    "Maize", "Rice", "Beans", "Sorghum", "Sunflower", "Cassava", "Irish potato", "Sweet potato",
    "Tomato", "Onion", "Cabbage", "Watermelon", "Coffee", "Tea", "Cashew", "Cotton", "Tobacco",
    "Sugarcane", "Banana", "Avocado", "Groundnuts", "Sesame", "Pigeon peas", "Wheat",
]

# Fields every product must have, and extra fields each category requires.
# Kept here (not only in templates) so the web form and any future API enforce the same rules.
ALWAYS_REQUIRED_FIELDS = [
    "name", "brand", "category", "pack_size", "unit", "wholesale_price", "min_order_quantity", "stock_available",
]
CATEGORY_REQUIRED_FIELDS = {
    "fertilizer": ["composition", "registration_number"],
    "pesticides": ["composition", "registration_number", "toxicity_class", "safety_precautions"],
    "seeds": ["seed_variety", "registration_number", "suitable_regions", "soil_type"],
    "seedlings": ["seed_variety", "suitable_regions", "soil_type"],
}
PESTICIDE_ONLY_FIELDS = ["toxicity_class"]
SEED_ONLY_FIELDS = ["seed_variety", "maturity_days", "germination_rate"]


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    """ImageField that accepts several files from one <input multiple>."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleImageInput(attrs={"accept": "image/*"}))
        kwargs.setdefault("validators", IMAGE_VALIDATORS)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        if len(files) > MAX_IMAGES_PER_UPLOAD:
            raise forms.ValidationError(f"Upload at most {MAX_IMAGES_PER_UPLOAD} images at a time.")
        cleaned = [super(MultipleImageField, self).clean(f, initial) for f in files]
        for image in cleaned:
            validate_image_size(image)
        return cleaned


def validate_image_size(image):
    if image and getattr(image, "size", 0) > MAX_IMAGE_BYTES:
        raise forms.ValidationError(f"{image.name} is larger than 5 MB.")


class CropListField(forms.CharField):
    """Comma-separated text in the form, a clean de-duplicated list of crop names in the model."""

    def prepare_value(self, value):
        if isinstance(value, (list, tuple)):
            return ", ".join(value)
        return value

    def to_python(self, value):
        # Accepts "Maize, Beans", ["Maize", "Beans"], or repeated multipart fields, even ["Maize,Beans"].
        values = value if isinstance(value, (list, tuple)) else [value or ""]
        items = [part for v in values for part in str(v).split(",")]
        seen, crops = set(), []
        for item in items:
            crop = item.strip()[:60]
            if crop and crop.lower() not in seen:
                seen.add(crop.lower())
                crops.append(crop)
        return crops


class WholesaleProductForm(StyledModelForm):
    new_images = MultipleImageField(
        required=False,
        label="Product photos",
        help_text="JPG, PNG or WebP, up to 5 MB each, at most 8 at a time. The first photo becomes the cover if none is set.",
    )
    target_crops = CropListField(
        required=False,
        label="Target crops",
        help_text="Separate with commas, e.g. Maize, Beans, Sunflower.",
        widget=forms.TextInput(attrs={"list": "crop-suggestions", "autocomplete": "off"}),
    )
    suitable_regions = forms.MultipleChoiceField(
        required=False, choices=TANZANIA_REGIONS, widget=forms.CheckboxSelectMultiple,
        label="Suitable regions",
        help_text="Tick every region this performs well in, so farmers can tell it suits their area.",
    )
    soil_type = forms.MultipleChoiceField(
        required=False, choices=WholesaleProduct.SOIL_TYPE_CHOICES, widget=forms.CheckboxSelectMultiple,
        label="Suitable soil type",
        help_text="Tick every soil type this performs well in.",
    )

    class Meta:
        model = WholesaleProduct
        fields = [
            "name",
            "brand",
            "category",
            "pack_size",
            "unit",
            "wholesale_price",
            "suggested_retail_price",
            "min_order_quantity",
            "stock_available",
            "composition",
            "registration_authority",
            "registration_number",
            "target_crops",
            "suitable_regions",
            "soil_type",
            "usage_instructions",
            "toxicity_class",
            "safety_precautions",
            "seed_variety",
            "maturity_days",
            "germination_rate",
            "shelf_life_months",
            "description",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "usage_instructions": forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. 1 bag per acre at planting, top-dress after 4 weeks"}),
            "safety_precautions": forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. Wear gloves and mask. Pre-harvest interval 14 days."}),
            "composition": forms.TextInput(attrs={"placeholder": "e.g. 18-46-0 or Lambda-cyhalothrin 5% EC"}),
            "pack_size": forms.TextInput(attrs={"placeholder": "e.g. 50 kg, 1 litre, 2 kg"}),
        }
        labels = {
            "wholesale_price": "Wholesale price (TZS)",
            "suggested_retail_price": "Suggested retail price (TZS)",
            "stock_available": "Units available to ship",
            "composition": "Composition / active ingredient",
            "registration_authority": "Registered with",
            "germination_rate": "Germination rate (%)",
            "maturity_days": "Days to maturity",
            "shelf_life_months": "Shelf life (months)",
            "toxicity_class": "WHO toxicity class",
            "is_active": "Visible to shops",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ALWAYS_REQUIRED_FIELDS:
            self.fields[name].required = True
        self.fields["registration_authority"].help_text = "Filled in from the category if left blank."

    def _has_photo(self, new_images):
        if new_images:
            return True
        return bool(self.instance.pk and self.instance.images.exists())

    def clean(self):
        cleaned = super().clean()
        wholesale = cleaned.get("wholesale_price")
        retail = cleaned.get("suggested_retail_price")
        if wholesale is not None and retail is not None and retail < wholesale:
            self.add_error("suggested_retail_price", "Suggested retail price should not be below the wholesale price.")

        category = cleaned.get("category")
        category_label = dict(self.fields["category"].choices).get(category, category)
        for name in CATEGORY_REQUIRED_FIELDS.get(category, []):
            if name not in self.errors and cleaned.get(name) in (None, "", []):
                self.add_error(name, f"Required for {category_label}.")

        if category in WholesaleProduct.CATEGORY_REGULATOR and not cleaned.get("registration_authority"):
            cleaned["registration_authority"] = WholesaleProduct.CATEGORY_REGULATOR[category]

        # Clear values that don't apply to the chosen category, so stale data isn't shown to shops.
        if category != "pesticides":
            for name in PESTICIDE_ONLY_FIELDS:
                cleaned[name] = ""
        if category not in ("seeds", "seedlings"):
            cleaned["seed_variety"] = ""
            cleaned["maturity_days"] = None
            cleaned["germination_rate"] = None

        if "new_images" not in self.errors and not self._has_photo(cleaned.get("new_images")):
            self.add_error("new_images", "Add at least one photo so shops can recognise the product.")
        return cleaned


class ShopStockItemForm(StyledModelForm):
    class Meta:
        model = ShopStockItem
        fields = [
            "name", "brand", "category", "sku", "unit", "cost_price", "selling_price", "quantity", "reorder_level",
            "batch_number", "expiry_date", "image", "is_active",
        ]
        widgets = {"expiry_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        labels = {
            "cost_price": "Cost price (TZS)",
            "selling_price": "Selling price (TZS)",
            "quantity": "Quantity in stock",
            "reorder_level": "Alert me when stock falls to",
            "batch_number": "Batch / lot number",
            "is_active": "Available in POS",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].widget.attrs["accept"] = "image/*"
        self.fields["expiry_date"].help_text = "Required for seeds and pesticides. You'll be warned 60 days before."
        if self.instance.pk:
            # Quantity changes after creation must go through stock adjustments so they are audited.
            del self.fields["quantity"]

    def clean_image(self):
        image = self.cleaned_data.get("image")
        validate_image_size(image)
        return image

    def clean(self):
        cleaned = super().clean()
        cost = cleaned.get("cost_price")
        price = cleaned.get("selling_price")
        if cost is not None and price is not None and price < cost:
            self.add_error("selling_price", "Selling price is below cost price.")
        if cleaned.get("category") in ("seeds", "pesticides") and not cleaned.get("expiry_date") and "expiry_date" not in self.errors:
            self.add_error("expiry_date", "Expiry date is required for seeds and pesticides.")
        return cleaned


class StockAdjustmentForm(forms.Form):
    change = forms.DecimalField(
        max_digits=12, decimal_places=2, label="Change",
        help_text="Positive to add stock, negative to remove (e.g. -2 for damaged bags).",
        widget=forms.NumberInput(attrs={"class": "form-input", "step": "0.01"}),
    )
    note = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Reason"}))

"""
Input supply chain: manufacturers publish a wholesale catalog, input shops
(agro-dealers) order stock from it and sell to farmers through a POS.

Both sides are represented by operations.InputSeller profiles; a profile with
seller_type == "manufacturer" is a manufacturer, anything else is a shop.
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from operations.models import TANZANIA_REGIONS, InputSeller

IMAGE_VALIDATORS = [FileExtensionValidator(["jpg", "jpeg", "png", "webp"])]
ZERO = Decimal("0")


def _reference(prefix):
    return f"{prefix}-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"


class WholesaleProduct(models.Model):
    """An input a manufacturer offers to shops at wholesale price."""

    UNIT_CHOICES = [
        ("bag", "Bag"),
        ("kg", "Kilogram"),
        ("litre", "Litre"),
        ("bottle", "Bottle"),
        ("packet", "Packet"),
        ("carton", "Carton"),
        ("piece", "Piece"),
    ]

    REGULATOR_CHOICES = [
        ("tfra", "TFRA (fertilizers)"),
        ("tphpa", "TPHPA / former TPRI (pesticides)"),
        ("tosci", "TOSCI (seeds)"),
        ("other", "Other"),
    ]
    # Which regulator registers each category; drives the default and the required fields.
    CATEGORY_REGULATOR = {"fertilizer": "tfra", "pesticides": "tphpa", "seeds": "tosci"}

    SOIL_TYPE_CHOICES = [
        ("clay", "Clay"),
        ("clay_loam", "Clay loam"),
        ("sandy", "Sandy"),
        ("sandy_loam", "Sandy loam"),
        ("loam", "Loam (well-balanced)"),
        ("volcanic", "Volcanic / black cotton soil"),
        ("red_soil", "Red soil"),
        ("well_drained", "Any well-drained soil"),
    ]

    TOXICITY_CHOICES = [
        ("Ia", "Ia: Extremely hazardous"),
        ("Ib", "Ib: Highly hazardous"),
        ("II", "II: Moderately hazardous"),
        ("III", "III: Slightly hazardous"),
        ("U", "U: Unlikely to present acute hazard"),
    ]

    manufacturer = models.ForeignKey(InputSeller, on_delete=models.CASCADE, related_name="wholesale_products")
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=30, choices=InputSeller.PRODUCT_CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    pack_size = models.CharField(max_length=60, blank=True, help_text="e.g. 50 kg, 1 litre, 100 g")

    # Composition and regulation
    composition = models.CharField(
        max_length=255, blank=True,
        help_text="NPK ratio for fertilizer (e.g. 18-46-0) or active ingredient and strength for pesticides.",
    )
    registration_authority = models.CharField(max_length=10, choices=REGULATOR_CHOICES, blank=True)
    registration_number = models.CharField(max_length=60, blank=True)

    # Agronomy: where and on what soil this performs well, so a farmer or shop can tell
    # at a glance whether it suits their area instead of having to ask in Farmer Talk.
    target_crops = models.JSONField(default=list, blank=True, help_text="List of crop names, e.g. [\"Maize\", \"Beans\"].")
    suitable_regions = models.JSONField(
        default=list, blank=True,
        help_text="Tanzania regions this performs well in. Required for seeds and seedlings.",
    )
    soil_type = models.JSONField(
        default=list, blank=True,
        help_text="Soil types this suits, e.g. [\"clay_loam\", \"well_drained\"]. Required for seeds and seedlings.",
    )
    usage_instructions = models.TextField(blank=True, help_text="Application rate and timing.")

    # Pesticide safety
    toxicity_class = models.CharField(max_length=4, choices=TOXICITY_CHOICES, blank=True)
    safety_precautions = models.TextField(blank=True, help_text="Protective equipment, re-entry and pre-harvest intervals.")

    # Seeds
    seed_variety = models.CharField(max_length=120, blank=True)
    maturity_days = models.PositiveSmallIntegerField(blank=True, null=True)
    germination_rate = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("100"))],
    )

    shelf_life_months = models.PositiveSmallIntegerField(blank=True, null=True)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default="bag")
    wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])
    suggested_retail_price = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(ZERO)]
    )
    min_order_quantity = models.PositiveIntegerField(default=1)
    stock_available = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.pack_size})" if self.pack_size else self.name

    @property
    def target_crops_display(self):
        return ", ".join(self.target_crops or [])

    @property
    def suitable_regions_display(self):
        return ", ".join(self.suitable_regions or [])

    @property
    def soil_type_display(self):
        labels = dict(self.SOIL_TYPE_CHOICES)
        return ", ".join(labels.get(v, v) for v in (self.soil_type or []))

    @property
    def primary_image(self):
        images = list(self.images.all())
        for image in images:
            if image.is_primary:
                return image
        return images[0] if images else None


class WholesaleProductImage(models.Model):
    product = models.ForeignKey(WholesaleProduct, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="inputs/wholesale/", validators=IMAGE_VALIDATORS)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "created_at"]

    def __str__(self):
        return f"Image for {self.product}"


class ShopStockItem(models.Model):
    """A line of inventory held by an input shop and sold through the POS."""

    shop = models.ForeignKey(InputSeller, on_delete=models.CASCADE, related_name="stock_items")
    wholesale_product = models.ForeignKey(
        WholesaleProduct, on_delete=models.SET_NULL, blank=True, null=True, related_name="shop_stock_items"
    )
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=30, choices=InputSeller.PRODUCT_CATEGORY_CHOICES, default="other")
    sku = models.CharField("SKU / barcode", max_length=64, blank=True)
    batch_number = models.CharField(max_length=60, blank=True)
    expiry_date = models.DateField(blank=True, null=True)
    unit = models.CharField(max_length=20, choices=WholesaleProduct.UNIT_CHOICES, default="piece")
    image = models.ImageField(upload_to="inputs/stock/", blank=True, null=True, validators=IMAGE_VALIDATORS)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)])
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)])
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("5"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_level

    EXPIRY_WARNING_DAYS = 60

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())

    @property
    def expires_soon(self):
        if not self.expiry_date or self.is_expired:
            return False
        return (self.expiry_date - timezone.localdate()).days <= self.EXPIRY_WARNING_DAYS

    @property
    def stock_value(self):
        return self.quantity * self.cost_price

    @property
    def margin_percent(self):
        """Markup on cost, e.g. cost 100 / price 125 -> 25."""
        if not self.cost_price:
            return None
        return round((self.selling_price - self.cost_price) / self.cost_price * 100)


class StockMovement(models.Model):
    """Audit trail for every change to a shop's stock quantity."""

    REASON_CHOICES = [
        ("opening", "Opening stock"),
        ("sale", "Sale"),
        ("restock", "Received from order"),
        ("adjustment", "Manual adjustment"),
        ("farmer_order", "Reserved for farmer order"),
        ("order_cancelled", "Farmer order cancelled"),
    ]

    stock_item = models.ForeignKey(ShopStockItem, on_delete=models.CASCADE, related_name="movements")
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    change = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=40, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.stock_item} {self.change:+}"


class Sale(models.Model):
    # Methods a cashier can pick in the POS.
    POS_PAYMENT_CHOICES = [
        ("cash", "Cash"),
        ("mobile_money", "Mobile money"),
        ("bank", "Bank / card"),
        ("credit", "Credit"),
    ]
    PAYMENT_CHOICES = POS_PAYMENT_CHOICES + [("on_delivery", "Paid on delivery")]
    CHANNEL_CHOICES = [
        ("pos", "Shop counter (POS)"),
        ("kikapu", "Kikapu WhatsApp order"),
    ]

    shop = models.ForeignKey(InputSeller, on_delete=models.CASCADE, related_name="sales")
    receipt_number = models.CharField(max_length=32, unique=True, editable=False)
    customer_name = models.CharField(max_length=120, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default="cash")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="pos")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    sold_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.receipt_number

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = _reference("RC")
        super().save(*args, **kwargs)

    @property
    def change_due(self):
        return max(self.amount_paid - self.total, ZERO)

    @property
    def balance_due(self):
        return max(self.total - self.amount_paid, ZERO)

    @property
    def cost_total(self):
        return sum((item.cost_price * item.quantity for item in self.items.all()), ZERO)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    stock_item = models.ForeignKey(ShopStockItem, on_delete=models.SET_NULL, blank=True, null=True, related_name="sale_items")
    product_name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"


class PurchaseOrder(models.Model):
    """A shop's order for stock from one manufacturer."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("dispatched", "Dispatched"),
        ("received", "Received"),
        ("cancelled", "Cancelled"),
    ]
    OPEN_STATUSES = ("pending", "confirmed", "dispatched")

    shop = models.ForeignKey(InputSeller, on_delete=models.CASCADE, related_name="purchase_orders")
    manufacturer = models.ForeignKey(InputSeller, on_delete=models.CASCADE, related_name="incoming_orders")
    order_number = models.CharField(max_length=32, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True)
    manufacturer_note = models.TextField(blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    received_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = _reference("PO")
        super().save(*args, **kwargs)

    def recalculate_total(self):
        self.total = self.items.aggregate(
            total=Sum(ExpressionWrapper(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=14, decimal_places=2)))
        )["total"] or ZERO
        self.save(update_fields=["total", "updated_at"])


class PurchaseOrderItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    wholesale_product = models.ForeignKey(WholesaleProduct, on_delete=models.SET_NULL, blank=True, null=True, related_name="order_items")
    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class FarmerOrder(models.Model):
    """
    An order a farmer places with an input shop from outside the shop, currently via Kikapu's
    WhatsApp number. Stock is reserved when the order is accepted and returned if it is cancelled;
    a Sale is recorded when it is delivered.
    """

    STATUS_CHOICES = [
        ("pending", "New"),
        ("confirmed", "Confirmed"),
        ("dispatched", "Dispatched"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]
    OPEN_STATUSES = ("pending", "confirmed", "dispatched")
    # Allowed next statuses for the shop.
    TRANSITIONS = {
        "pending": ("confirmed", "cancelled"),
        "confirmed": ("dispatched", "cancelled"),
        "dispatched": ("delivered",),
        "delivered": (),
        "cancelled": (),
    }
    CHANNEL_CHOICES = [("kikapu", "Kikapu WhatsApp")]

    shop = models.ForeignKey(InputSeller, on_delete=models.CASCADE, related_name="farmer_orders")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="kikapu")
    external_order_id = models.CharField(max_length=64, help_text="The caller's order id, e.g. Kikapu's KP-INP-00482.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    farmer_name = models.CharField(max_length=120)
    farmer_phone = models.CharField(max_length=30)
    farmer_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="farmer_orders")
    delivery_region = models.CharField(max_length=60, blank=True)
    delivery_notes = models.TextField(blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    shop_note = models.CharField(max_length=255, blank=True, help_text="Latest message for the farmer, sent with status updates.")
    sale = models.OneToOneField(Sale, on_delete=models.SET_NULL, blank=True, null=True, related_name="farmer_order")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["channel", "external_order_id"], name="unique_external_farmer_order"),
        ]

    def __str__(self):
        return self.order_number

    @property
    def order_number(self):
        return f"MS-{self.pk}" if self.pk else "MS-new"

    @property
    def allowed_next_statuses(self):
        return list(self.TRANSITIONS.get(self.status, ()))


class FarmerOrderItem(models.Model):
    order = models.ForeignKey(FarmerOrder, on_delete=models.CASCADE, related_name="items")
    stock_item = models.ForeignKey(ShopStockItem, on_delete=models.SET_NULL, blank=True, null=True, related_name="farmer_order_items")
    product_name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

from django import forms
from django.utils.text import slugify

from website.models import Category, Product, ProductImage


def generate_unique_slug(name, instance=None):
    base_slug = slugify(name) or "product"
    slug = base_slug
    counter = 2

    queryset = Product.objects.all()
    if instance and instance.pk:
        queryset = queryset.exclude(pk=instance.pk)

    while queryset.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


class SupplierProductForm(forms.ModelForm):
    primary_image = forms.ImageField(required=False)

    class Meta:
        model = Product
        fields = [
            "category",
            "name",
            "description",
            "price",
            "discount_price",
            "stock",
            "is_hydroponics",
            "requires_quote",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")
        self.fields["category"].empty_label = "Select a category"
        self.fields["category"].help_text = "Choose the best fit for what you are selling."
        self.fields["primary_image"].help_text = "Optional cover image for the listing."

        for _, field in self.fields.items():
            widget = field.widget
            existing = widget.attrs.get("class", "")

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = (
                    f"h-4 w-4 rounded border-gray-300 text-[var(--brand-primary)] "
                    f"focus:ring-[var(--brand-accent)] {existing}"
                ).strip()
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = f"form-select {existing}".strip()
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs["class"] = (
                    "block w-full text-sm text-gray-600 "
                    "file:mr-4 file:rounded-xl file:border-0 "
                    "file:bg-[var(--brand-primary)] file:px-4 file:py-2 file:text-white "
                    f"{existing}"
                ).strip()
            else:
                widget.attrs["class"] = f"form-input {existing}".strip()

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get("price")
        discount_price = cleaned_data.get("discount_price")

        if price is not None and discount_price is not None and discount_price > price:
            self.add_error("discount_price", "Discount price cannot be higher than the main price.")

        return cleaned_data

    def save(self, supplier, commit=True):
        product = super().save(commit=False)
        product.supplier = supplier

        if not product.slug or "name" in self.changed_data:
            product.slug = generate_unique_slug(product.name, instance=product)

        if commit:
            product.save()
            self.save_m2m()

            image = self.cleaned_data.get("primary_image")
            if image:
                primary = product.images.filter(is_primary=True).first()
                if primary:
                    primary.image = image
                    primary.save(update_fields=["image"])
                else:
                    ProductImage.objects.create(product=product, image=image, is_primary=True)

        return product

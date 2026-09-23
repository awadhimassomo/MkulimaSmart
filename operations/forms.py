import json

from django import forms
from django.contrib.auth import get_user_model

from website.models import Farm

from .models import PlantingRecord

User = get_user_model()


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            existing = widget.attrs.get("class", "")

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f"h-5 w-5 rounded border-gray-300 text-[var(--brand-primary)] focus:ring-[var(--brand-accent)] {existing}".strip()
                continue

            if isinstance(widget, forms.Textarea):
                widget.attrs["class"] = f"form-input min-h-32 {existing}".strip()
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = f"form-select {existing}".strip()
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs["class"] = f"block w-full text-sm text-gray-600 file:mr-4 file:rounded-xl file:border-0 file:bg-[var(--brand-primary)] file:px-4 file:py-2 file:text-white {existing}".strip()
            else:
                widget.attrs["class"] = f"form-input {existing}".strip()


class PlantingRecordForm(StyledModelForm):
    farmer_name_input = forms.CharField(required=False, label="Farmer name")
    farm_name_input = forms.CharField(required=False, label="Farm name")
    boundary = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), help_text="Optional JSON farm boundary payload.")

    class Meta:
        model = PlantingRecord
        fields = [
            "farmer",
            "farmer_name_input",
            "farmer_phone",
            "farmer_email",
            "farm",
            "farm_name_input",
            "seedling_batch",
            "crop_type",
            "planting_date",
            "expected_harvest_date",
            "expected_quantity",
            "unit",
            "farm_location",
            "region",
            "farm_size",
            "farm_size_unit",
            "notes",
            "photo",
        ]
        widgets = {
            "planting_date": forms.DateInput(attrs={"type": "date"}),
            "expected_harvest_date": forms.DateInput(attrs={"type": "date"}),
            "seedling_batch": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        seedling_batch = kwargs.pop("seedling_batch", None)
        super().__init__(*args, **kwargs)

        self.user = user
        self.seedling_batch = seedling_batch

        self.fields["farmer"].required = False
        self.fields["farm"].required = False
        self.fields["farmer_phone"].required = True
        self.fields["crop_type"].required = True
        self.fields["planting_date"].required = True
        self.fields["farm_location"].required = True
        self.fields["farm_size_unit"].initial = "hectares"
        self.fields["expected_quantity"].label = "Expected quantity"
        self.fields["farm_location"].label = "Farm location"

        if user and getattr(user, "is_authenticated", False) and not user.is_staff:
            self.fields["farm"].queryset = Farm.objects.filter(owner=user)
            self.fields["farmer"].initial = user
            self.fields["farmer"].queryset = self.fields["farmer"].queryset.filter(pk=user.pk)
            self.fields["farmer_phone"].initial = user.phone_number
            self.fields["farmer_email"].initial = user.email
            self.fields["farmer_name_input"].initial = user.get_full_name()
        elif user and getattr(user, "is_authenticated", False):
            self.fields["farmer"].queryset = User.objects.order_by("first_name", "last_name", "phone_number")
            self.fields["farm"].queryset = Farm.objects.select_related("owner").order_by("name")
        else:
            self.fields["farmer"].queryset = User.objects.none()
            self.fields["farm"].queryset = Farm.objects.none()
            self.fields["farmer"].help_text = "Use the farmer name field below when coming from a QR scan."
            self.fields["farm"].help_text = "Use the farm name field below when coming from a QR scan."

        if seedling_batch:
            self.fields["seedling_batch"].initial = seedling_batch
            self.fields["seedling_batch"].widget = forms.HiddenInput()
            self.fields["crop_type"].initial = seedling_batch.seedling_type
            self.fields["crop_type"].help_text = f"Seedling batch: {seedling_batch.seedling_batch_id}"

        if self.instance.pk:
            self.fields["farmer_name_input"].initial = self.instance.farmer_name or self.instance.farmer.get_full_name()
            self.fields["farm_name_input"].initial = self.instance.farm_name or self.instance.farm.name
            self.fields["farm_location"].initial = self.instance.farm_location or self.instance.location or self.instance.farm.location
            self.fields["expected_quantity"].initial = self.instance.expected_quantity or self.instance.expected_yield

        self.order_fields([
            "farmer",
            "farmer_name_input",
            "farmer_phone",
            "farmer_email",
            "farm",
            "farm_name_input",
            "crop_type",
            "planting_date",
            "expected_harvest_date",
            "expected_quantity",
            "unit",
            "farm_location",
            "region",
            "farm_size",
            "farm_size_unit",
            "photo",
            "notes",
            "seedling_batch",
        ])

    def clean_boundary(self):
        boundary = self.cleaned_data.get("boundary")
        if not boundary:
            return None
        try:
            return json.loads(boundary)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Boundary must be valid JSON.") from exc

    def clean(self):
        cleaned_data = super().clean()
        farmer = cleaned_data.get("farmer")
        farmer_name_input = (cleaned_data.get("farmer_name_input") or "").strip()
        farm = cleaned_data.get("farm")
        farm_name_input = (cleaned_data.get("farm_name_input") or "").strip()
        planting_date = cleaned_data.get("planting_date")
        expected_harvest_date = cleaned_data.get("expected_harvest_date")

        if not farmer and not farmer_name_input:
            self.add_error("farmer_name_input", "Farmer name is required when no existing farmer is selected.")

        if not farm and not farm_name_input:
            self.add_error("farm_name_input", "Farm name is required when no existing farm is selected.")

        if expected_harvest_date and planting_date and expected_harvest_date < planting_date:
            self.add_error("expected_harvest_date", "Expected harvest date cannot be earlier than planting date.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        farmer = self.cleaned_data.get("farmer")
        farm = self.cleaned_data.get("farm")
        farmer_name_input = (self.cleaned_data.get("farmer_name_input") or "").strip()
        farm_name_input = (self.cleaned_data.get("farm_name_input") or "").strip()
        farmer_phone = (self.cleaned_data.get("farmer_phone") or "").strip()
        farmer_email = (self.cleaned_data.get("farmer_email") or "").strip()
        farm_location = (self.cleaned_data.get("farm_location") or "").strip()
        farm_size = self.cleaned_data.get("farm_size")

        if farmer is None:
            farmer = User.objects.filter(phone_number=farmer_phone).first()
            if farmer is None:
                first_name, _, last_name = farmer_name_input.partition(" ")
                farmer = User.objects.create_user(
                    phone_number=farmer_phone,
                    password=None,
                    first_name=first_name.strip(),
                    last_name=last_name.strip(),
                    email=farmer_email,
                    is_farmer=True,
                )
            else:
                updated_fields = []
                if farmer_name_input and not farmer.get_full_name().strip():
                    first_name, _, last_name = farmer_name_input.partition(" ")
                    farmer.first_name = first_name.strip()
                    farmer.last_name = last_name.strip()
                    updated_fields.extend(["first_name", "last_name"])
                if farmer_email and not farmer.email:
                    farmer.email = farmer_email
                    updated_fields.append("email")
                if updated_fields:
                    farmer.save(update_fields=updated_fields)

        if farm is None:
            farm = Farm.objects.filter(owner=farmer, name__iexact=farm_name_input).first()
            if farm is None:
                farm = Farm.objects.create(
                    owner=farmer,
                    name=farm_name_input,
                    location=farm_location,
                    size=farm_size or 0,
                )
            else:
                updated_fields = []
                if farm_location and not farm.location:
                    farm.location = farm_location
                    updated_fields.append("location")
                if farm_size and not farm.size:
                    farm.size = farm_size
                    updated_fields.append("size")
                if updated_fields:
                    farm.save(update_fields=updated_fields)

        instance.farmer = farmer
        instance.farm = farm
        instance.seedling_batch = self.seedling_batch or self.cleaned_data.get("seedling_batch")
        instance.farmer_name = farmer_name_input or farmer.get_full_name() or farmer.phone_number
        instance.farmer_phone = farmer_phone or farmer.phone_number
        instance.farmer_email = farmer_email or farmer.email or ""
        instance.farm_name = farm_name_input or farm.name
        instance.farm_location = farm_location or farm.location
        instance.location = instance.farm_location
        instance.farm_size = farm_size if farm_size is not None else farm.size
        instance.quantity_planted = self.cleaned_data.get("expected_quantity")
        instance.expected_yield = self.cleaned_data.get("expected_quantity")

        if commit:
            instance.save()
            self.save_m2m()
        return instance

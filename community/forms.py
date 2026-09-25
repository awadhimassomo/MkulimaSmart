from django import forms

from inputs.forms import CROP_SUGGESTIONS

from .models import Discussion, Reply


class StyledFormMixin:
    def _style(self):
        for field in self.fields.values():
            widget = field.widget
            existing = widget.attrs.get("class", "")
            if isinstance(widget, forms.Textarea):
                widget.attrs["class"] = f"form-input min-h-32 {existing}".strip()
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = f"form-select {existing}".strip()
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs["class"] = (
                    "block w-full text-sm text-gray-600 file:mr-4 file:rounded-xl file:border-0 "
                    f"file:bg-[var(--brand-primary)] file:px-4 file:py-2 file:text-white {existing}"
                ).strip()
            else:
                widget.attrs["class"] = f"form-input {existing}".strip()


class DiscussionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Discussion
        fields = ["kind", "crop", "seed_variety", "title", "body", "region", "photo"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 6, "placeholder": "What did you plant, how much land, what happened, what would you do differently?"}),
            "title": forms.TextInput(attrs={"placeholder": "e.g. Zamseed 606 on 1 acre — 3 packets, 145 debe harvest"}),
            "crop": forms.TextInput(attrs={"list": "crop-suggestions", "autocomplete": "off", "placeholder": "e.g. Maize"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.crop_suggestions = CROP_SUGGESTIONS
        self.fields["crop"].required = True
        self.fields["title"].required = True
        self.fields["body"].required = True
        self._style()


class ReplyForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Reply
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Add your own experience or ask a follow-up question…"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].label = ""
        self._style()

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from assistant.models import Message
from callcenter.models import Agronomist

from . import services
from .models import DatasetExport, PROBLEM_TYPES

SKIPPED_KEY = "label_skipped"


def labeller_required(view_func):
    """Active agronomists label photos; administrators may too."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        agronomist = Agronomist.objects.filter(user=request.user, is_active=True).first()
        if agronomist is None and not request.user.is_superuser:
            return render(request, "callcenter/not_agronomist.html", status=403)
        request.label_source = "agronomist" if agronomist else "ops"
        return view_func(request, *args, **kwargs)

    return wrapper


def superuser_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("gova_pp:login")
        if not request.user.is_superuser:
            return render(request, "opsdash/forbidden.html", status=403)
        return view_func(request, *args, **kwargs)

    return wrapper


@labeller_required
def station(request):
    skipped = request.session.get(SKIPPED_KEY, [])
    wanted = request.GET.get("photo")
    if wanted and str(wanted).isdigit():
        message = services.labelable(Message.objects.filter(pk=int(wanted))).select_related("conversation").first()
        remaining = services.labelable().count()
    else:
        message, remaining = services.next_photo(skipped)
    if message is None:
        return render(request, "trainingdata/label_empty.html", {"skipped": len(skipped)})
    guess = services.ai_guess(message)
    return render(request, "trainingdata/label.html", {
        "message": message,
        "guess": guess,
        "remaining": remaining,
        "crops": services.CROPS,
        "problems": services.PROBLEMS,
        "problem_types": PROBLEM_TYPES,
        "region": message.conversation.region,
    })


@labeller_required
@require_POST
def save(request, pk):
    message = get_object_or_404(Message, pk=pk, kind="image")
    action = request.POST.get("action")
    if action == "skip":
        request.session[SKIPPED_KEY] = request.session.get(SKIPPED_KEY, []) + [message.pk]
        return redirect("training_data:station")
    try:
        services.save_label(
            message,
            {
                "crop": request.POST.get("crop", ""), "problem": request.POST.get("problem", ""),
                "problem_type": request.POST.get("problem_type", ""), "reject": action == "reject",
                "reject_reason": request.POST.get("reject_reason", ""),
            },
            request.user,
            request.label_source,
        )
    except services.LabelError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('training_data:station')}?photo={message.pk}")
    messages.success(request, "Saved. Thank you.")
    return redirect("training_data:station")


@superuser_required
def dataset(request):
    return render(request, "trainingdata/dataset.html", {
        "nav": "dataset", "stats": services.stats(), "exports": DatasetExport.objects.select_related("exported_by")[:10],
    })


@superuser_required
@require_POST
def export(request):
    archive, record = services.build_export(request.user)
    name = f"mkulima-crop-photos-{timezone.localdate():%Y%m%d}-{record.pk}.zip"
    return FileResponse(archive, as_attachment=True, filename=name, content_type="application/zip")

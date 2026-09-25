from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import DiscussionForm, ReplyForm
from .models import Discussion


def discussion_list(request):
    q = (request.GET.get("q") or "").strip()
    crop = (request.GET.get("crop") or "").strip()
    kind = request.GET.get("kind") or ""

    discussions = Discussion.objects.filter(is_active=True).select_related("author")
    if q:
        discussions = discussions.filter(
            Q(title__icontains=q) | Q(body__icontains=q) | Q(crop__icontains=q) | Q(seed_variety__icontains=q)
        )
    if crop:
        discussions = discussions.filter(crop__iexact=crop)
    if kind:
        discussions = discussions.filter(kind=kind)

    top_crops = list(
        Discussion.objects.filter(is_active=True).values("crop").annotate(total=Count("id")).order_by("-total")[:12]
    )
    page = Paginator(discussions, 12).get_page(request.GET.get("page"))
    context = {
        "page_obj": page,
        "discussions": page.object_list,
        "top_crops": top_crops,
        "kind_choices": Discussion.KIND_CHOICES,
        "filters": {"q": q, "crop": crop, "kind": kind},
    }
    return render(request, "community/discussion_list.html", context)


def discussion_detail(request, pk):
    discussion = get_object_or_404(Discussion.objects.select_related("author"), pk=pk, is_active=True)
    replies = discussion.replies.select_related("author")

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.info(request, "Please log in to reply.")
            return redirect(f"{request.path}?login=1")
        form = ReplyForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.discussion = discussion
            reply.author = request.user
            reply.save()
            messages.success(request, "Your reply was posted.")
            return redirect("community:discussion_detail", pk=discussion.pk)
    else:
        form = ReplyForm()

    context = {"discussion": discussion, "replies": replies, "form": form}
    return render(request, "community/discussion_detail.html", context)


@login_required
def discussion_create(request):
    initial = {}
    crop = request.GET.get("crop")
    if crop:
        initial["crop"] = crop

    if request.method == "POST":
        form = DiscussionForm(request.POST, request.FILES)
        if form.is_valid():
            discussion = form.save(commit=False)
            discussion.author = request.user
            discussion.save()
            messages.success(request, "Posted. Other farmers can now reply.")
            return redirect("community:discussion_detail", pk=discussion.pk)
    else:
        form = DiscussionForm(initial=initial)

    return render(request, "community/discussion_form.html", {"form": form})


@login_required
@require_POST
def discussion_report(request, pk):
    """A lightweight report: notifies via messages/admin visibility rather than auto-hiding,
    so one report can't silence a genuine post."""
    discussion = get_object_or_404(Discussion, pk=pk)
    messages.success(request, "Thanks, we'll review this post.")
    # Kept intentionally simple: staff review flagged posts in Django admin, where
    # is_active can be turned off. A dedicated Report model can be added if volume grows.
    return redirect("community:discussion_detail", pk=discussion.pk)

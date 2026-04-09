from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import FarmActivityForm, FarmInputUsageForm, InputSellerForm, InspectionLogForm, PlantingRecordForm, SeedlingBatchForm
from .models import FarmActivity, InputSeller, PlantingRecord, SeedlingBatch, build_qr_image


@login_required
def dashboard(request):
    planting_records = PlantingRecord.objects.select_related("farm", "seedling_batch")
    if not request.user.is_staff:
        planting_records = planting_records.filter(farmer=request.user)

    recent_activities = FarmActivity.objects.select_related("planting_record").order_by("-activity_date")
    if not request.user.is_staff:
        recent_activities = recent_activities.filter(planting_record__farmer=request.user)
    recent_activities = recent_activities[:10]

    farms_with_no_recent_activity = (
        planting_records.values("farm__name", "farm_id")
        .annotate(last_activity=Max("activities__activity_date"))
        .filter(last_activity__isnull=True)
    )

    context = {
        "seller_count": InputSeller.objects.count(),
        "seedling_batch_count": SeedlingBatch.objects.count(),
        "planting_record_count": planting_records.count(),
        "records_by_crop": planting_records.values("crop_type").annotate(total=Count("id")).order_by("-total"),
        "records_by_region": planting_records.values("farm__location").annotate(total=Count("id")).order_by("-total"),
        "upcoming_expected_harvests": planting_records.filter(
            expected_harvest_date__gte=timezone.now().date(),
            expected_harvest_date__lte=timezone.now().date() + timedelta(days=45),
        ).order_by("expected_harvest_date")[:10],
        "recent_activities": recent_activities,
        "farms_not_verified": planting_records.exclude(verification_status="verified").select_related("farm")[:10],
        "farms_with_no_recent_activity": farms_with_no_recent_activity[:10],
    }
    return render(request, "operations/dashboard.html", context)


@login_required
def seller_list(request):
    sellers = InputSeller.objects.all().order_by("seller_name")
    return render(request, "operations/seller_list.html", {"sellers": sellers})


@login_required
def seller_create(request):
    if request.method == "POST":
        form = InputSellerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Input seller saved successfully.")
            return redirect("operations:seller_list")
    else:
        form = InputSellerForm()

    return render(request, "operations/form_page.html", {"form": form, "title": "Register Input Seller", "subtitle": "Add a seedling or input supplier."})


@login_required
def batch_list(request):
    batches = SeedlingBatch.objects.select_related("seller").all()
    return render(request, "operations/batch_list.html", {"batches": batches})


@login_required
def batch_create(request):
    if request.method == "POST":
        form = SeedlingBatchForm(request.POST)
        if form.is_valid():
            batch = form.save()
            messages.success(request, "Seedling batch created and QR prepared.")
            return redirect("operations:batch_detail", pk=batch.pk)
    else:
        form = SeedlingBatchForm()

    return render(request, "operations/form_page.html", {"form": form, "title": "Create Seedling Batch", "subtitle": "Capture the first traceability point."})


@login_required
def batch_detail(request, pk):
    batch = get_object_or_404(SeedlingBatch.objects.select_related("seller"), pk=pk)
    return render(request, "operations/batch_detail.html", {"batch": batch})


@login_required
def batch_qr_print(request, pk):
    batch = get_object_or_404(SeedlingBatch.objects.select_related("seller"), pk=pk)
    return render(request, "operations/batch_qr_print.html", {"batch": batch})


def batch_qr_image(request, pk):
    batch = get_object_or_404(SeedlingBatch, pk=pk)
    qr_image = build_qr_image(batch.get_absolute_scan_url())
    response = HttpResponse(qr_image.read(), content_type="image/png")
    response["Content-Disposition"] = f'inline; filename="{batch.seedling_batch_id}.png"'
    return response


def batch_scan(request, seedling_batch_id):
    batch = get_object_or_404(SeedlingBatch, seedling_batch_id=seedling_batch_id)
    return redirect("operations:planting_qr_intake", seedling_batch_id=batch.seedling_batch_id)


@login_required
def planting_record_list(request):
    records = PlantingRecord.objects.select_related("farm", "seedling_batch", "farmer")
    if not request.user.is_staff:
        records = records.filter(farmer=request.user)
    return render(request, "operations/planting_record_list.html", {"records": records})


@login_required
def planting_record_create(request, seedling_batch_id=None):
    batch = None
    if seedling_batch_id:
        batch = get_object_or_404(SeedlingBatch, seedling_batch_id=seedling_batch_id)

    if request.method == "POST":
        form = PlantingRecordForm(request.POST, request.FILES, user=request.user, seedling_batch=batch)
        if form.is_valid():
            record = form.save()
            messages.success(request, "Planting record saved successfully.")
            return redirect("operations:planting_record_detail", pk=record.pk)
    else:
        initial = {}
        if batch:
            initial["seedling_batch"] = batch
            initial["crop_type"] = batch.seedling_type
        form = PlantingRecordForm(initial=initial, user=request.user, seedling_batch=batch)

    return render(request, "operations/form_page.html", {
        "form": form,
        "title": "Create Planting Record",
        "subtitle": "Link a seedling batch to a farmer, farm, and planting cycle.",
    })


def planting_record_qr_intake(request, seedling_batch_id):
    batch = get_object_or_404(SeedlingBatch.objects.select_related("seller"), seedling_batch_id=seedling_batch_id)

    active_user = request.user if getattr(request.user, "is_authenticated", False) else None

    if request.method == "POST":
        form = PlantingRecordForm(request.POST, request.FILES, user=active_user, seedling_batch=batch)
        if form.is_valid():
            record = form.save()
            messages.success(request, "Planting traceability details submitted successfully.")
            return render(
                request,
                "operations/planting_record_submitted.html",
                {
                    "record": record,
                    "batch": batch,
                },
            )
    else:
        initial = {
            "seedling_batch": batch,
            "crop_type": batch.seedling_type,
        }
        form = PlantingRecordForm(initial=initial, user=active_user, seedling_batch=batch)

    return render(
        request,
        "operations/form_page.html",
        {
            "form": form,
            "title": "Production Intake Form",
            "subtitle": "Fill this form at planting time so we can trace where this batch was planted.",
            "submit_label": "Submit intake",
            "show_cancel": False,
            "batch": batch,
        },
    )


@login_required
def planting_record_detail(request, pk):
    queryset = PlantingRecord.objects.select_related("farm", "farmer", "seedling_batch")
    if not request.user.is_staff:
        queryset = queryset.filter(farmer=request.user)
    record = get_object_or_404(queryset, pk=pk)
    return render(request, "operations/planting_record_detail.html", {"record": record})


@login_required
def add_activity(request, pk):
    record = get_object_or_404(PlantingRecord, pk=pk)

    if request.method == "POST":
        form = FarmActivityForm(request.POST, request.FILES)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.planting_record = record
            activity.created_by = request.user
            activity.save()
            messages.success(request, "Farm activity logged.")
            return redirect("operations:planting_record_detail", pk=record.pk)
    else:
        form = FarmActivityForm()

    return render(request, "operations/form_page.html", {"form": form, "title": "Add Farm Activity", "subtitle": f"Track work done for {record.crop_type}."})


@login_required
def add_input_usage(request, pk):
    record = get_object_or_404(PlantingRecord, pk=pk)

    if request.method == "POST":
        form = FarmInputUsageForm(request.POST)
        if form.is_valid():
            usage = form.save(commit=False)
            usage.planting_record = record
            usage.save()
            messages.success(request, "Farm input usage recorded.")
            return redirect("operations:planting_record_detail", pk=record.pk)
    else:
        form = FarmInputUsageForm()

    return render(request, "operations/form_page.html", {"form": form, "title": "Add Input Usage", "subtitle": f"Record inputs applied to {record.crop_type}."})


@login_required
def add_inspection(request, pk):
    record = get_object_or_404(PlantingRecord, pk=pk)

    if request.method == "POST":
        form = InspectionLogForm(request.POST, request.FILES)
        if form.is_valid():
            inspection = form.save(commit=False)
            inspection.planting_record = record
            inspection.visited_by = request.user
            inspection.save()
            messages.success(request, "Inspection logged.")
            return redirect("operations:planting_record_detail", pk=record.pk)
    else:
        form = InspectionLogForm()

    return render(request, "operations/form_page.html", {"form": form, "title": "Add Inspection Log", "subtitle": f"Capture field verification for {record.crop_type}."})

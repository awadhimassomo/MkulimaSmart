from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.views.decorators.http import require_POST

from operations.forms import PlantingRecordForm
from operations.models import InputSeller, PlantingRecord, SeedlingBatch, build_qr_image
from website.models import Category, Product

from .forms import SupplierProductForm, SupplierSeedlingBatchForm


def supplier_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_supplier or request.user.is_staff:
            return view_func(request, *args, **kwargs)

        messages.error(request, "Supplier access is required to manage marketplace listings.")
        return redirect("website:dashboard")

    return wrapped


def home(request):
    """
    Main marketplace page with categories and featured products
    """
    q          = request.GET.get("q") or request.GET.get("query") or ""
    cat_id     = request.GET.get("category") or ""
    min_price  = request.GET.get("min_price") or ""
    max_price  = request.GET.get("max_price") or ""
    region     = request.GET.get("region") or ""
    in_stock   = request.GET.get("in_stock")  # checkbox "1" if on
    page_num   = request.GET.get("page", 1)
    order      = request.GET.get("order") or "-created_at"  # e.g. -created_at, price, -price

    qs = Product.objects.select_related("category", "supplier").prefetch_related("images")

    # search
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(category__name__icontains=q)
        )

    # filters
    if cat_id:
        qs = qs.filter(category_id=cat_id)
    if min_price:
        qs = qs.filter(price__gte=min_price)
    if max_price:
        qs = qs.filter(price__lte=max_price)
    if region:
        qs = qs.filter(supplier__address__icontains=region)
    if in_stock:
        qs = qs.filter(stock__gt=0)

    # sort
    valid_orders = {"-created_at", "created_at", "price", "-price", "name", "-name"}
    if order in valid_orders:
        qs = qs.order_by(order)

    # featured products (active products, possibly with discount)
    featured_products = qs.filter(is_active=True)[:8] if qs.exists() else Product.objects.filter(is_active=True)[:8]

    # pagination
    paginator = Paginator(qs, 12)  # 12 per page
    page_obj = paginator.get_page(page_num)

    categories = Category.objects.order_by("name")
    # Simple region list (replace with your table if you have one)
    regions = ["Dar es Salaam", "Arusha", "Morogoro", "Mbeya", "Dodoma", "Mwanza", "Tanga", "Kilimanjaro"]

    context = {
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "categories": categories,
        "regions": regions,
        "featured_products": featured_products,
        "query": q,
    }
    return render(request, 'marketplace/home.html', context)


def seller_start(request):
    if request.user.is_authenticated and (request.user.is_supplier or request.user.is_staff):
        return redirect("marketplace:supplier_dashboard")

    context = {
        "is_supplier_user": request.user.is_authenticated and request.user.is_supplier,
    }
    return render(request, "marketplace/seller_start.html", context)


@login_required
@require_POST
def become_supplier(request):
    if request.user.is_supplier:
        messages.info(request, "Your account already has supplier access.")
    else:
        request.user.is_supplier = True
        request.user.save(update_fields=["is_supplier"])
        messages.success(request, "Supplier access enabled. You can now manage marketplace products and seedling batches.")
    InputSeller.get_or_create_for_user(request.user)
    return redirect("marketplace:supplier_dashboard")


@supplier_required
def supplier_dashboard(request):
    products = Product.objects.filter(supplier=request.user).select_related("category").prefetch_related("images").order_by("-created_at")
    low_stock_products = products.filter(stock__lte=5)
    seller_profile = InputSeller.get_or_create_for_user(request.user)
    seedling_batches = (
        SeedlingBatch.objects.filter(seller=seller_profile)
        .prefetch_related("planting_records")
        .order_by("-created_at")
    )
    linked_plantings = PlantingRecord.objects.filter(seedling_batch__seller=seller_profile)

    context = {
        "seller_profile": seller_profile,
        "products": products[:6],
        "product_count": products.count(),
        "active_count": products.filter(is_active=True).count(),
        "low_stock_count": low_stock_products.count(),
        "inventory_units": products.aggregate(total=Sum("stock")).get("total") or 0,
        "low_stock_products": low_stock_products[:5],
        "seedling_batches": seedling_batches[:6],
        "seedling_batch_count": seedling_batches.count(),
        "seedling_units_total": seedling_batches.aggregate(total=Sum("quantity_available")).get("total") or 0,
        "seedling_low_stock_count": seedling_batches.filter(quantity_available__lte=5).count(),
        "seedling_trace_count": linked_plantings.count(),
    }
    return render(request, "marketplace/supplier_dashboard.html", context)


@supplier_required
def supplier_seedling_batch_create(request):
    seller_profile = InputSeller.get_or_create_for_user(request.user)

    if request.method == "POST":
        form = SupplierSeedlingBatchForm(request.POST)
        if form.is_valid():
            batch = form.save(commit=False)
            batch.seller = seller_profile
            batch.save()
            messages.success(request, f"{batch.seedling_batch_id} is ready. You can now print or share its QR code.")
            return redirect("marketplace:supplier_dashboard")
    else:
        form = SupplierSeedlingBatchForm()

    context = {
        "form": form,
        "page_title": "Create Seedling Batch",
        "page_subtitle": "Register nursery stock, manage availability, and generate a QR code for traceability.",
        "submit_label": "Create Batch",
    }
    return render(request, "marketplace/seedling_batch_form.html", context)


@supplier_required
def supplier_batch_qr_print(request, pk):
    seller_profile = InputSeller.get_or_create_for_user(request.user)
    batch = get_object_or_404(SeedlingBatch.objects.select_related("seller"), pk=pk, seller=seller_profile)
    if not batch.qr_code:
        batch.ensure_qr_code()
        batch.save(update_fields=["qr_code"])
    return render(request, "marketplace/batch_qr_print.html", {"batch": batch})


def supplier_batch_qr_image(request, pk):
    batch = get_object_or_404(SeedlingBatch, pk=pk)
    if not batch.qr_code:
        batch.ensure_qr_code()
        batch.save(update_fields=["qr_code"])

    if batch.qr_code:
        response = FileResponse(batch.qr_code.open("rb"), content_type="image/png")
    else:
        qr_image = build_qr_image(batch.get_absolute_scan_url())
        response = HttpResponse(qr_image.read(), content_type="image/png")

    response["Content-Disposition"] = f'inline; filename="{batch.seedling_batch_id}.png"'
    return response


def batch_scan(request, seedling_batch_id):
    batch = get_object_or_404(SeedlingBatch, seedling_batch_id=seedling_batch_id)
    return redirect("marketplace:planting_qr_intake", seedling_batch_id=batch.seedling_batch_id)


def planting_record_qr_intake(request, seedling_batch_id):
    batch = get_object_or_404(SeedlingBatch.objects.select_related("seller"), seedling_batch_id=seedling_batch_id)
    active_user = request.user if getattr(request.user, "is_authenticated", False) else None

    if request.method == "POST":
        form = PlantingRecordForm(request.POST, request.FILES, user=active_user, seedling_batch=batch)
        if form.is_valid():
            record = form.save()
            phone_number = form.cleaned_data.get("farmer_phone") or record.farmer_phone
            messages.success(request, "Planting details submitted successfully.")
            return render(
                request,
                "marketplace/planting_record_submitted.html",
                {
                    "record": record,
                    "batch": batch,
                    "phone_number": phone_number,
                },
            )
    else:
        initial = {
            "seedling_batch": batch,
            "crop_type": batch.seedling_type,
        }
        form = PlantingRecordForm(initial=initial, user=active_user, seedling_batch=batch)

    form.fields["farmer_phone"].help_text = "Phone number is required so we can contact you later with a registration link."

    return render(
        request,
        "marketplace/planting_intake_form.html",
        {
            "form": form,
            "title": "Planting Intake Form",
            "subtitle": "This form is free for farmers and can be submitted without creating an account.",
            "batch": batch,
        },
    )


@supplier_required
def supplier_product_create(request):
    if request.method == "POST":
        form = SupplierProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(supplier=request.user)
            messages.success(request, f"{product.name} is now listed in the marketplace.")
            return redirect("marketplace:supplier_product_detail", pk=product.pk)
    else:
        form = SupplierProductForm()

    context = {
        "form": form,
        "page_title": "Create Product Listing",
        "page_subtitle": "Publish a new item and make it available to buyers.",
        "submit_label": "Publish Listing",
    }
    return render(request, "marketplace/product_form.html", context)


@supplier_required
def supplier_product_edit(request, pk):
    product = get_object_or_404(Product.objects.prefetch_related("images"), pk=pk, supplier=request.user)

    if request.method == "POST":
        form = SupplierProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            product = form.save(supplier=request.user)
            messages.success(request, f"{product.name} was updated successfully.")
            return redirect("marketplace:supplier_product_detail", pk=product.pk)
    else:
        form = SupplierProductForm(instance=product)

    context = {
        "form": form,
        "product": product,
        "page_title": "Edit Product Listing",
        "page_subtitle": "Keep your pricing, stock, and product details current.",
        "submit_label": "Save Changes",
    }
    return render(request, "marketplace/product_form.html", context)


@supplier_required
def supplier_product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category", "supplier").prefetch_related("images"),
        pk=pk,
        supplier=request.user,
    )
    return render(request, "marketplace/supplier_product_detail.html", {"product": product})

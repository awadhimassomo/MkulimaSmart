<<<<<<< HEAD
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.views.decorators.http import require_POST

from website.models import Category, Product

from .forms import SupplierProductForm


def supplier_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_supplier or request.user.is_staff:
            return view_func(request, *args, **kwargs)

        messages.error(request, "Supplier access is required to manage marketplace listings.")
        return redirect("website:dashboard")

    return wrapped


=======
from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Q
from website.models import Product, Category

# Create your views here.
>>>>>>> 
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

<<<<<<< HEAD
    qs = Product.objects.select_related("category", "supplier").prefetch_related("images")
=======
    qs = Product.objects.select_related("category").prefetch_related("images")
>>>>>>> 

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
<<<<<<< HEAD
        qs = qs.filter(supplier__address__icontains=region)
=======
        qs = qs.filter(location__icontains=region)
>>>>>>> 
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
<<<<<<< HEAD


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
        messages.success(request, "Supplier access enabled. You can now add marketplace products.")
    return redirect("marketplace:supplier_dashboard")


@supplier_required
def supplier_dashboard(request):
    products = Product.objects.filter(supplier=request.user).select_related("category").prefetch_related("images").order_by("-created_at")
    low_stock_products = products.filter(stock__lte=5)

    context = {
        "products": products[:6],
        "product_count": products.count(),
        "active_count": products.filter(is_active=True).count(),
        "low_stock_count": low_stock_products.count(),
        "inventory_units": products.aggregate(total=Sum("stock")).get("total") or 0,
        "low_stock_products": low_stock_products[:5],
    }
    return render(request, "marketplace/supplier_dashboard.html", context)


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
=======
>>>>>>> 

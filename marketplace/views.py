from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Q
from website.models import Product, Category

# Create your views here.
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

    qs = Product.objects.select_related("category").prefetch_related("images")

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
        qs = qs.filter(location__icontains=region)
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

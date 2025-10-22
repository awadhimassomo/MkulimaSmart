from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.core.paginator import Paginator

from .models import (User, Farm, Crop, Category, Product, ProductImage, Cart, CartItem, Order,
                      Warehouse, WarehouseBooking, Transport, TransportBooking, Course, Lesson, Testimonial)


def home(request):
    """
    Home page view - scrollable landing page with sections
    """
    # Temporarily commented out to avoid DB error
    # testimonials = Testimonial.objects.filter(is_active=True)[:3]
    testimonials = []  # Empty list as a temporary workaround
    
    # Try/except to handle potential missing tables for other models
    try:
        # Get featured products for different sections
        hydroponics = Product.objects.filter(is_hydroponics=True, is_active=True)[:3]
        featured_products = Product.objects.filter(is_active=True)[:4]  # For services overview
    except Exception as e:
        print(f"Error loading products: {e}")
        hydroponics = []
        featured_products = []
    
    context = {
        'testimonials': testimonials,
        'hydroponics': hydroponics,
        'featured_products': featured_products,
    }
    
    return render(request, 'website/home.html', context)


@login_required
def dashboard(request):
    """
    User dashboard view showing their farms and crops
    """
    from .weather_utils import get_weather_for_location
    import logging
    logger = logging.getLogger(__name__)
    
    farms = Farm.objects.filter(owner=request.user)
    recent_orders = Order.objects.filter(user=request.user).order_by('-created_at')[:5]
    warehouse_bookings = WarehouseBooking.objects.filter(user=request.user)[:3]
    transport_bookings = TransportBooking.objects.filter(user=request.user)[:3]
    
    # Count crops for sale
    crops_for_sale = Crop.objects.filter(farm__owner=request.user, is_available_for_sale=True).count()
    
    # Get weather for the first farm (or use default location)
    weather_data = None
    weather_location = None
    
    print(f"\n=== DASHBOARD DEBUG ===")
    print(f"User: {request.user}")
    print(f"Number of farms: {farms.count()}")
    
    if farms.exists():
        # Get weather for the first farm
        first_farm = farms.first()
        print(f"First farm: {first_farm.name}")
        print(f"Farm location: {first_farm.location}")
        weather_location = first_farm.location
        
        print(f"Fetching weather for: {weather_location}")
        weather_data = get_weather_for_location(first_farm.location)
        
        if weather_data:
            print(f"Weather data received: Temperature {weather_data.get('temperature')}°C")
        else:
            print("No weather data returned")
    else:
        print("User has no farms")
    
    print(f"=== END DEBUG ===\n")
    
    context = {
        'farms': farms,
        'recent_orders': recent_orders,
        'warehouse_bookings': warehouse_bookings,
        'transport_bookings': transport_bookings,
        'crops_for_sale': crops_for_sale,
        'weather_data': weather_data,
        'weather_location': weather_location,
    }
    return render(request, 'website/dashboard.html', context)


# Farm Management Views
@login_required
def farm_detail(request, farm_id):
    """
    View details of a specific farm
    """
    farm = get_object_or_404(Farm, id=farm_id, owner=request.user)
    crops = farm.crops.all()
    
    context = {
        'farm': farm,
        'crops': crops,
    }
    return render(request, 'website/farm_detail.html', context)


@login_required
def farm_add(request):
    """
    Add a new farm
    """
    if request.method == 'POST':
        # Process form data
        # For brevity, form processing is omitted here
        messages.success(request, _("Farm added successfully!"))
        return redirect('website:dashboard')
    
    return render(request, 'website/farm_form.html')


@login_required
def farm_edit(request, farm_id):
    """
    Edit an existing farm
    """
    farm = get_object_or_404(Farm, id=farm_id, owner=request.user)
    
    if request.method == 'POST':
        # Process form data
        # For brevity, form processing is omitted here
        messages.success(request, _("Farm updated successfully!"))
        return redirect('website:farm_detail', farm_id=farm.id)
    
    context = {
        'farm': farm,
    }
    return render(request, 'website/farm_form.html', context)


@login_required
def crop_add(request, farm_id):
    """
    Add a new crop to a farm
    """
    farm = get_object_or_404(Farm, id=farm_id, owner=request.user)
    
    if request.method == 'POST':
        # Process form data
        # For brevity, form processing is omitted here
        messages.success(request, _("Crop added successfully!"))
        return redirect('website:farm_detail', farm_id=farm.id)
    
    context = {
        'farm': farm,
    }
    return render(request, 'website/crop_form.html', context)


@login_required
def crop_edit(request, farm_id, crop_id):
    """
    Edit an existing crop
    """
    farm = get_object_or_404(Farm, id=farm_id, owner=request.user)
    crop = get_object_or_404(Crop, id=crop_id, farm=farm)
    
    if request.method == 'POST':
        # Process form data
        # For brevity, form processing is omitted here
        messages.success(request, _("Crop updated successfully!"))
        return redirect('website:farm_detail', farm_id=farm.id)
    
    context = {
        'farm': farm,
        'crop': crop,
    }
    return render(request, 'website/crop_form.html', context)


# Marketplace Views
def marketplace(request):
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
        qs = qs.filter(location__icontains=region)  # or region__iexact if you have a Region model
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
    return render(request, "website/marketplace.html", context)


def category_detail(request, slug):
    """
    Display products in a specific category
    """
    category = get_object_or_404(Category, slug=slug, is_active=True)
    products = Product.objects.filter(category=category, is_active=True)
    
    context = {
        'category': category,
        'products': products,
    }
    return render(request, 'website/category_detail.html', context)


def product_detail(request, slug):
    """
    Display details of a specific product
    """
    product = get_object_or_404(Product, slug=slug, is_active=True)
    related_products = Product.objects.filter(
        category=product.category,
        is_active=True
    ).exclude(id=product.id)[:4]
    
    context = {
        'product': product,
        'related_products': related_products,
    }
    return render(request, 'website/product_detail.html', context)


@login_required
def cart(request):
    """
    View the shopping cart
    """
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    context = {
        'cart': cart,
    }
    return render(request, 'website/cart.html', context)


@login_required
def add_to_cart(request, product_id):
    """
    Add a product to the shopping cart
    """
    product = get_object_or_404(Product, id=product_id, is_active=True)
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product
    )
    
    if not created:
        cart_item.quantity += 1
        cart_item.save()
    
    return redirect('website:cart')


@login_required
def remove_from_cart(request, item_id):
    """
    Remove an item from the shopping cart
    """
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    cart_item.delete()
    
    return redirect('website:cart')


@login_required
def checkout(request):
    """
    Checkout process for orders
    """
    cart = get_object_or_404(Cart, user=request.user)
    
    if request.method == 'POST':
        # Process order
        # For brevity, form processing is omitted here
        total_amount = cart.get_total()
        shipping_address = request.POST.get('shipping_address')
        phone_number = request.POST.get('phone_number')
        
        # Create order (simplified)
        order = Order.objects.create(
            user=request.user,
            total_amount=total_amount,
            shipping_address=shipping_address,
            phone_number=phone_number
        )
        
        # Clear cart
        cart.items.all().delete()
        
        messages.success(request, _("Order placed successfully!"))
        return redirect('website:order_detail', order_id=order.id)
    
    context = {
        'cart': cart,
    }
    return render(request, 'website/checkout.html', context)


@login_required
def order_list(request):
    """
    List all orders for the current user
    """
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'orders': orders,
    }
    return render(request, 'website/order_list.html', context)


@login_required
def order_detail(request, order_id):
    """
    View details of a specific order
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)
    
    context = {
        'order': order,
    }
    return render(request, 'website/order_detail.html', context)


# Booking Views
def booking_home(request):
    """
    Booking homepage with options for warehouse and transport booking
    """
    warehouses = Warehouse.objects.filter(is_active=True)[:4]
    transports = Transport.objects.filter(is_active=True)[:4]
    
    context = {
        'warehouses': warehouses,
        'transports': transports,
    }
    return render(request, 'website/booking_home.html', context)


def personnel_booking(request):
    """
    Personnel services booking page - farm labor, agronomists, extension officers, etc.
    """
    # Define personnel service categories
    personnel_services = [
        {
            'category': 'Farm Labor',
            'icon': '👨‍🌾',
            'description': 'Skilled farm workers for planting, weeding, and harvesting',
            'services': [
                {'name': 'Planting Services', 'price': '30,000', 'unit': 'per acre/day'},
                {'name': 'Weeding Services', 'price': '25,000', 'unit': 'per acre/day'},
                {'name': 'Harvesting Labor', 'price': '35,000', 'unit': 'per acre/day'},
                {'name': 'General Farm Labor', 'price': '20,000', 'unit': 'per person/day'},
            ]
        },
        {
            'category': 'Expert Consultation',
            'icon': '👨‍🔬',
            'description': 'Professional agricultural expertise and consultation',
            'services': [
                {'name': 'Agronomist Visit', 'price': '80,000', 'unit': 'per visit'},
                {'name': 'Soil Specialist Consultation', 'price': '70,000', 'unit': 'per visit'},
                {'name': 'Crop Disease Diagnosis', 'price': '60,000', 'unit': 'per visit'},
                {'name': 'Farm Planning Consultation', 'price': '100,000', 'unit': 'per session'},
            ]
        },
        {
            'category': 'Extension Services',
            'icon': '📋',
            'description': 'Extension officers for farm assessments and guidance',
            'services': [
                {'name': 'Extension Officer Visit', 'price': '50,000', 'unit': 'per visit'},
                {'name': 'Farm Assessment', 'price': '75,000', 'unit': 'per farm'},
                {'name': 'Certification Support', 'price': '120,000', 'unit': 'per service'},
                {'name': 'Record Keeping Training', 'price': '40,000', 'unit': 'per session'},
            ]
        },
        {
            'category': 'Training & Workshops',
            'icon': '🎓',
            'description': 'Educational sessions and hands-on training',
            'services': [
                {'name': 'Group Training Session', 'price': '150,000', 'unit': 'per session'},
                {'name': 'Demonstration Farm Tour', 'price': '30,000', 'unit': 'per person'},
                {'name': 'Workshop Facilitation', 'price': '200,000', 'unit': 'per day'},
                {'name': 'On-Farm Training', 'price': '100,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Veterinary Services',
            'icon': '🐄',
            'description': 'Animal health and livestock management',
            'services': [
                {'name': 'Veterinary Visit', 'price': '60,000', 'unit': 'per visit'},
                {'name': 'Vaccination Service', 'price': '40,000', 'unit': 'per session'},
                {'name': 'Animal Insemination', 'price': '80,000', 'unit': 'per animal'},
                {'name': 'Herd Health Assessment', 'price': '120,000', 'unit': 'per herd'},
            ]
        },
        {
            'category': 'Specialized Services',
            'icon': '⚙️',
            'description': 'Technical and specialized agricultural services',
            'services': [
                {'name': 'Irrigation System Setup', 'price': '150,000', 'unit': 'per acre'},
                {'name': 'Greenhouse Management', 'price': '90,000', 'unit': 'per month'},
                {'name': 'Post-Harvest Handling', 'price': '70,000', 'unit': 'per day'},
                {'name': 'Organic Certification Prep', 'price': '250,000', 'unit': 'per farm'},
            ]
        },
    ]
    
    context = {
        'personnel_services': personnel_services,
    }
    return render(request, 'website/personnel_booking.html', context)


def soil_booking(request):
    """
    Soil services booking page - soil testing, irrigation, fertilizer application, spraying
    """
    # Define soil service categories
    soil_services = [
        {
            'category': 'Soil Testing & Analysis',
            'icon': '🔬',
            'description': 'Professional soil testing and nutrient analysis services',
            'services': [
                {'name': 'Basic Soil Test', 'price': '50,000', 'unit': 'per sample'},
                {'name': 'Complete Nutrient Analysis', 'price': '120,000', 'unit': 'per sample'},
                {'name': 'pH Testing Service', 'price': '30,000', 'unit': 'per sample'},
                {'name': 'Soil Texture Analysis', 'price': '40,000', 'unit': 'per sample'},
            ]
        },
        {
            'category': 'Irrigation Services',
            'icon': '💧',
            'description': 'Irrigation system installation and maintenance',
            'services': [
                {'name': 'Drip Irrigation Setup', 'price': '300,000', 'unit': 'per acre'},
                {'name': 'Sprinkler System Installation', 'price': '350,000', 'unit': 'per acre'},
                {'name': 'Irrigation Repair & Maintenance', 'price': '80,000', 'unit': 'per visit'},
                {'name': 'Water Pump Installation', 'price': '150,000', 'unit': 'per unit'},
            ]
        },
        {
            'category': 'Fertilizer Application',
            'icon': '🌾',
            'description': 'Professional fertilizer application and soil amendment',
            'services': [
                {'name': 'Organic Fertilizer Application', 'price': '60,000', 'unit': 'per acre'},
                {'name': 'Chemical Fertilizer Application', 'price': '55,000', 'unit': 'per acre'},
                {'name': 'Foliar Feeding Service', 'price': '45,000', 'unit': 'per acre'},
                {'name': 'Lime Application', 'price': '50,000', 'unit': 'per acre'},
            ]
        },
        {
            'category': 'Spraying Services',
            'icon': '🚁',
            'description': 'Pesticide and herbicide application services',
            'services': [
                {'name': 'Drone Spraying', 'price': '70,000', 'unit': 'per acre'},
                {'name': 'Manual Spraying Service', 'price': '40,000', 'unit': 'per acre'},
                {'name': 'Herbicide Application', 'price': '50,000', 'unit': 'per acre'},
                {'name': 'Fungicide Application', 'price': '55,000', 'unit': 'per acre'},
            ]
        },
        {
            'category': 'Soil Preparation',
            'icon': '🚜',
            'description': 'Land preparation and soil conditioning services',
            'services': [
                {'name': 'Deep Ploughing', 'price': '80,000', 'unit': 'per acre'},
                {'name': 'Harrowing Service', 'price': '50,000', 'unit': 'per acre'},
                {'name': 'Ridging & Furrowing', 'price': '60,000', 'unit': 'per acre'},
                {'name': 'Soil Amendment Service', 'price': '70,000', 'unit': 'per acre'},
            ]
        },
        {
            'category': 'Water Management',
            'icon': '💦',
            'description': 'Water conservation and drainage solutions',
            'services': [
                {'name': 'Drainage System Installation', 'price': '200,000', 'unit': 'per acre'},
                {'name': 'Water Harvesting Setup', 'price': '250,000', 'unit': 'per system'},
                {'name': 'Mulching Service', 'price': '45,000', 'unit': 'per acre'},
                {'name': 'Moisture Conservation', 'price': '60,000', 'unit': 'per acre'},
            ]
        },
    ]
    
    context = {
        'soil_services': soil_services,
    }
    return render(request, 'website/soil_booking.html', context)


def rooms_booking(request):
    """
    Rooms and spaces booking page - warehouses, cold storage, processing facilities
    """
    # Define rooms/spaces service categories
    rooms_services = [
        {
            'category': 'Storage Facilities',
            'icon': '🏢',
            'description': 'Secure storage spaces for agricultural products',
            'services': [
                {'name': 'Standard Warehouse Space', 'price': '150,000', 'unit': 'per month'},
                {'name': 'Cold Storage Room', 'price': '300,000', 'unit': 'per month'},
                {'name': 'Grain Storage Facility', 'price': '200,000', 'unit': 'per month'},
                {'name': 'Controlled Atmosphere Storage', 'price': '400,000', 'unit': 'per month'},
            ]
        },
        {
            'category': 'Processing Facilities',
            'icon': '🏭',
            'description': 'Facilities for processing and value addition',
            'services': [
                {'name': 'Drying Facility', 'price': '100,000', 'unit': 'per day'},
                {'name': 'Milling Room', 'price': '120,000', 'unit': 'per day'},
                {'name': 'Packaging Facility', 'price': '80,000', 'unit': 'per day'},
                {'name': 'Processing Workshop', 'price': '150,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Office & Meeting Spaces',
            'icon': '🏛️',
            'description': 'Professional spaces for meetings and administration',
            'services': [
                {'name': 'Small Meeting Room', 'price': '30,000', 'unit': 'per day'},
                {'name': 'Large Conference Hall', 'price': '80,000', 'unit': 'per day'},
                {'name': 'Office Space', 'price': '120,000', 'unit': 'per month'},
                {'name': 'Training Hall', 'price': '100,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Specialized Storage',
            'icon': '❄️',
            'description': 'Temperature and humidity controlled storage',
            'services': [
                {'name': 'Refrigerated Container', 'price': '250,000', 'unit': 'per month'},
                {'name': 'Seed Storage Room', 'price': '180,000', 'unit': 'per month'},
                {'name': 'Chemical Storage Facility', 'price': '200,000', 'unit': 'per month'},
                {'name': 'Fertilizer Storage', 'price': '150,000', 'unit': 'per month'},
            ]
        },
        {
            'category': 'Livestock Facilities',
            'icon': '🐄',
            'description': 'Housing and management facilities for livestock',
            'services': [
                {'name': 'Poultry House', 'price': '200,000', 'unit': 'per month'},
                {'name': 'Dairy Parlor', 'price': '180,000', 'unit': 'per month'},
                {'name': 'Animal Quarantine Space', 'price': '150,000', 'unit': 'per week'},
                {'name': 'Feed Storage Room', 'price': '100,000', 'unit': 'per month'},
            ]
        },
    ]
    
    context = {
        'rooms_services': rooms_services,
    }
    return render(request, 'website/rooms_booking.html', context)


def equipment_booking(request):
    """
    Equipment booking page - sprayers, planters, weeders, nursery equipment
    """
    # Define equipment service categories
    equipment_services = [
        {
            'category': 'Spraying Equipment',
            'icon': '💦',
            'description': 'Professional spraying tools and equipment',
            'services': [
                {'name': 'Knapsack Sprayer', 'price': '15,000', 'unit': 'per day'},
                {'name': 'Motorized Sprayer', 'price': '35,000', 'unit': 'per day'},
                {'name': 'Boom Sprayer', 'price': '50,000', 'unit': 'per day'},
                {'name': 'Mist Blower', 'price': '40,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Planting Equipment',
            'icon': '🌱',
            'description': 'Tools for efficient planting and seeding',
            'services': [
                {'name': 'Seed Drill', 'price': '45,000', 'unit': 'per day'},
                {'name': 'Transplanter', 'price': '60,000', 'unit': 'per day'},
                {'name': 'Manual Planter', 'price': '10,000', 'unit': 'per day'},
                {'name': 'Precision Seeder', 'price': '70,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Weeding & Cultivation Tools',
            'icon': '🔧',
            'description': 'Equipment for weed control and soil cultivation',
            'services': [
                {'name': 'Power Weeder', 'price': '25,000', 'unit': 'per day'},
                {'name': 'Rotary Hoe', 'price': '30,000', 'unit': 'per day'},
                {'name': 'Inter-row Cultivator', 'price': '35,000', 'unit': 'per day'},
                {'name': 'Hand Tools Set', 'price': '8,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Harvesting Equipment',
            'icon': '🌾',
            'description': 'Tools for efficient crop harvesting',
            'services': [
                {'name': 'Reaper Machine', 'price': '50,000', 'unit': 'per day'},
                {'name': 'Grain Thresher', 'price': '60,000', 'unit': 'per day'},
                {'name': 'Maize Sheller', 'price': '25,000', 'unit': 'per day'},
                {'name': 'Harvesting Baskets/Crates', 'price': '5,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Irrigation Equipment',
            'icon': '💧',
            'description': 'Water pumps and irrigation tools',
            'services': [
                {'name': 'Water Pump (Petrol)', 'price': '40,000', 'unit': 'per day'},
                {'name': 'Water Pump (Diesel)', 'price': '50,000', 'unit': 'per day'},
                {'name': 'Hose & Fittings Set', 'price': '10,000', 'unit': 'per day'},
                {'name': 'Portable Sprinkler', 'price': '20,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Post-Harvest Equipment',
            'icon': '📦',
            'description': 'Processing and storage equipment',
            'services': [
                {'name': 'Grain Dryer', 'price': '80,000', 'unit': 'per day'},
                {'name': 'Sorting Machine', 'price': '45,000', 'unit': 'per day'},
                {'name': 'Weighing Scale (Digital)', 'price': '8,000', 'unit': 'per day'},
                {'name': 'Packaging Machine', 'price': '55,000', 'unit': 'per day'},
            ]
        },
    ]
    
    context = {
        'equipment_services': equipment_services,
    }
    return render(request, 'website/equipment_booking.html', context)


def machinery_booking(request):
    """
    Machinery booking page - tractors, harvesters, land clearing equipment
    """
    # Define machinery service categories
    machinery_services = [
        {
            'category': 'Tractors',
            'icon': '🚜',
            'description': 'Heavy-duty tractors for various farm operations',
            'services': [
                {'name': 'Small Tractor (30-50 HP)', 'price': '120,000', 'unit': 'per day'},
                {'name': 'Medium Tractor (50-80 HP)', 'price': '180,000', 'unit': 'per day'},
                {'name': 'Large Tractor (80+ HP)', 'price': '250,000', 'unit': 'per day'},
                {'name': 'Tractor with Operator', 'price': '200,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Ploughing & Tilling',
            'icon': '⚙️',
            'description': 'Land preparation machinery',
            'services': [
                {'name': 'Disc Plough Service', 'price': '80,000', 'unit': 'per acre'},
                {'name': 'Mould Board Plough', 'price': '70,000', 'unit': 'per acre'},
                {'name': 'Rotavator Service', 'price': '90,000', 'unit': 'per acre'},
                {'name': 'Subsoiler Service', 'price': '100,000', 'unit': 'per acre'},
            ]
        },
        {
            'category': 'Harvesters',
            'icon': '🌽',
            'description': 'Combine and specialized harvesters',
            'services': [
                {'name': 'Combine Harvester', 'price': '300,000', 'unit': 'per day'},
                {'name': 'Maize Harvester', 'price': '200,000', 'unit': 'per day'},
                {'name': 'Rice Harvester', 'price': '250,000', 'unit': 'per day'},
                {'name': 'Forage Harvester', 'price': '180,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Land Clearing',
            'icon': '🪓',
            'description': 'Heavy equipment for land clearing and leveling',
            'services': [
                {'name': 'Bulldozer Service', 'price': '400,000', 'unit': 'per day'},
                {'name': 'Excavator Service', 'price': '350,000', 'unit': 'per day'},
                {'name': 'Bush Cutter/Slasher', 'price': '150,000', 'unit': 'per day'},
                {'name': 'Grader/Leveler', 'price': '300,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Transport & Hauling',
            'icon': '🚛',
            'description': 'Farm transport and material hauling',
            'services': [
                {'name': 'Farm Truck Rental', 'price': '100,000', 'unit': 'per day'},
                {'name': 'Tractor Trailer Service', 'price': '80,000', 'unit': 'per day'},
                {'name': 'Pickup Truck', 'price': '70,000', 'unit': 'per day'},
                {'name': 'Cargo Van', 'price': '60,000', 'unit': 'per day'},
            ]
        },
        {
            'category': 'Specialized Machinery',
            'icon': '🤖',
            'description': 'Advanced and specialized farm machinery',
            'services': [
                {'name': 'Agricultural Drone', 'price': '150,000', 'unit': 'per day'},
                {'name': 'Laser Land Leveler', 'price': '200,000', 'unit': 'per day'},
                {'name': 'GPS-Guided Tractor', 'price': '300,000', 'unit': 'per day'},
                {'name': 'Baler Machine', 'price': '120,000', 'unit': 'per day'},
            ]
        },
    ]
    
    context = {
        'machinery_services': machinery_services,
    }
    return render(request, 'website/machinery_booking.html', context)


def warehouse_list(request):
    """
    List all available warehouses
    """
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'warehouses': warehouses,
    }
    return render(request, 'website/warehouse_list.html', context)


def warehouse_detail(request, warehouse_id):
    """
    Display details of a specific warehouse
    """
    warehouse = get_object_or_404(Warehouse, id=warehouse_id, is_active=True)
    
    context = {
        'warehouse': warehouse,
    }
    return render(request, 'website/warehouse_detail.html', context)


@login_required
def warehouse_booking(request, warehouse_id):
    """
    Book a warehouse
    """
    warehouse = get_object_or_404(Warehouse, id=warehouse_id, is_active=True)
    
    if request.method == 'POST':
        # Process form data
        # For brevity, form processing is omitted here
        messages.success(request, _("Warehouse booked successfully!"))
        return redirect('website:my_bookings')
    
    context = {
        'warehouse': warehouse,
    }
    return render(request, 'website/warehouse_booking.html', context)


def transport_list(request):
    """
    List all available transport vehicles
    """
    transports = Transport.objects.filter(is_active=True)
    
    context = {
        'transports': transports,
    }
    return render(request, 'website/transport_list.html', context)


def transport_detail(request, transport_id):
    """
    Display details of a specific transport vehicle
    """
    transport = get_object_or_404(Transport, id=transport_id, is_active=True)
    
    context = {
        'transport': transport,
    }
    return render(request, 'website/transport_detail.html', context)


@login_required
def transport_booking(request, transport_id):
    """
    Book a transport vehicle
    """
    transport = get_object_or_404(Transport, id=transport_id, is_active=True)
    
    if request.method == 'POST':
        # Process form data
        # For brevity, form processing is omitted here
        messages.success(request, _("Transport booked successfully!"))
        return redirect('website:my_bookings')
    
    context = {
        'transport': transport,
    }
    return render(request, 'website/transport_booking.html', context)


@login_required
def my_bookings(request):
    """
    View all bookings for the current user
    """
    warehouse_bookings = WarehouseBooking.objects.filter(user=request.user).order_by('-created_at')
    transport_bookings = TransportBooking.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'warehouse_bookings': warehouse_bookings,
        'transport_bookings': transport_bookings,
    }
    return render(request, 'website/my_bookings.html', context)


# Training Views
def training_home(request):
    """
    Training homepage with course categories
    """
    courses = Course.objects.all()
    
    # Group courses by category
    crop_courses = courses.filter(category='crop')
    livestock_courses = courses.filter(category='livestock')
    hydroponics_courses = courses.filter(category='hydroponics')
    agribusiness_courses = courses.filter(category='agribusiness')
    
    context = {
        'crop_courses': crop_courses,
        'livestock_courses': livestock_courses,
        'hydroponics_courses': hydroponics_courses,
        'agribusiness_courses': agribusiness_courses,
    }
    return render(request, 'website/training_home.html', context)


def course_detail(request, slug):
    """
    Display details of a specific course
    """
    course = get_object_or_404(Course, slug=slug)
    lessons = course.lessons.all().order_by('position')
    
    context = {
        'course': course,
        'lessons': lessons,
    }
    return render(request, 'website/course_detail.html', context)


@login_required
def lesson_detail(request, lesson_id):
    """
    View a specific lesson
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course = lesson.course
    
    # Check if user has access to this lesson
    if not course.is_free and course not in request.user.enrolled_courses.all():
        messages.error(request, _("You must enroll in this course to access this lesson."))
        return redirect('website:course_detail', slug=course.slug)
    
    # Get next and previous lessons
    next_lesson = Lesson.objects.filter(course=course, position__gt=lesson.position).order_by('position').first()
    prev_lesson = Lesson.objects.filter(course=course, position__lt=lesson.position).order_by('-position').first()
    
    context = {
        'lesson': lesson,
        'course': course,
        'next_lesson': next_lesson,
        'prev_lesson': prev_lesson,
    }
    return render(request, 'website/lesson_detail.html', context)


@login_required
def my_courses(request):
    """
    View all courses the user is enrolled in
    """
    # This assumes there's an enrollment model - simplified for brevity
    enrolled_courses = Course.objects.filter(enrolled_users=request.user)
    
    context = {
        'enrolled_courses': enrolled_courses,
    }
    return render(request, 'website/my_courses.html', context)


# About Page
def about(request):
    """
    About page with company information
    """
    return render(request, 'website/about.html')

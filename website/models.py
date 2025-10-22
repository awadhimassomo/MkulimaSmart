from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, FileExtensionValidator
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    """
    Custom user manager that uses phone number as the unique identifier
    instead of username
    """
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('The Phone Number must be set')
        
        # Normalize the phone number by removing spaces and dashes
        phone_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')
        
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
            
        return self.create_user(phone_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model that uses phone number as the primary identifier
    """
    phone_number = models.CharField(_("Phone Number"), max_length=15, unique=True)
    email = models.EmailField(_("Email Address"), blank=True)
    first_name = models.CharField(_("First Name"), max_length=30, blank=True)
    last_name = models.CharField(_("Last Name"), max_length=150, blank=True)
    is_farmer = models.BooleanField(_("Is Farmer"), default=False)
    is_supplier = models.BooleanField(_("Is Supplier"), default=False)
    is_trainer = models.BooleanField(_("Is Trainer"), default=False)
    address = models.CharField(_("Address"), max_length=255, blank=True, null=True)
    profile_picture = models.ImageField(_("Profile Picture"), upload_to='profile_pics/', blank=True, null=True)
    date_joined = models.DateTimeField(_("Date Joined"), default=timezone.now)
    is_active = models.BooleanField(_("Active"), default=True)
    is_staff = models.BooleanField(_("Staff Status"), default=False)
    
    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []  # No additional required fields for creating a superuser
    
    objects = CustomUserManager()
    
    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
    
    def __str__(self):
        return self.phone_number
        
    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.phone_number
        
    def get_short_name(self):
        return self.first_name or self.phone_number


class Farm(models.Model):
    """
    Farm model representing agricultural land owned/managed by a user
    """
    name = models.CharField(_("Farm Name"), max_length=100)
    location = models.CharField(_("Location"), max_length=200)
    size = models.DecimalField(_("Size (hectares)"), max_digits=10, decimal_places=2)
    soil_type = models.CharField(_("Soil Type"), max_length=100, blank=True, null=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="farms")
    description = models.TextField(_("Description"), blank=True, null=True)
    is_hydroponic = models.BooleanField(_("Is Hydroponic"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Farm")
        verbose_name_plural = _("Farms")
    
    def __str__(self):
        return self.name


class Crop(models.Model):
    """
    Crop model representing a type of crop planted in a farm
    """
    name = models.CharField(_("Crop Name"), max_length=100)
    description = models.TextField(_("Description"), blank=True, null=True)
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="website_crops")
    planting_date = models.DateField(_("Planting Date"))
    expected_harvest_date = models.DateField(_("Expected Harvest Date"), blank=True, null=True)
    quantity = models.DecimalField(_("Quantity (kg)"), max_digits=10, decimal_places=2, default=0)
    is_available_for_sale = models.BooleanField(_("Available for Sale"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Crop")
        verbose_name_plural = _("Crops")
    
    def __str__(self):
        return f"{self.name} at {self.farm.name}"


# Marketplace Models
class Category(models.Model):
    """
    Categories for marketplace products (Tools, Seeds, Fertilizers, etc.)
    """
    name = models.CharField(_("Category Name"), max_length=100)
    slug = models.SlugField(_("Slug"), unique=True)
    description = models.TextField(_("Description"), blank=True, null=True)
    image = models.ImageField(_("Image"), upload_to='category_images/', blank=True, null=True)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('website:category_detail', kwargs={'slug': self.slug})


class Product(models.Model):
    """
    Products in the marketplace (tools, seeds, fertilizers, etc.)
    """
    name = models.CharField(_("Product Name"), max_length=200)
    slug = models.SlugField(_("Slug"), unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    description = models.TextField(_("Description"))
    price = models.DecimalField(_("Price"), max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(_("Discount Price"), max_digits=10, decimal_places=2, blank=True, null=True)
    stock = models.PositiveIntegerField(_("Stock"), default=0)
    is_hydroponics = models.BooleanField(_("Is Hydroponics"), default=False)
    requires_quote = models.BooleanField(_("Requires Quote"), default=False)
    is_active = models.BooleanField(_("Is Active"), default=True)
    supplier = models.ForeignKey(User, on_delete=models.CASCADE, related_name="products")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('website:product_detail', kwargs={'slug': self.slug})


class ProductImage(models.Model):
    """
    Images for products
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(_("Image"), upload_to='product_images/')
    is_primary = models.BooleanField(_("Is Primary"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _("Product Image")
        verbose_name_plural = _("Product Images")
    
    def __str__(self):
        return f"Image for {self.product.name}"


class Cart(models.Model):
    """
    Shopping cart for marketplace
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="carts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Cart")
        verbose_name_plural = _("Carts")
    
    def __str__(self):
        return f"Cart for {self.user.phone_number}"
        
    def get_total(self):
        return sum(item.get_total_price() for item in self.items.all())


class CartItem(models.Model):
    """
    Items in a shopping cart
    """
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(_("Quantity"), default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _("Cart Item")
        verbose_name_plural = _("Cart Items")
    
    def __str__(self):
        return f"{self.quantity} x {self.product.name}"
    
    def get_total_price(self):
        price = self.product.discount_price if self.product.discount_price else self.product.price
        return price * self.quantity


class Order(models.Model):
    """
    Orders from the marketplace
    """
    STATUS_CHOICES = [
        ('pending', _("Pending")),
        ('processing', _("Processing")),
        ('shipped', _("Shipped")),
        ('delivered', _("Delivered")),
        ('cancelled', _("Cancelled")),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(_("Total Amount"), max_digits=10, decimal_places=2)
    shipping_address = models.TextField(_("Shipping Address"))
    phone_number = models.CharField(_("Phone Number"), max_length=15)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
    
    def __str__(self):
        return f"Order #{self.id} - {self.user.phone_number}"


# Booking Models
class Warehouse(models.Model):
    """
    Warehouses for booking storage
    """
    name = models.CharField(_("Warehouse Name"), max_length=200)
    location = models.CharField(_("Location"), max_length=200)
    capacity = models.DecimalField(_("Capacity (cubic meters)"), max_digits=10, decimal_places=2)
    available_capacity = models.DecimalField(_("Available Capacity (cubic meters)"), max_digits=10, decimal_places=2)
    price_per_cubic_meter = models.DecimalField(_("Price per Cubic Meter"), max_digits=10, decimal_places=2)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="warehouses")
    description = models.TextField(_("Description"), blank=True, null=True)
    image = models.ImageField(_("Image"), upload_to='warehouse_images/', blank=True, null=True)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Warehouse")
        verbose_name_plural = _("Warehouses")
    
    def __str__(self):
        return self.name


class WarehouseBooking(models.Model):
    """
    Bookings for warehouse storage
    """
    STATUS_CHOICES = [
        ('pending', _("Pending")),
        ('confirmed', _("Confirmed")),
        ('cancelled', _("Cancelled")),
        ('completed', _("Completed")),
    ]
    
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="bookings")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="warehouse_bookings")
    start_date = models.DateField(_("Start Date"))
    end_date = models.DateField(_("End Date"))
    cubic_meters = models.DecimalField(_("Cubic Meters"), max_digits=10, decimal_places=2)
    total_price = models.DecimalField(_("Total Price"), max_digits=10, decimal_places=2)
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(_("Notes"), blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Warehouse Booking")
        verbose_name_plural = _("Warehouse Bookings")
    
    def __str__(self):
        return f"{self.warehouse.name} - {self.user.phone_number} - {self.start_date}"


class Transport(models.Model):
    """
    Vehicles for transport booking
    """
    TYPE_CHOICES = [
        ('truck', _("Truck")),
        ('van', _("Van")),
        ('pickup', _("Pickup")),
        ('tractor', _("Tractor")),
    ]
    
    name = models.CharField(_("Vehicle Name"), max_length=200)
    type = models.CharField(_("Vehicle Type"), max_length=20, choices=TYPE_CHOICES)
    capacity = models.DecimalField(_("Capacity (tons)"), max_digits=10, decimal_places=2)
    price_per_km = models.DecimalField(_("Price per KM"), max_digits=10, decimal_places=2)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transports")
    description = models.TextField(_("Description"), blank=True, null=True)
    image = models.ImageField(_("Image"), upload_to='transport_images/', blank=True, null=True)
    license_plate = models.CharField(_("License Plate"), max_length=20)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Transport")
        verbose_name_plural = _("Transports")
    
    def __str__(self):
        return f"{self.name} ({self.license_plate})"


class TransportBooking(models.Model):
    """
    Bookings for transport
    """
    STATUS_CHOICES = [
        ('pending', _("Pending")),
        ('confirmed', _("Confirmed")),
        ('cancelled', _("Cancelled")),
        ('completed', _("Completed")),
    ]
    
    transport = models.ForeignKey(Transport, on_delete=models.CASCADE, related_name="bookings")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transport_bookings")
    pickup_location = models.CharField(_("Pickup Location"), max_length=200)
    dropoff_location = models.CharField(_("Dropoff Location"), max_length=200)
    distance = models.DecimalField(_("Distance (km)"), max_digits=10, decimal_places=2)
    date = models.DateField(_("Date"))
    time = models.TimeField(_("Time"))
    total_price = models.DecimalField(_("Total Price"), max_digits=10, decimal_places=2)
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='pending')
    load_description = models.TextField(_("Load Description"))
    share_load = models.BooleanField(_("Share Load"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Transport Booking")
        verbose_name_plural = _("Transport Bookings")
    
    def __str__(self):
        return f"{self.transport.name} - {self.user.phone_number} - {self.date}"


# Training Models
class Course(models.Model):
    """
    Training courses for farmers
    """
    CATEGORY_CHOICES = [
        ('crop', _("Crop Management")),
        ('livestock', _("Livestock")),
        ('hydroponics', _("Hydroponics")),
        ('agribusiness', _("Agribusiness")),
    ]
    
    title = models.CharField(_("Title"), max_length=200)
    slug = models.SlugField(_("Slug"), unique=True)
    category = models.CharField(_("Category"), max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField(_("Description"))
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courses")
    thumbnail = models.ImageField(_("Thumbnail"), upload_to='course_thumbnails/')
    is_free = models.BooleanField(_("Is Free"), default=False)
    price = models.DecimalField(_("Price"), max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Course")
        verbose_name_plural = _("Courses")
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('website:course_detail', kwargs={'slug': self.slug})


class Lesson(models.Model):
    """
    Lessons within courses
    """
    title = models.CharField(_("Title"), max_length=200)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    video = models.FileField(_("Video"), upload_to='lesson_videos/', validators=[FileExtensionValidator(allowed_extensions=['mp4', 'webm', 'avi'])])
    description = models.TextField(_("Description"))
    duration = models.PositiveIntegerField(_("Duration (minutes)"))
    is_preview = models.BooleanField(_("Is Preview"), default=False)
    position = models.PositiveIntegerField(_("Position"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Lesson")
        verbose_name_plural = _("Lessons")
        ordering = ['position']
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"


# Testimonial Model
class Testimonial(models.Model):
    """
    Testimonials from farmers
    """
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="testimonials")
    content = models.TextField(_("Testimonial Content"))
    image = models.ImageField(_("Image"), upload_to='testimonial_images/', blank=True, null=True)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Testimonial")
        verbose_name_plural = _("Testimonials")
    
    def __str__(self):
        return f"Testimonial by {self.farmer.get_full_name() or self.farmer.phone_number}"


# Weather Data Model
class WeatherData(models.Model):
    """
    Weather data for farms
    """
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="weather_data")
    date = models.DateField(_("Date"))
    temperature = models.DecimalField(_("Temperature (\u00b0C)"), max_digits=5, decimal_places=2)
    humidity = models.DecimalField(_("Humidity (%)"), max_digits=5, decimal_places=2)
    rainfall = models.DecimalField(_("Rainfall (mm)"), max_digits=6, decimal_places=2, default=0)
    wind_speed = models.DecimalField(_("Wind Speed (km/h)"), max_digits=5, decimal_places=2, default=0)
    pressure = models.DecimalField(_("Pressure (hPa)"), max_digits=6, decimal_places=2, default=1013.25)
    source = models.CharField(_("Data Source"), max_length=50, default="manual")
    notes = models.TextField(_("Notes"), blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _("Weather Data")
        verbose_name_plural = _("Weather Data")
        ordering = ['-date']
    
    def __str__(self):
        return f"Weather data for {self.farm.name} on {self.date}"


# Rain Forecast Model
class RainForecast(models.Model):
    """
    Rain forecast data for farms
    """
    ACCURACY_CHOICES = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
    ]
    
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="rain_forecasts")
    forecast_date = models.DateField(_("Forecast Date"))
    probability = models.DecimalField(_("Rain Probability (%)"), max_digits=5, decimal_places=2)
    expected_rainfall = models.DecimalField(_("Expected Rainfall (mm)"), max_digits=6, decimal_places=2)
    accuracy = models.CharField(_("Forecast Accuracy"), max_length=10, choices=ACCURACY_CHOICES, default='medium')
    source = models.CharField(_("Forecast Source"), max_length=100, default="AI Prediction")
    notes = models.TextField(_("Notes"), blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Rain Forecast")
        verbose_name_plural = _("Rain Forecasts")
        ordering = ['forecast_date']
    
    def __str__(self):
        return f"Rain forecast for {self.farm.name} on {self.forecast_date}"

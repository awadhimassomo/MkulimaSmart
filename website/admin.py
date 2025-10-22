from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import (User, Farm, Crop, Category, Product, ProductImage, Cart, CartItem, Order,
                     Warehouse, WarehouseBooking, Transport, TransportBooking, Course, Lesson, Testimonial,
                     WeatherData, RainForecast)


class CustomUserAdmin(admin.ModelAdmin):
    """
    Custom admin interface for the User model
    """
    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
        (_('Additional Information'), {'fields': ('is_farmer', 'is_supplier', 'is_trainer', 'address', 'profile_picture')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'password1', 'password2', 'email'),
        }),
    )
    list_display = ('phone_number', 'email', 'first_name', 'last_name', 'is_farmer', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'is_farmer')
    search_fields = ('phone_number', 'first_name', 'last_name', 'email')
    ordering = ('phone_number',)


class FarmAdmin(admin.ModelAdmin):
    """
    Admin interface for the Farm model
    """
    list_display = ('name', 'location', 'size', 'soil_type', 'owner', 'created_at')
    list_filter = ('soil_type', 'created_at')
    search_fields = ('name', 'location', 'owner__phone_number')


class CropAdmin(admin.ModelAdmin):
    """
    Admin interface for the Crop model
    """
    list_display = ('name', 'farm', 'planting_date', 'expected_harvest_date')
    list_filter = ('planting_date', 'expected_harvest_date')
    search_fields = ('name', 'farm__name')


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active')
    prepopulated_fields = {'slug': ('name',)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'is_active', 'supplier')
    list_filter = ('category', 'is_active', 'is_hydroponics', 'requires_quote')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductImageInline]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 1


class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at')
    inlines = [CartItemInline]


class OrderAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'total_amount', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__phone_number', 'shipping_address')


class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'capacity', 'available_capacity', 'price_per_cubic_meter', 'owner')
    list_filter = ('is_active',)
    search_fields = ('name', 'location')


class WarehouseBookingAdmin(admin.ModelAdmin):
    list_display = ('warehouse', 'user', 'start_date', 'end_date', 'status')
    list_filter = ('status',)
    search_fields = ('warehouse__name', 'user__phone_number')


class TransportAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'license_plate', 'capacity', 'owner')
    list_filter = ('type', 'is_active')
    search_fields = ('name', 'license_plate')


class TransportBookingAdmin(admin.ModelAdmin):
    list_display = ('transport', 'user', 'date', 'pickup_location', 'dropoff_location', 'status')
    list_filter = ('status', 'share_load')
    search_fields = ('transport__name', 'user__phone_number')


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1


class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'instructor', 'is_free')
    list_filter = ('category', 'is_free')
    search_fields = ('title', 'description')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [LessonInline]


class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'duration', 'is_preview', 'position')
    list_filter = ('is_preview', 'course')
    search_fields = ('title', 'description')


class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('farmer', 'is_active', 'created_at')
    list_filter = ('is_active',)


class WeatherDataAdmin(admin.ModelAdmin):
    list_display = ('farm', 'date', 'temperature', 'humidity', 'rainfall', 'wind_speed', 'source')
    list_filter = ('date', 'source', 'farm')
    search_fields = ('farm__name', 'notes')
    date_hierarchy = 'date'


class RainForecastAdmin(admin.ModelAdmin):
    list_display = ('farm', 'forecast_date', 'probability', 'expected_rainfall', 'accuracy', 'source')
    list_filter = ('forecast_date', 'accuracy', 'source', 'farm')
    search_fields = ('farm__name', 'notes')
    date_hierarchy = 'forecast_date'


# Register models with the admin site
admin.site.register(User, CustomUserAdmin)
admin.site.register(Farm, FarmAdmin)
admin.site.register(Crop, CropAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(Cart, CartAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(Warehouse, WarehouseAdmin)
admin.site.register(WarehouseBooking, WarehouseBookingAdmin)
admin.site.register(Transport, TransportAdmin)
admin.site.register(TransportBooking, TransportBookingAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(Lesson, LessonAdmin)
admin.site.register(Testimonial, TestimonialAdmin)
admin.site.register(WeatherData, WeatherDataAdmin)
admin.site.register(RainForecast, RainForecastAdmin)

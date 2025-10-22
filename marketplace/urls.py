from django.urls import path
from . import views

app_name = 'marketplace'

urlpatterns = [
    # Marketplace home page
    path('', views.home, name='home'),
    # Add other marketplace URLs here as needed
]

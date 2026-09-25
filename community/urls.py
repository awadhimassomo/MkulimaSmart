from django.urls import path

from . import views

app_name = "community"

urlpatterns = [
    path("", views.discussion_list, name="discussion_list"),
    path("new/", views.discussion_create, name="discussion_create"),
    path("<int:pk>/", views.discussion_detail, name="discussion_detail"),
    path("<int:pk>/report/", views.discussion_report, name="discussion_report"),
]

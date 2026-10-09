from django.urls import path

from . import views

app_name = "callcenter"

urlpatterns = [
    path("", views.console, name="console"),
    path("state/", views.state, name="state"),
    path("availability/", views.availability, name="availability"),
    path("case/<int:pk>/", views.case_detail, name="case"),
    path("case/<int:pk>/messages/", views.case_messages, name="case_messages"),
    path("case/<int:pk>/accept/", views.case_accept, name="case_accept"),
    path("case/<int:pk>/reply/", views.case_reply, name="case_reply"),
    path("case/<int:pk>/release/", views.case_release, name="case_release"),
    path("case/<int:pk>/close/", views.case_close, name="case_close"),
    path("case/<int:pk>/ai/", views.case_ai, name="case_ai"),
    path("join/<str:token>/", views.join, name="join"),
    path("team/", views.team, name="team"),
    path("team/invite/", views.team_invite, name="team_invite"),
    path("team/invite/<int:pk>/revoke/", views.team_revoke, name="team_revoke"),
    path("team/agronomist/<int:pk>/toggle/", views.team_toggle, name="team_toggle"),
]

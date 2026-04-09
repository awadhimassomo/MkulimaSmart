from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'ecop'

urlpatterns = [
    # Group management
    path('create_group/', views.CreateGroupView.as_view(), name='create_group'),
    path('nearby_groups/', views.NearbyGroupsView.as_view(), name='nearby_groups'),
    
    # Group membership
    path('join_request/', views.JoinGroupRequestView.as_view(), name='join_request'),
    path('pending_join_requests/', views.PendingJoinRequestsView.as_view(), 
         name='pending_join_requests'),
    path('respond_join_request/', views.RespondJoinRequestView.as_view(), 
         name='respond_join_request'),
    path('group_members/', views.GroupMembersView.as_view(), name='group_members'),
    
    # Commitments
    path('lock_commitment/', views.LockCommitmentView.as_view(), name='lock_commitment'),
    path('commitments/', views.CommitmentsView.as_view(), name='commitments'),
    
    # Analytics
    path('aggregation_data/', views.AggregationDataView.as_view(), name='aggregation_data'),
    
    # Authentication
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

from rest_framework import permissions

class IsLeadFarmer(permissions.BasePermission):
    """
    Custom permission to only allow lead farmers to access the view.
    A user is considered a lead farmer if they have the is_lead_farmer flag set to True.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        return getattr(user, 'is_lead_farmer', False) or user.founded_groups.filter(is_active=True).exists()

class IsGroupFounder(permissions.BasePermission):
    """
    Custom permission to only allow the founder of a group to access the view.
    """
    def has_object_permission(self, request, view, obj):
        # Check if the user is the founder of the group
        return obj.founder == request.user

class IsGroupMember(permissions.BasePermission):
    """
    Custom permission to only allow members of a group to access the view.
    """
    def has_object_permission(self, request, view, obj):
        # Check if the user is a member of the group
        return obj.members.filter(user=request.user, is_active=True).exists()

class IsCommitmentOwner(permissions.BasePermission):
    """
    Custom permission to only allow the owner of a commitment to access it.
    """
    def has_object_permission(self, request, view, obj):
        # Check if the user is the founder of the group that owns the commitment
        return obj.group.founder == request.user

class IsFarmerCommitmentOwner(permissions.BasePermission):
    """
    Custom permission to only allow the farmer who made a commitment to access it.
    """
    def has_object_permission(self, request, view, obj):
        # Check if the user is the farmer who made the commitment
        return obj.farmer == request.user

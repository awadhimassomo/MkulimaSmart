from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import EcopGroup, EcopGroupMember, EcopJoinRequest
from .notifications import NotificationService

User = get_user_model()

@receiver(post_save, sender=EcopGroup)
def set_user_as_lead_farmer(sender, instance, created, **kwargs):
    """
    Signal to automatically set a user as a lead farmer when they create a group.
    """
    if created:
        user = instance.founder
        if not user.is_lead_farmer:
            user.is_lead_farmer = True
            user.save(update_fields=['is_lead_farmer'])

@receiver(post_save, sender=EcopJoinRequest)
def notify_join_request_created(sender, instance, created, **kwargs):
    """
    Signal to send notification when a new join request is created.
    """
    if created:
        # Import here to avoid circular imports
        from django.core.handlers.wsgi import WSGIRequest
        
        # Create a mock request object if not available in the signal
        request = getattr(instance, '_request', None)
        if request is None:
            request = WSGIRequest({
                'REQUEST_METHOD': 'POST',
                'wsgi.input': None,
            })
            request.user = instance.farmer
            
        # Send notification
        NotificationService.send_join_request_notification(instance, request)

@receiver(post_save, sender=EcopJoinRequest)
def handle_join_request_response(sender, instance, **kwargs):
    """
    Signal to handle join request responses and send notifications.
    """
    if instance.status != 'pending' and not getattr(instance, '_notified', False):
        # Import here to avoid circular imports
        from django.core.handlers.wsgi import WSGIRequest
        
        # Create a mock request object if not available in the signal
        request = getattr(instance, '_request', None)
        if request is None:
            request = WSGIRequest({
                'REQUEST_METHOD': 'POST',
                'wsgi.input': None,
            })
            request.user = instance.group.founder
        
        # Send notification
        NotificationService.send_join_request_response(instance, request)
        
        # Mark as notified to prevent duplicate notifications
        instance._notified = True
        # Save without triggering the signal again
        EcopJoinRequest.objects.filter(pk=instance.pk).update(_notified=True)

@receiver(post_save, sender=EcopGroupMember)
def notify_group_member_added(sender, instance, created, **kwargs):
    """
    Signal to send notification when a user is added to a group.
    """
    if created:
        # This could be used to send a welcome message to the new member
        pass

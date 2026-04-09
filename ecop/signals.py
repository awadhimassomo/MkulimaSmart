from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
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
        NotificationService.send_join_request_notification(instance, getattr(instance, '_request', None))

@receiver(post_save, sender=EcopJoinRequest)
def handle_join_request_response(sender, instance, **kwargs):
    """
    Signal to handle join request responses and send notifications.
    """
    if instance.status != 'pending' and not getattr(instance, '_notified', False):
        NotificationService.send_join_request_response(instance, getattr(instance, '_request', None))

@receiver(post_save, sender=EcopGroupMember)
def notify_group_member_added(sender, instance, created, **kwargs):
    """
    Signal to send notification when a user is added to a group.
    """
    if created:
        # This could be used to send a welcome message to the new member
        pass

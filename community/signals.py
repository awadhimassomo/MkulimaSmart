from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Discussion, Reply


@receiver(post_save, sender=Reply)
def _increment_reply_count(sender, instance, created, **kwargs):
    if created:
        Discussion.objects.filter(pk=instance.discussion_id).update(reply_count=F("reply_count") + 1)


@receiver(post_delete, sender=Reply)
def _decrement_reply_count(sender, instance, **kwargs):
    Discussion.objects.filter(pk=instance.discussion_id, reply_count__gt=0).update(reply_count=F("reply_count") - 1)

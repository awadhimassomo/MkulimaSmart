from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.core.exceptions import ValidationError

User = get_user_model()

class EcopGroup(models.Model):
    """
    Represents a farmer cooperative group in the Ecop system.
    """
    id = models.AutoField(primary_key=True)
    group_name = models.CharField(max_length=255, unique=True, 
                                help_text="Name of the cooperative group")
    primary_crop = models.CharField(max_length=100, 
                                  help_text="Primary crop for this group")
    location = models.CharField(max_length=255, 
                              help_text="Geographic location of the group")
    founder = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, 
        related_name='founded_groups',
        help_text="User who created this group (becomes Lead Farmer)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, 
                                  help_text="Whether the group is currently active")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Ecop Group'
        verbose_name_plural = 'Ecop Groups'
    
    def __str__(self):
        return f"{self.group_name} - {self.primary_crop} ({self.location})"
    
    @property
    def member_count(self):
        """Returns the number of active members in the group."""
        return self.members.filter(is_active=True).count()
    
    @property
    def founder_name(self):
        """Returns the full name of the group founder."""
        return f"{self.founder.first_name} {self.founder.last_name}"
    
    def clean(self):
        # Ensure group name is unique (case-insensitive)
        if EcopGroup.objects.filter(
            group_name__iexact=self.group_name
        ).exclude(pk=self.pk).exists():
            raise ValidationError({
                'group_name': 'A group with this name already exists in the system.'
            })


class EcopGroupMember(models.Model):
    """
    Represents the membership of a user in an Ecop group.
    """
    group = models.ForeignKey(
        EcopGroup, 
        on_delete=models.CASCADE, 
        related_name='members',
        help_text="The group this membership belongs to"
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='ecop_memberships',
        help_text="The user who is a member of the group"
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, 
                                  help_text="Whether the membership is active")
    
    class Meta:
        unique_together = ('group', 'user')
        ordering = ['-joined_at']
        verbose_name = 'Ecop Group Member'
        verbose_name_plural = 'Ecop Group Members'
    
    def __str__(self):
        return f"{self.user.get_full_name()} in {self.group.group_name}"


class EcopJoinRequest(models.Model):
    """
    Represents a request from a farmer to join an Ecop group.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    id = models.AutoField(primary_key=True)
    group = models.ForeignKey(
        EcopGroup, 
        on_delete=models.CASCADE, 
        related_name='join_requests',
        help_text="The group being requested to join"
    )
    farmer = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='ecop_join_requests',
        help_text="The farmer requesting to join the group"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        help_text="Current status of the join request"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    response_note = models.TextField(null=True, blank=True,
                                   help_text="Optional note from the group founder")
    
    class Meta:
        unique_together = ('group', 'farmer')
        ordering = ['-created_at']
        verbose_name = 'Ecop Join Request'
        verbose_name_plural = 'Ecop Join Requests'
    
    def __str__(self):
        return f"{self.farmer.get_full_name()} -> {self.group.group_name} ({self.status})"
    
    def save(self, *args, **kwargs):
        # Update responded_at when status changes from pending
        if self.pk:
            old_instance = EcopJoinRequest.objects.get(pk=self.pk)
            if old_instance.status == 'pending' and self.status != 'pending':
                self.responded_at = timezone.now()
        super().save(*args, **kwargs)
        
        # If approved, add user to group
        if self.status == 'approved':
            EcopGroupMember.objects.get_or_create(
                group=self.group,
                user=self.farmer,
                defaults={'is_active': True}
            )


class EcopCommitment(models.Model):
    """
    Represents a commitment made by a group to supply a certain crop.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('locked', 'Locked'),
        ('matched', 'Matched'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.AutoField(primary_key=True)
    group = models.ForeignKey(
        EcopGroup, 
        on_delete=models.CASCADE, 
        related_name='commitments',
        help_text="The group making this commitment"
    )
    crop = models.CharField(max_length=100, 
                          help_text="Type of crop being committed")
    total_volume = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Total volume in kg"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        help_text="Current status of the commitment"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    matched_at = models.DateTimeField(null=True, blank=True)
    
    # Buyer information (when matched)
    buyer = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='ecop_purchases',
        help_text="Buyer who matched with this commitment"
    )
    agreed_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Agreed price per kg"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Ecop Commitment'
        verbose_name_plural = 'Ecop Commitments'
    
    def __str__(self):
        return f"{self.group.group_name} - {self.total_volume}kg {self.crop} ({self.status})"
    
    @property
    def farmer_count(self):
        """Returns the number of farmers in this commitment."""
        return self.farmer_commitments.count()
    
    @property
    def group_name(self):
        """Returns the name of the group."""
        return self.group.group_name
    
    def lock(self):
        """Locks the commitment and sets the locked timestamp."""
        if self.status == 'pending':
            self.status = 'locked'
            self.locked_at = timezone.now()
            self.save(update_fields=['status', 'locked_at'])
            return True
        return False
    
    def match(self, buyer, price_per_kg):
        """Matches the commitment with a buyer."""
        if self.status == 'locked':
            self.status = 'matched'
            self.buyer = buyer
            self.agreed_price = price_per_kg
            self.matched_at = timezone.now()
            self.save(update_fields=[
                'status', 'buyer', 'agreed_price', 'matched_at'
            ])
            return True
        return False


class EcopFarmerCommitment(models.Model):
    """
    Represents an individual farmer's commitment within a group commitment.
    """
    commitment = models.ForeignKey(
        EcopCommitment, 
        on_delete=models.CASCADE, 
        related_name='farmer_commitments',
        help_text="The parent group commitment"
    )
    farmer = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='my_ecop_commitments',
        help_text="The farmer making this commitment"
    )
    volume = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Volume in kg committed by this farmer"
    )
    is_paid = models.BooleanField(
        default=False,
        help_text="Whether the farmer has been paid"
    )
    paid_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the payment was processed"
    )
    
    class Meta:
        unique_together = ('commitment', 'farmer')
        verbose_name = 'Ecop Farmer Commitment'
        verbose_name_plural = 'Ecop Farmer Commitments'
    
    def __str__(self):
        return f"{self.farmer.get_full_name()} - {self.volume}kg"
    
    @property
    def farmer_name(self):
        """Returns the full name of the farmer."""
        return f"{self.farmer.first_name} {self.farmer.last_name}"
    
    @property
    def phone_number(self):
        """Returns the phone number of the farmer."""
        return self.farmer.phone_number
    
    def mark_as_paid(self):
        """Marks this commitment as paid."""
        if not self.is_paid:
            self.is_paid = True
            self.paid_at = timezone.now()
            self.save(update_fields=['is_paid', 'paid_at'])
            
            # If all farmer commitments are paid, mark parent as fulfilled
            if not self.commitment.farmer_commitments.filter(is_paid=False).exists():
                self.commitment.status = 'fulfilled'
                self.commitment.save(update_fields=['status'])
            return True
        return False


# Add a signal to update user's is_lead_farmer status when they create a group
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=EcopGroup)
def update_lead_farmer_status(sender, instance, created, **kwargs):
    """
    Updates the founder's is_lead_farmer status when they create a new group.
    """
    if created and not instance.founder.is_lead_farmer:
        instance.founder.is_lead_farmer = True
        instance.founder.save(update_fields=['is_lead_farmer'])

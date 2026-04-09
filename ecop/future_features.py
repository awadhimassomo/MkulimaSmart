"""
Phase 3 - Future Features for Ecop Module

This module contains the implementation of future features for the Ecop module,
including buyer matching, payment processing, and additional SMS notifications.
"""

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q, F, Sum
from django.conf import settings

from .models import (
    EcopCommitment, EcopFarmerCommitment, 
    EcopGroup, EcopGroupMember
)
from .notifications import NotificationService

class BuyerMatchingService:
    """
    Service for handling buyer matching for farmer commitments.
    """
    
    @classmethod
    def find_matching_buyers(cls, commitment):
        """
        Find potential buyers for a given commitment.
        
        Args:
            commitment (EcopCommitment): The commitment to find buyers for
            
        Returns:
            QuerySet: Matching buyers or purchase orders
        """
        # This is a placeholder implementation
        # In a real system, this would query a buyers/marketplace database
        # and return matching buyers based on crop type, quantity, price, etc.
        
        # For now, return an empty queryset
        return []
    
    @classmethod
    def match_commitment_to_buyer(cls, commitment_id, buyer_id):
        """
        Match a commitment to a specific buyer.
        
        Args:
            commitment_id (int): ID of the commitment to match
            buyer_id (int): ID of the buyer to match with
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            with transaction.atomic():
                commitment = EcopCommitment.objects.select_for_update().get(
                    id=commitment_id,
                    status=EcopCommitment.ACTIVE
                )
                
                # In a real implementation, we would validate the buyer here
                # and create a purchase order or similar
                
                # Update commitment status to MATCHED
                commitment.status = EcopCommitment.MATCHED
                commitment.matched_at = timezone.now()
                commitment.save()
                
                # Send SMS notifications to farmers
                farmer_commitments = commitment.farmer_commitments.filter(
                    status=EcopFarmerCommitment.PENDING
                )
                
                for fc in farmer_commitments:
                    NotificationService.send_match_confirmation(fc)
                
                return True, "Successfully matched commitment with buyer"
                
        except EcopCommitment.DoesNotExist:
            return False, "Commitment not found or not eligible for matching"
        except Exception as e:
            return False, f"Error matching commitment: {str(e)}"


class PaymentProcessingService:
    """
    Service for handling payment processing for farmer commitments.
    """
    
    @classmethod
    def process_payment(cls, commitment_id, payment_data):
        """
        Process payment for a matched commitment.
        
        Args:
            commitment_id (int): ID of the commitment to process payment for
            payment_data (dict): Payment information
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            with transaction.atomic():
                commitment = EcopCommitment.objects.select_for_update().get(
                    id=commitment_id,
                    status=EcopCommitment.MATCHED
                )
                
                # In a real implementation, we would integrate with a payment gateway here
                # and process the payment using the payment_data
                
                # Update commitment status to PAID
                commitment.status = EcopCommitment.PAID
                commitment.paid_at = timezone.now()
                commitment.payment_reference = payment_data.get('reference')
                commitment.save()
                
                # Update farmer commitments and process payments to farmers
                farmer_commitments = commitment.farmer_commitments.filter(
                    status=EcopFarmerCommitment.CONFIRMED
                )
                
                for fc in farmer_commitments:
                    # Calculate payment amount based on volume and price
                    payment_amount = float(fc.volume) * float(commitment.agreed_price)
                    
                    # Update farmer commitment status
                    fc.status = EcopFarmerCommitment.PAID
                    fc.payment_amount = payment_amount
                    fc.payment_reference = f"{commitment.payment_reference}-{fc.id}"
                    fc.paid_at = timezone.now()
                    fc.save()
                    
                    # Send payment confirmation SMS
                    NotificationService.send_payment_confirmation(fc)
                
                return True, "Payment processed successfully"
                
        except EcopCommitment.DoesNotExist:
            return False, "Commitment not found or not eligible for payment"
        except Exception as e:
            return False, f"Error processing payment: {str(e)}"


class CommitmentWorkflowService:
    """
    Service for managing the commitment workflow, including status transitions
    and related operations.
    """
    
    @classmethod
    def confirm_farmer_commitment(cls, farmer_commitment_id):
        """
        Confirm a farmer's commitment to supply their produce.
        
        Args:
            farmer_commitment_id (int): ID of the farmer commitment to confirm
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            with transaction.atomic():
                fc = EcopFarmerCommitment.objects.select_for_update().get(
                    id=farmer_commitment_id,
                    status=EcopFarmerCommitment.PENDING
                )
                
                # Update status to confirmed
                fc.status = EcopFarmerCommitment.CONFIRMED
                fc.confirmed_at = timezone.now()
                fc.save()
                
                # Check if all farmers have confirmed
                commitment = fc.commitment
                unconfirmed = commitment.farmer_commitments.filter(
                    status=EcopFarmerCommitment.PENDING
                ).exists()
                
                if not unconfirmed:
                    # All farmers have confirmed, update commitment status
                    commitment.status = EcopCommitment.CONFIRMED
                    commitment.save()
                
                return True, "Commitment confirmed successfully"
                
        except EcopFarmerCommitment.DoesNotExist:
            return False, "Farmer commitment not found or already confirmed"
        except Exception as e:
            return False, f"Error confirming commitment: {str(e)}"
    
    @classmethod
    def cancel_commitment(cls, commitment_id, reason=None):
        """
        Cancel a commitment and all associated farmer commitments.
        
        Args:
            commitment_id (int): ID of the commitment to cancel
            reason (str, optional): Reason for cancellation
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            with transaction.atomic():
                commitment = EcopCommitment.objects.select_for_update().get(
                    id=commitment_id,
                    status__in=[
                        EcopCommitment.ACTIVE, 
                        EcopCommitment.CONFIRMED,
                        EcopCommitment.MATCHED
                    ]
                )
                
                # Update commitment status
                commitment.status = EcopCommitment.CANCELLED
                commitment.cancelled_at = timezone.now()
                commitment.cancellation_reason = reason
                commitment.save()
                
                # Cancel all farmer commitments
                commitment.farmer_commitments.filter(
                    status__in=[
                        EcopFarmerCommitment.PENDING,
                        EcopFarmerCommitment.CONFIRMED
                    ]
                ).update(
                    status=EcopFarmerCommitment.CANCELLED,
                    cancelled_at=timezone.now(),
                    cancellation_reason=reason
                )
                
                # TODO: Send notifications to all affected farmers
                
                return True, "Commitment cancelled successfully"
                
        except EcopCommitment.DoesNotExist:
            return False, "Commitment not found or not eligible for cancellation"
        except Exception as e:
            return False, f"Error cancelling commitment: {str(e)}"

import logging

from django.utils import timezone

from .models import EcopJoinRequest

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service class for handling all Ecop module notifications.
    """

    @staticmethod
    def send_sms(phone_number, message):
        """
        Send an SMS to the specified phone number.
        This is a placeholder that should be integrated with an SMS gateway.
        """

        try:
            logger.info(f"[SMS] To: {phone_number}, Message: {message}")
            return True
        except Exception as e:
            logger.error(f"Failed to send SMS to {phone_number}: {str(e)}")
            return False

    @classmethod
    def send_commitment_confirmation(cls, farmer_commitment):
        """
        Send SMS 1: Commitment Confirmation to a farmer.
        """

        try:
            farmer = farmer_commitment.farmer
            group = farmer_commitment.commitment.group

            message = (
                f"Habari {farmer.first_name}!\n"
                f"Umeweka ahadi ya {farmer_commitment.volume} kg za {farmer_commitment.commitment.crop} "
                f"kwa kundi la {group.group_name}. "
                f"Tutakujulisha soko litakapopatikana.\n"
                f"- Kikapu Mkulima Smart"
            )

            return cls.send_sms(farmer.phone_number, message)
        except Exception as e:
            logger.error(f"Failed to send commitment confirmation: {str(e)}")
            return False

    @classmethod
    def send_match_confirmation(cls, farmer_commitment):
        """
        Send SMS 2: Match Confirmation to a farmer.
        """

        try:
            farmer = farmer_commitment.farmer
            commitment = farmer_commitment.commitment
            total_amount = float(commitment.agreed_price) * float(farmer_commitment.volume)

            message = (
                f"Hongera {farmer.first_name}!\n"
                f"Soko limepatikana! Mnunuzi atalipa TZS {commitment.agreed_price}/kg kwa "
                f"{commitment.crop} yako.\n"
                f"Kiasi: {farmer_commitment.volume} kg. Jumla: TZS {total_amount:,.2f}.\n"
                f"- Kikapu Mkulima Smart"
            )

            return cls.send_sms(farmer.phone_number, message)
        except Exception as e:
            logger.error(f"Failed to send match confirmation: {str(e)}")
            return False

    @classmethod
    def send_payment_confirmation(cls, farmer_commitment):
        """
        Send SMS 3: Payment Confirmation to a farmer.
        """

        try:
            farmer = farmer_commitment.farmer
            commitment = farmer_commitment.commitment
            amount = float(commitment.agreed_price) * float(farmer_commitment.volume)

            message = (
                f"Malipo yamekamilika!\n"
                f"Umepokea TZS {amount:,.2f} kwa {farmer_commitment.volume} kg "
                f"za {commitment.crop}.\n"
                f"Asante kwa kushirikiana!\n"
                f"- Kikapu Mkulima Smart"
            )

            return cls.send_sms(farmer.phone_number, message)
        except Exception as e:
            logger.error(f"Failed to send payment confirmation: {str(e)}")
            return False

    @classmethod
    def send_join_request_notification(cls, join_request, request):
        """
        Send an in-app notification to the group founder about a new join request.
        """

        try:
            farmer = join_request.farmer
            notification = {
                "type": "new_join_request",
                "message": f"{farmer.get_full_name()} ameomba kujiunga na kikundi chako cha {join_request.group.group_name}.",
                "farmer_id": farmer.id,
                "farmer_name": farmer.get_full_name(),
                "group_id": join_request.group.id,
                "group_name": join_request.group.group_name,
                "request_id": join_request.id,
                "timestamp": timezone.now(),
                "is_read": False,
            }

            logger.info(f"[NOTIFICATION] {notification['message']}")
            return True
        except Exception as e:
            logger.error(f"Failed to send join request notification: {str(e)}")
            return False

    @classmethod
    def send_join_request_response(cls, join_request, request):
        """
        Send an in-app notification to the farmer about their join request response.
        """

        try:
            group = join_request.group
            status_display = dict(EcopJoinRequest.STATUS_CHOICES).get(join_request.status, join_request.status)

            notification = {
                "type": "join_request_response",
                "message": f"Ombi lako la kujiunga na kikundi cha {group.group_name} limesitishwa kama '{status_display}'.",
                "group_id": group.id,
                "group_name": group.group_name,
                "status": join_request.status,
                "status_display": status_display,
                "response_note": join_request.response_note,
                "timestamp": timezone.now(),
                "is_read": False,
            }

            logger.info(f"[NOTIFICATION] {notification['message']}")
            return True
        except Exception as e:
            logger.error(f"Failed to send join request response notification: {str(e)}")
            return False

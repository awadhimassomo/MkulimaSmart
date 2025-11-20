from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db.models import Q, Sum, Count
from django.utils import timezone

from .notifications import NotificationService
from .models import (
    EcopGroup, EcopGroupMember, EcopJoinRequest, 
    EcopCommitment, EcopFarmerCommitment
)
from .serializers import (
    EcopGroupSerializer, EcopGroupMemberSerializer, 
    EcopJoinRequestSerializer, EcopCommitmentSerializer,
    EcopFarmerCommitmentSerializer, CreateGroupSerializer,
    JoinGroupRequestSerializer, RespondJoinRequestSerializer,
    LockCommitmentSerializer, UserSerializer
)
from .permissions import (
    IsLeadFarmer, IsGroupFounder, IsGroupMember, 
    IsCommitmentOwner, IsFarmerCommitmentOwner
)
from django.contrib.auth import get_user_model

User = get_user_model()

class CreateGroupView(APIView):
    """
    API endpoint to create a new Ecop group.
    Any authenticated user can create a group and become a lead farmer.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = CreateGroupSerializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                # Create the group
                group = EcopGroup.objects.create(
                    group_name=serializer.validated_data['group_name'],
                    primary_crop=serializer.validated_data['primary_crop'],
                    location=serializer.validated_data['location'],
                    founder=request.user
                )
                # Add founder as first member
                EcopGroupMember.objects.create(
                    group=group,
                    user=request.user,
                    is_active=True
                )
                
                # The founder is automatically set as lead farmer via the signal
                
                # Return the created group
                group_serializer = EcopGroupSerializer(group)
                return Response({
                    'status': 'success',
                    'message': 'Group created successfully',
                    'group': group_serializer.data,
                    'user_updated': True
                }, status=status.HTTP_201_CREATED)
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

class NearbyGroupsView(APIView):
    """
    API endpoint to get nearby Ecop groups.
    Any authenticated user can view nearby groups.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        location = request.query_params.get('location', '').strip()
        
        # Get groups the user is already a member of
        user_groups = EcopGroupMember.objects.filter(
            user=request.user,
            is_active=True
        ).values_list('group_id', flat=True)
        
        # Filter groups by location and exclude groups user is already in
        groups = EcopGroup.objects.filter(is_active=True)
        
        if location:
            groups = groups.filter(location__icontains=location)
        
        if user_groups:
            groups = groups.exclude(id__in=user_groups)
        
        # Order by newest first
        groups = groups.order_by('-created_at')
        
        serializer = EcopGroupSerializer(groups, many=True)
        return Response({
            'status': 'success',
            'groups': serializer.data
        })

class JoinGroupRequestView(APIView):
    """
    API endpoint to send a join request to a group.
    Any authenticated user can request to join a group.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = JoinGroupRequestSerializer(data=request.data)
        if serializer.is_valid():
            group_id = serializer.validated_data['group_id']
            group = get_object_or_404(EcopGroup, id=group_id, is_active=True)
            
            # Check if user is already a member
            if EcopGroupMember.objects.filter(
                group=group, 
                user=request.user
            ).exists():
                return Response({
                    'status': 'error',
                    'message': 'You are already a member of this group.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if there's already a pending request
            existing_request = EcopJoinRequest.objects.filter(
                group=group,
                farmer=request.user,
                status='pending'
            ).first()
            
            if existing_request:
                return Response({
                    'status': 'error',
                    'message': 'You have already sent a request to this group.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create the join request
            join_request = EcopJoinRequest.objects.create(
                group=group,
                farmer=request.user,
                status='pending'
            )
            
            # Send notification to the group founder about the join request
            NotificationService.send_join_request_notification(join_request, self.request)
            
            return Response({
                'status': 'success',
                'message': 'Join request sent successfully',
                'request_id': join_request.id
            }, status=status.HTTP_201_CREATED)
            
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

class PendingJoinRequestsView(APIView):
    """
    API endpoint to get pending join requests for groups where the user is the founder.
    Only lead farmers can view join requests for their groups.
    """
    permission_classes = [IsAuthenticated, IsLeadFarmer]
    
    def get(self, request):
        # Get groups where user is the founder
        groups = EcopGroup.objects.filter(founder=request.user, is_active=True)
        
        # Get pending join requests for these groups
        requests = EcopJoinRequest.objects.filter(
            group__in=groups,
            status='pending'
        ).select_related('group', 'farmer').order_by('created_at')
        
        serializer = EcopJoinRequestSerializer(requests, many=True)
        return Response({
            'status': 'success',
            'requests': serializer.data
        })

class RespondJoinRequestView(APIView):
    """
    API endpoint to approve or reject a join request.
    Only the group founder can respond to join requests.
    """
    permission_classes = [IsAuthenticated, IsLeadFarmer]
    
    def post(self, request):
        serializer = RespondJoinRequestSerializer(data=request.data)
        if serializer.is_valid():
            join_request = serializer.validated_data['request_id']
            approve = serializer.validated_data['approve']
            note = serializer.validated_data.get('note', '')
            
            # Verify the request belongs to a group where user is the founder
            if join_request.group.founder != request.user:
                return Response({
                    'status': 'error',
                    'message': 'You are not authorized to respond to this request.'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Update the join request in a transaction
            with transaction.atomic():
                join_request.status = 'approved' if approve else 'rejected'
                join_request.response_note = note
                join_request.responded_at = timezone.now()
                join_request.save()
                
                # If approved, add the user to the group
                if join_request.status == EcopJoinRequest.APPROVED:
                    EcopGroupMember.objects.create(
                        group=join_request.group,
                        user=join_request.farmer,
                        is_active=True,
                        joined_at=timezone.now()
                    )
                
                # Send notification to the farmer about the response
                NotificationService.send_join_request_response(join_request, self.request)
            
            return Response({
                'success': True,
                'message': f'Join request {join_request.get_status_display().lower()}' + 
                          (' and member added to group' if approve else '')
            })
            
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

class GroupMembersView(APIView):
    """
    API endpoint to get members of groups where the user is the founder.
    Only the group founder can view the member list.
    """
    permission_classes = [IsAuthenticated, IsLeadFarmer]
    
    def get(self, request):
        # Get groups where user is the founder
        groups = EcopGroup.objects.filter(founder=request.user, is_active=True)
        
        # Get active members of these groups
        members = EcopGroupMember.objects.filter(
            group__in=groups,
            is_active=True
        ).select_related('user').order_by('joined_at')
        
        # Format the response
        members_data = [{
            'id': member.user.id,
            'first_name': member.user.first_name,
            'last_name': member.user.last_name,
            'name': f"{member.user.first_name} {member.user.last_name}",
            'phone_number': member.user.phone_number,
            'joined_at': member.joined_at
        } for member in members]
        
        return Response({
            'status': 'success',
            'members': members_data
        })

class LockCommitmentView(APIView):
    """
    API endpoint to lock a commitment and notify farmers.
    Only the group founder can lock a commitment.
    """
    permission_classes = [IsAuthenticated, IsLeadFarmer]
    
    def post(self, request):
        serializer = LockCommitmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Get the group (must be founded by the current user)
            group = get_object_or_404(
                EcopGroup, 
                founder=request.user, 
                is_active=True
            )
            
            # Create the commitment
            commitment = EcopCommitment.objects.create(
                group=group,
                crop=serializer.validated_data['crop'],
                total_volume=0,  # Will be updated when farmers commit
                target_price=serializer.validated_data['target_price'],
                status=EcopCommitment.ACTIVE,
                created_by=request.user,
                created_at=timezone.now()
            )
            
            # Create farmer commitments
            total_volume = 0
            farmer_commitments = []
            
            for farmer_data in serializer.validated_data['farmer_commitments']:
                farmer = farmer_data['farmer']
                volume = farmer_data['volume']
                
                farmer_commitment = EcopFarmerCommitment(
                    commitment=commitment,
                    farmer=farmer,
                    volume=volume,
                    status=EcopFarmerCommitment.PENDING,
                    committed_at=timezone.now()
                )
                farmer_commitments.append(farmer_commitment)
                total_volume += volume
            
            # Bulk create farmer commitments
            EcopFarmerCommitment.objects.bulk_create(farmer_commitments)
            
            # Update total volume
            commitment.total_volume = total_volume
            commitment.save()
            
            # Send SMS notifications to farmers
            for farmer_commitment in farmer_commitments:
                NotificationService.send_commitment_confirmation(farmer_commitment)
            
            # Get the serialized commitment data
            commitment_serializer = EcopCommitmentSerializer(commitment)
            
            return Response({
                'success': True,
                'message': 'Commitment locked successfully. SMS sent to all farmers.',
                'commitment': commitment_serializer.data,
                'commitment_id': commitment.id
            }, status=status.HTTP_201_CREATED)

class CommitmentsView(APIView):
    """
    API endpoint to get commitments for groups where the user is the founder.
    Only the group founder can view commitments.
    """
    permission_classes = [IsAuthenticated, IsLeadFarmer]
    
    def get(self, request):
        status_filter = request.query_params.get('status')
        
        # Get groups where user is the founder
        groups = EcopGroup.objects.filter(founder=request.user, is_active=True)
        
        # Get commitments for these groups
        commitments = EcopCommitment.objects.filter(
            group__in=groups
        ).select_related('group', 'buyer').prefetch_related('farmer_commitments__farmer')
        
        # Apply status filter if provided
        if status_filter and status_filter in dict(EcopCommitment.STATUS_CHOICES):
            commitments = commitments.filter(status=status_filter)
        
        # Order by creation date (newest first)
        commitments = commitments.order_by('-created_at')
        
        serializer = EcopCommitmentSerializer(commitments, many=True)
        return Response({
            'status': 'success',
            'commitments': serializer.data
        })

class AggregationDataView(APIView):
    """
    API endpoint to get platform-wide and group-specific statistics.
    Any authenticated user can view platform-wide stats.
    Group-specific stats are only visible to the group founder.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        response_data = {
            'status': 'success',
            'platform_success_rate': self._calculate_platform_success_rate(),
            'total_volume_sold': self._calculate_total_volume_sold(),
            'total_farmers_paid': self._calculate_total_farmers_paid(),
            'avg_payment': self._calculate_avg_payment(),
        }
        
        # Add group-specific stats if user is a lead farmer
        if hasattr(request.user, 'is_lead_farmer') and request.user.is_lead_farmer:
            response_data.update({
                'group_success_rate': self._calculate_group_success_rate(request.user),
                'group_total_volume': self._calculate_group_total_volume(request.user),
                'group_commitments_count': self._calculate_group_commitments_count(request.user),
            })
        
        return Response(response_data)
    
    def _calculate_platform_success_rate(self):
        # Calculate success rate as percentage of fulfilled commitments
        total = EcopCommitment.objects.count()
        if total == 0:
            return 0.0
        fulfilled = EcopCommitment.objects.filter(status='fulfilled').count()
        return round((fulfilled / total) * 100, 2)
    
    def _calculate_total_volume_sold(self):
        # Calculate total volume of fulfilled commitments
        result = EcopCommitment.objects.filter(
            status='fulfilled'
        ).aggregate(total=Sum('total_volume'))
        return float(result['total'] or 0)
    
    def _calculate_total_farmers_paid(self):
        # Count unique farmers with at least one paid commitment
        return EcopFarmerCommitment.objects.filter(
            is_paid=True
        ).values('farmer').distinct().count()
    
    def _calculate_avg_payment(self):
        # Calculate average payment per farmer (simplified)
        paid_commitments = EcopFarmerCommitment.objects.filter(is_paid=True)
        if not paid_commitments.exists():
            return 0
        
        total_payment = sum(
            commitment.volume * commitment.commitment.agreed_price
            for commitment in paid_commitments.select_related('commitment')
            if commitment.commitment.agreed_price is not None
        )
        
        return round(total_payment / paid_commitments.count(), 2)
    
    def _calculate_group_success_rate(self, user):
        # Calculate success rate for groups where user is founder
        groups = EcopGroup.objects.filter(founder=user, is_active=True)
        total = EcopCommitment.objects.filter(group__in=groups).count()
        if total == 0:
            return 0.0
        fulfilled = EcopCommitment.objects.filter(
            group__in=groups,
            status='fulfilled'
        ).count()
        return round((fulfilled / total) * 100, 2)
    
    def _calculate_group_total_volume(self, user):
        # Calculate total volume for groups where user is founder
        groups = EcopGroup.objects.filter(founder=user, is_active=True)
        result = EcopCommitment.objects.filter(
            group__in=groups
        ).aggregate(total=Sum('total_volume'))
        return float(result['total'] or 0)
    
    def _calculate_group_commitments_count(self, user):
        # Count commitments for groups where user is founder
        groups = EcopGroup.objects.filter(founder=user, is_active=True)
        return EcopCommitment.objects.filter(group__in=groups).count()

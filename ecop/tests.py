from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone

from .models import (
    EcopGroup, EcopGroupMember, EcopJoinRequest, 
    EcopCommitment, EcopFarmerCommitment
)
from .serializers import (
    EcopGroupSerializer, EcopGroupMemberSerializer, 
    EcopJoinRequestSerializer, EcopCommitmentSerializer,
    EcopFarmerCommitmentSerializer
)

User = get_user_model()

class EcopBaseTestCase(APITestCase):
    """Base test case with common setup for Ecop module tests."""
    
    def setUp(self):
        # Create test users
        self.user1 = User.objects.create_user(
            email='test1@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User1',
            phone_number='+255700000001',
            is_lead_farmer=True
        )
        
        self.user2 = User.objects.create_user(
            email='test2@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User2',
            phone_number='+255700000002'
        )
        
        # Create a test group
        self.group = EcopGroup.objects.create(
            group_name='Test Farmers Group',
            primary_crop='Maize',
            location='Arusha, Tanzania',
            founder=self.user1
        )
        
        # Add user1 as a member of the group
        EcopGroupMember.objects.create(
            group=self.group,
            user=self.user1,
            is_active=True,
            joined_at=timezone.now()
        )
        
        # Get JWT tokens for authentication
        self.user1_token = str(RefreshToken.for_user(self.user1).access_token)
        self.user2_token = str(RefreshToken.for_user(self.user2).access_token)
        
        # Set up API client with authentication
        self.client = APIClient()


class EcopGroupTests(EcopBaseTestCase):
    """Tests for Ecop group related endpoints."""
    
    def test_create_group_authenticated(self):
        """Test creating a new group as an authenticated user."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user2_token}')
        
        data = {
            'group_name': 'New Farmers Group',
            'primary_crop': 'Beans',
            'location': 'Dodoma, Tanzania'
        }
        
        response = self.client.post(
            reverse('ecop:create_group'),
            data=data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EcopGroup.objects.count(), 2)  # Original + new group
        self.assertTrue(EcopGroupMember.objects.filter(
            group__group_name='New Farmers Group',
            user=self.user2
        ).exists())
        
        # Verify user is now a lead farmer
        self.user2.refresh_from_db()
        self.assertTrue(self.user2.is_lead_farmer)
    
    def test_get_nearby_groups(self):
        """Test retrieving nearby groups."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user2_token}')
        
        response = self.client.get(reverse('ecop:nearby_groups'))
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['group_name'], 'Test Farmers Group')


class JoinRequestTests(EcopBaseTestCase):
    """Tests for group join request related endpoints."""
    
    def test_send_join_request(self):
        """Test sending a join request to a group."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user2_token}')
        
        data = {
            'group_id': self.group.id,
            'message': 'I would like to join your group.'
        }
        
        response = self.client.post(
            reverse('ecop:join_request'),
            data=data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EcopJoinRequest.objects.filter(
            group=self.group,
            farmer=self.user2,
            status='pending'
        ).exists())
    
    def test_respond_to_join_request(self):
        """Test responding to a join request as a group founder."""
        # Create a join request
        join_request = EcopJoinRequest.objects.create(
            group=self.group,
            farmer=self.user2,
            status='pending',
            requested_at=timezone.now()
        )
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user1_token}')
        
        data = {
            'request_id': join_request.id,
            'status': 'approved',
            'response_note': 'Welcome to the group!'
        }
        
        response = self.client.post(
            reverse('ecop:respond_join_request'),
            data=data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify the join request was updated
        join_request.refresh_from_db()
        self.assertEqual(join_request.status, 'approved')
        
        # Verify the user was added to the group
        self.assertTrue(EcopGroupMember.objects.filter(
            group=self.group,
            user=self.user2,
            is_active=True
        ).exists())


class CommitmentTests(EcopBaseTestCase):
    """Tests for commitment related endpoints."""
    
    def test_create_commitment(self):
        """Test creating a new commitment as a group founder."""
        # Add user2 to the group first
        EcopGroupMember.objects.create(
            group=self.group,
            user=self.user2,
            is_active=True,
            joined_at=timezone.now()
        )
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user1_token}')
        
        data = {
            'group_id': self.group.id,
            'crop': 'Maize',
            'target_price': 1500.00,
            'farmer_commitments': [
                {
                    'farmer_id': self.user1.id,
                    'volume': 100.0
                },
                {
                    'farmer_id': self.user2.id,
                    'volume': 150.0
                }
            ]
        }
        
        response = self.client.post(
            reverse('ecop:lock_commitment'),
            data=data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EcopCommitment.objects.count(), 1)
        self.assertEqual(EcopFarmerCommitment.objects.count(), 2)
        
        # Verify total volume was calculated correctly
        commitment = EcopCommitment.objects.first()
        self.assertEqual(commitment.total_volume, 250.0)  # 100 + 150
    
    def test_get_commitments(self):
        """Test retrieving commitments for a group."""
        # Create a test commitment
        commitment = EcopCommitment.objects.create(
            group=self.group,
            crop='Maize',
            total_volume=100.0,
            target_price=1500.00,
            status='active',
            created_by=self.user1
        )
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user1_token}')
        
        response = self.client.get(
            reverse('ecop:commitments'),
            {'group_id': self.group.id}
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], commitment.id)


class AggregationDataTests(EcopBaseTestCase):
    """Tests for aggregation data endpoint."""
    
    def test_get_aggregation_data(self):
        """Test retrieving platform-wide aggregation data."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user1_token}')
        
        response = self.client.get(reverse('ecop:aggregation_data'))
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('platform_stats', response.data)
        self.assertIn('group_stats', response.data)
        
        # Verify platform stats structure
        platform_stats = response.data['platform_stats']
        self.assertIn('total_groups', platform_stats)
        self.assertIn('total_farmers', platform_stats)
        self.assertIn('total_volume_committed', platform_stats)
        
        # Verify group stats structure
        group_stats = response.data['group_stats']
        self.assertEqual(len(group_stats), 1)  # Only one group in test data
        self.assertEqual(group_stats[0]['group_name'], self.group.group_name)

# Ecop (E-Cooperative) Module

This module handles the E-Cooperative functionality for the Mkulima Smart platform, enabling farmers to form groups, create supply commitments, and connect with buyers.

## Features

- **Group Management**: Create and manage farmer groups
- **Membership**: Handle join requests and group membership
- **Commitments**: Create and manage supply commitments
- **Buyer Matching**: Match farmer groups with potential buyers
- **Payment Processing**: Handle payments for fulfilled commitments
- **Notifications**: SMS and in-app notifications for important events

## API Endpoints

### Group Management

#### Create a New Group
- **URL**: `/api/ecop/create_group/`
- **Method**: `POST`
- **Authentication**: JWT required
- **Request Body**:
  ```json
  {
    "group_name": "Farmers United",
    "primary_crop": "Maize",
    "location": "Arusha, Tanzania"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "message": "Group created successfully",
    "group_id": 1
  }
  ```

#### Get Nearby Groups
- **URL**: `/api/ecop/nearby_groups/`
- **Method**: `GET`
- **Authentication**: JWT required
- **Query Parameters**:
  - `latitude` (optional)
  - `longitude` (optional)
  - `radius_km` (optional, default: 10)
- **Response**:
  ```json
  [
    {
      "id": 1,
      "group_name": "Farmers United",
      "primary_crop": "Maize",
      "location": "Arusha, Tanzania",
      "member_count": 15,
      "distance_km": 2.5
    }
  ]
  ```

### Membership

#### Send Join Request
- **URL**: `/api/ecop/join_request/`
- **Method**: `POST`
- **Authentication**: JWT required
- **Request Body**:
  ```json
  {
    "group_id": 1,
    "message": "I would like to join your group."
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "message": "Join request sent successfully",
    "request_id": 1
  }
  ```

#### Respond to Join Request
- **URL**: `/api/ecop/respond_join_request/`
- **Method**: `POST`
- **Authentication**: JWT required (group founder only)
- **Request Body**:
  ```json
  {
    "request_id": 1,
    "status": "approved",
    "response_note": "Welcome to the group!"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "message": "Join request approved and member added to group"
  }
  ```

### Commitments

#### Lock Commitment
- **URL**: `/api/ecop/lock_commitment/`
- **Method**: `POST`
- **Authentication**: JWT required (group founder only)
- **Request Body**:
  ```json
  {
    "group_id": 1,
    "crop": "Maize",
    "target_price": 1500.00,
    "farmer_commitments": [
      {
        "farmer_id": 2,
        "volume": 100.0
      },
      {
        "farmer_id": 3,
        "volume": 150.0
      }
    ]
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "message": "Commitment locked successfully. SMS sent to all farmers.",
    "commitment_id": 1,
    "commitment": {
      "id": 1,
      "group": 1,
      "crop": "Maize",
      "total_volume": 250.0,
      "target_price": "1500.00",
      "status": "active",
      "created_at": "2025-11-14T10:00:00Z"
    }
  }
  ```

#### Get Commitments
- **URL**: `/api/ecop/commitments/`
- **Method**: `GET`
- **Authentication**: JWT required
- **Query Parameters**:
  - `group_id` (optional)
  - `status` (optional): active, confirmed, matched, paid, cancelled
- **Response**:
  ```json
  [
    {
      "id": 1,
      "group": 1,
      "crop": "Maize",
      "total_volume": 250.0,
      "target_price": "1500.00",
      "status": "active",
      "created_at": "2025-11-14T10:00:00Z"
    }
  ]
  ```

### Analytics

#### Get Aggregation Data
- **URL**: `/api/ecop/aggregation_data/`
- **Method**: `GET`
- **Authentication**: JWT required
- **Response**:
  ```json
  {
    "platform_stats": {
      "total_groups": 10,
      "total_farmers": 150,
      "total_volume_committed": 12500.5,
      "total_transactions": 45,
      "total_payments": 18750750.0
    },
    "group_stats": [
      {
        "group_id": 1,
        "group_name": "Farmers United",
        "total_volume": 2500.0,
        "total_transactions": 12,
        "success_rate": 85.5
      }
    ]
  }
  ```

## Models

### EcopGroup
- `group_name`: Name of the group (unique)
- `primary_crop`: Primary crop for the group
- `location`: Group's location
- `founder`: Reference to the user who created the group
- `created_at`: Timestamp of group creation
- `is_active`: Whether the group is active

### EcopGroupMember
- `group`: Reference to the group
- `user`: Reference to the user
- `is_active`: Whether the membership is active
- `joined_at`: Timestamp of joining
- `left_at`: Timestamp of leaving (if applicable)

### EcopJoinRequest
- `group`: Reference to the group
- `farmer`: Reference to the user requesting to join
- `status`: Request status (pending, approved, rejected)
- `message`: Message from the farmer
- `response_note`: Response from the group founder
- `requested_at`: Timestamp of the request
- `responded_at`: Timestamp of the response

### EcopCommitment
- `group`: Reference to the group
- `crop`: Type of crop
- `total_volume`: Total volume committed (kg)
- `target_price`: Target price per unit
- `agreed_price`: Agreed price with buyer (if matched)
- `status`: Commitment status (active, confirmed, matched, paid, cancelled)
- `created_by`: User who created the commitment
- `created_at`: Timestamp of creation
- `matched_at`: Timestamp of buyer matching
- `paid_at`: Timestamp of payment
- `cancelled_at`: Timestamp of cancellation
- `cancellation_reason`: Reason for cancellation

### EcopFarmerCommitment
- `commitment`: Reference to the group commitment
- `farmer`: Reference to the farmer
- `volume`: Volume committed by the farmer (kg)
- `status`: Farmer's commitment status
- `payment_amount`: Amount to be paid to the farmer
- `payment_reference`: Payment reference
- `committed_at`: Timestamp of commitment
- `confirmed_at`: Timestamp of confirmation
- `paid_at`: Timestamp of payment
- `cancelled_at`: Timestamp of cancellation

## Setup

1. Add 'ecop' to your INSTALLED_APPS in settings.py:
   ```python
   INSTALLED_APPS = [
       # ...
       'ecop',
   ]
   ```

2. Run migrations:
   ```bash
   python manage.py makemigrations ecop
   python manage.py migrate
   ```

3. Configure SMS settings in settings.py:
   ```python
   # Example using Africa's Talking
   AFRICAS_TALKING_API_KEY = 'your_api_key'
   AFRICAS_TALKING_USERNAME = 'your_username'
   ```

## Testing

Run the test suite:
```bash
python manage.py test ecop.tests -v 2
```

## Future Work

1. Implement buyer matching algorithm
2. Integrate with payment gateways
3. Add more detailed analytics and reporting
4. Implement push notifications
5. Add support for multiple crops per group
6. Implement bulk SMS for notifications

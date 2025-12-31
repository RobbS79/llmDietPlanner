"""
Test suite for login_app authentication endpoints.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .utils import generate_email_verification_token, verify_email_token
import json


class RegistrationTestCase(TestCase):
    """Test cases for user registration."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.register_url = reverse('login_app:register')
    
    def test_registration_success(self):
        """Test successful user registration."""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'securepass123',
            'passwordConfirm': 'securepass123'
        }
        
        response = self.client.post(self.register_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        self.assertIsNone(response.data['error'])
        self.assertEqual(response.data['data']['username'], 'testuser')
        self.assertEqual(response.data['data']['email'], 'test@example.com')
        
        # Verify user was created but is inactive
        user = User.objects.get(username='testuser')
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, 'test@example.com')
    
    def test_registration_duplicate_username(self):
        """Test registration with duplicate username."""
        User.objects.create_user(username='testuser', email='existing@example.com', password='pass123')
        
        data = {
            'username': 'testuser',
            'email': 'new@example.com',
            'password': 'securepass123',
            'passwordConfirm': 'securepass123'
        }
        
        response = self.client.post(self.register_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('already exists', response.data['error'])
    
    def test_registration_duplicate_email(self):
        """Test registration with duplicate email."""
        User.objects.create_user(username='existing', email='test@example.com', password='pass123')
        
        data = {
            'username': 'newuser',
            'email': 'test@example.com',
            'password': 'securepass123',
            'passwordConfirm': 'securepass123'
        }
        
        response = self.client.post(self.register_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('already registered', response.data['error'])
    
    def test_registration_password_mismatch(self):
        """Test registration with mismatched passwords."""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'securepass123',
            'passwordConfirm': 'differentpass123'
        }
        
        response = self.client.post(self.register_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('do not match', response.data['error'])
    
    def test_registration_weak_password(self):
        """Test registration with weak password."""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': '1234567',  # Too short and no letters
            'passwordConfirm': '1234567'
        }
        
        response = self.client.post(self.register_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')


class EmailVerificationTestCase(TestCase):
    """Test cases for email verification."""
    
    def setUp(self):
        """Set up test client and user."""
        self.client = APIClient()
        self.verify_url = reverse('login_app:verify-email')
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='securepass123',
            is_active=False
        )
    
    def test_email_verification_success(self):
        """Test successful email verification."""
        uid, token = generate_email_verification_token(self.user)
        
        response = self.client.get(self.verify_url, {'uid': uid, 'token': token})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertIsNone(response.data['error'])
        
        # Verify user is now active
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
    
    def test_email_verification_invalid_token(self):
        """Test email verification with invalid token."""
        uid, _ = generate_email_verification_token(self.user)
        invalid_token = 'invalid-token-123'
        
        response = self.client.get(self.verify_url, {'uid': uid, 'token': invalid_token})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('Invalid or expired', response.data['error'])
        
        # Verify user is still inactive
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
    
    def test_email_verification_missing_params(self):
        """Test email verification with missing parameters."""
        response = self.client.get(self.verify_url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('Missing uid or token', response.data['error'])
    
    def test_email_verification_already_verified(self):
        """Test email verification for already active user."""
        self.user.is_active = True
        self.user.save()
        
        uid, token = generate_email_verification_token(self.user)
        
        response = self.client.get(self.verify_url, {'uid': uid, 'token': token})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertIn('already verified', response.data['data']['message'])


class LoginTestCase(TestCase):
    """Test cases for user login."""
    
    def setUp(self):
        """Set up test client and users."""
        self.client = APIClient()
        self.login_url = reverse('login_app:login')
        
        # Create superuser (root user)
        self.superuser = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='rootpass123'
        )
        
        # Create regular active user
        self.regular_user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='securepass123',
            is_active=True
        )
        
        # Create inactive user
        self.inactive_user = User.objects.create_user(
            username='inactive',
            email='inactive@example.com',
            password='securepass123',
            is_active=False
        )
    
    def test_superuser_login_success(self):
        """Test successful login for superuser (root user)."""
        data = {
            'username': 'root',
            'password': 'rootpass123'
        }
        
        response = self.client.post(self.login_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertIsNone(response.data['error'])
        self.assertIn('access', response.data['data'])
        self.assertIn('refresh', response.data['data'])
        self.assertEqual(response.data['data']['user']['username'], 'root')
        self.assertTrue(self.superuser.is_superuser)
    
    def test_regular_user_login_success(self):
        """Test successful login for regular user."""
        data = {
            'username': 'testuser',
            'password': 'securepass123'
        }
        
        response = self.client.post(self.login_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertIn('access', response.data['data'])
        self.assertIn('refresh', response.data['data'])
        self.assertEqual(response.data['data']['user']['username'], 'testuser')
    
    def test_login_with_email(self):
        """Test login using email instead of username."""
        data = {
            'username': 'test@example.com',
            'password': 'securepass123'
        }
        
        response = self.client.post(self.login_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertIn('access', response.data['data'])
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        data = {
            'username': 'testuser',
            'password': 'wrongpassword'
        }
        
        response = self.client.post(self.login_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('Invalid', response.data['error'])
    
    def test_login_inactive_user(self):
        """Test login attempt for inactive user."""
        data = {
            'username': 'inactive',
            'password': 'securepass123'
        }
        
        response = self.client.post(self.login_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('not active', response.data['error'])
    
    def test_login_nonexistent_user(self):
        """Test login with non-existent username."""
        data = {
            'username': 'nonexistent',
            'password': 'somepassword'
        }
        
        response = self.client.post(self.login_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['status'], 'error')


class TokenRefreshTestCase(TestCase):
    """Test cases for JWT token refresh."""
    
    def setUp(self):
        """Set up test client and user."""
        self.client = APIClient()
        self.refresh_url = reverse('login_app:token-refresh')
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='securepass123',
            is_active=True
        )
    
    def test_token_refresh_success(self):
        """Test successful token refresh."""
        # Get initial tokens
        refresh_token = RefreshToken.for_user(self.user)
        access_token = refresh_token.access_token
        
        # Refresh the token
        data = {'refresh': str(refresh_token)}
        response = self.client.post(self.refresh_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        # New access token should be different
        self.assertNotEqual(response.data['access'], str(access_token))
    
    def test_token_refresh_invalid_token(self):
        """Test token refresh with invalid refresh token."""
        data = {'refresh': 'invalid-token-123'}
        response = self.client.post(self.refresh_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticationFlowTestCase(TestCase):
    """Integration tests for complete authentication flow."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.register_url = reverse('login_app:register')
        self.verify_url = reverse('login_app:verify-email')
        self.login_url = reverse('login_app:login')
    
    def test_complete_registration_and_login_flow(self):
        """Test complete flow: register -> verify -> login."""
        # Step 1: Register
        register_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'securepass123',
            'passwordConfirm': 'securepass123'
        }
        register_response = self.client.post(self.register_url, register_data, format='json')
        self.assertEqual(register_response.status_code, status.HTTP_201_CREATED)
        
        user = User.objects.get(username='newuser')
        self.assertFalse(user.is_active)
        
        # Step 2: Verify email
        uid, token = generate_email_verification_token(user)
        verify_response = self.client.get(self.verify_url, {'uid': uid, 'token': token})
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        
        # Step 3: Login
        login_data = {
            'username': 'newuser',
            'password': 'securepass123'
        }
        login_response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn('access', login_response.data['data'])
        self.assertIn('refresh', login_response.data['data'])

